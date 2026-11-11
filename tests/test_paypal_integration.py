"""Automated tests for PayPal Integration:

OAuth authentication, token caching, 401 re-authentication, rate limiting (429),
timeout handling (504), error sanitation, dispute requirements parser,
transaction search, evidence submission, audit logging, and dispute import.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.config import Settings, get_settings
from backend.main import app
from backend.paypal.client import (
    PayPalAPIError,
    PayPalAuthError,
    PayPalClient,
    PayPalNotFoundError,
    PayPalRateLimitError,
    PayPalTimeoutError,
    parse_dispute_requirements,
)


@pytest.fixture
def test_env():
    temp_dir = Path("test_scratch_paypal")
    temp_dir.mkdir(parents=True, exist_ok=True)
    sub_dir = Path(tempfile.mkdtemp(dir=str(temp_dir)))
    test_db = str(sub_dir / "test_paypal.db")
    test_uploads = str(sub_dir / "test_uploads")

    settings = Settings(
        db_path=test_db,
        upload_dir=test_uploads,
        paypal_client_id="",
        paypal_client_secret="",
    )

    def override_settings():
        return settings

    app.dependency_overrides[get_settings] = override_settings
    with TestClient(app) as client:
        yield {"client": client, "settings": settings, "db_path": test_db}
    app.dependency_overrides.clear()
    shutil.rmtree(sub_dir, ignore_errors=True)


# ---------------------------------------------------------------------
# 1. OAuth & Token Caching Tests
# ---------------------------------------------------------------------

def test_oauth_token_caching_and_expiry():
    token_calls = 0

    def handler(request: httpx.Request):
        nonlocal token_calls
        if request.url.path.endswith("/v1/oauth2/token"):
            token_calls += 1
            return httpx.Response(200, json={"access_token": f"token-{token_calls}", "expires_in": 3600})
        return httpx.Response(200, json={"items": []})

    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    settings = Settings(paypal_client_id="test_id", paypal_client_secret="test_secret")
    client = PayPalClient(settings, http=http)

    # First call acquires token
    client.list_disputes()
    assert token_calls == 1

    # Second call reuses cached token (expires_in = 3600)
    client.list_disputes()
    assert token_calls == 1

    # Force expiration by manipulating token_expires_at
    client._token_expires_at = time.monotonic() - 10
    client.list_disputes()
    assert token_calls == 2


def test_oauth_missing_credentials_raises_auth_error():
    settings = Settings(paypal_client_id="", paypal_client_secret="")
    client = PayPalClient(settings)
    with pytest.raises(PayPalAuthError) as exc_info:
        client._access_token()
    assert "credentials not configured" in str(exc_info.value).lower()
    assert exc_info.value.status_code == 401


def test_oauth_rejected_credentials_raises_auth_error():
    def handler(request: httpx.Request):
        if request.url.path.endswith("/v1/oauth2/token"):
            return httpx.Response(401, json={"error": "invalid_client"}, headers={"PayPal-Debug-Id": "dbg-auth-401"})
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    settings = Settings(paypal_client_id="bad_id", paypal_client_secret="bad_secret")
    client = PayPalClient(settings, http=http)

    with pytest.raises(PayPalAuthError) as exc_info:
        client.list_disputes()
    assert exc_info.value.status_code == 401
    assert exc_info.value.request_id == "dbg-auth-401"


# ---------------------------------------------------------------------
# 2. Re-authentication on 401 & Retries
# ---------------------------------------------------------------------

def test_request_reauthenticates_on_expired_token_401():
    """Verify that if an authenticated endpoint returns 401, the client refreshes

    the token and retries the request once automatically.
    """
    token_requests = 0
    dispute_requests = 0

    def handler(request: httpx.Request):
        nonlocal token_requests, dispute_requests
        if request.url.path.endswith("/v1/oauth2/token"):
            token_requests += 1
            return httpx.Response(200, json={"access_token": f"token-v{token_requests}", "expires_in": 3600})
        elif "/v1/customer/disputes" in request.url.path:
            dispute_requests += 1
            auth_header = request.headers.get("authorization", "")
            if auth_header == "Bearer token-v1":
                # First attempt with token-v1 simulated as expired by PayPal server
                return httpx.Response(401, json={"name": "AUTHENTICATION_FAILURE"}, headers={"PayPal-Debug-Id": "dbg-401-first"})
            elif auth_header == "Bearer token-v2":
                # Second attempt after auto-refresh succeeds
                return httpx.Response(200, json={"items": [{"dispute_id": "PP-D-RECOVERED"}]})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    settings = Settings(paypal_client_id="client_id", paypal_client_secret="client_secret")
    client = PayPalClient(settings, http=http)

    res = client.list_disputes()
    assert res["items"][0]["dispute_id"] == "PP-D-RECOVERED"
    assert token_requests == 2
    assert dispute_requests == 2


# ---------------------------------------------------------------------
# 3. Rate Limit (429) & Timeout (504) Handling
# ---------------------------------------------------------------------

def test_rate_limit_429_handling():
    def handler(request: httpx.Request):
        if request.url.path.endswith("/v1/oauth2/token"):
            return httpx.Response(200, json={"access_token": "valid-token", "expires_in": 3600})
        return httpx.Response(
            429,
            json={"name": "RATE_LIMIT_REACHED"},
            headers={"PayPal-Debug-Id": "dbg-429", "Retry-After": "45"},
        )

    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    settings = Settings(paypal_client_id="client_id", paypal_client_secret="client_secret")
    client = PayPalClient(settings, http=http)

    with pytest.raises(PayPalRateLimitError) as exc_info:
        client.list_disputes()
    assert exc_info.value.status_code == 429
    assert exc_info.value.retry_after == 45
    assert exc_info.value.request_id == "dbg-429"


def test_timeout_504_handling():
    def handler(request: httpx.Request):
        if request.url.path.endswith("/v1/oauth2/token"):
            return httpx.Response(200, json={"access_token": "valid-token", "expires_in": 3600})
        raise httpx.ReadTimeout("Read timed out on PayPal server")

    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    settings = Settings(paypal_client_id="client_id", paypal_client_secret="client_secret")
    client = PayPalClient(settings, http=http)

    with pytest.raises(PayPalTimeoutError) as exc_info:
        client.list_disputes()
    assert exc_info.value.status_code == 504
    assert "timed out" in str(exc_info.value).lower()


# ---------------------------------------------------------------------
# 4. Dispute Requirements & Actions Parser
# ---------------------------------------------------------------------

def test_parse_dispute_requirements_item_not_received():
    dispute = {
        "dispute_id": "PP-D-101",
        "reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        "status": "WAITING_FOR_SELLER_RESPONSE",
        "dispute_state": "REQUIRED_ACTION",
        "allowed_response_options": ["PROVIDE_EVIDENCE", "ACCEPT_CLAIM"],
        "seller_response_due_date": "2026-11-20T23:59:59Z",
    }
    reqs = parse_dispute_requirements(dispute)
    assert reqs["can_submit_evidence"] is True
    assert reqs["can_accept_claim"] is True
    assert "PROOF_OF_FULFILLMENT" in reqs["recommended_evidence_types"]
    assert "Submit Carrier Tracking" in reqs["supported_actions"]
    assert "tracking" in reqs["guidance"].lower()


def test_parse_dispute_requirements_not_as_described():
    dispute = {
        "dispute_id": "PP-D-102",
        "reason": "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED",
        "status": "WAITING_FOR_SELLER_RESPONSE",
        "allowed_response_options": ["PROVIDE_EVIDENCE", "MAKE_OFFER_TO_RESOLVE"],
    }
    reqs = parse_dispute_requirements(dispute)
    assert "MERCHANT_TERMS_AND_CONDITIONS" in reqs["recommended_evidence_types"]
    assert reqs["can_make_offer"] is True


def test_parse_dispute_requirements_unauthorised():
    dispute = {
        "dispute_id": "PP-D-103",
        "reason": "UNAUTHORISED",
        "status": "UNDER_REVIEW",
        "allowed_response_options": ["PROVIDE_EVIDENCE"],
    }
    reqs = parse_dispute_requirements(dispute)
    assert "BUYER_ID" in reqs["recommended_evidence_types"]
    assert "Submit Verified Fulfillment Proof" in reqs["supported_actions"]


# ---------------------------------------------------------------------
# 5. FastAPI Endpoints Tests
# ---------------------------------------------------------------------

def test_paypal_status_unconfigured(test_env):
    client = test_env["client"]
    resp = client.get("/api/paypal/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["connected"] is False
    assert data["configured"] is False
    assert data["mode"] == "demo"
    assert "paypal_client_secret" not in data


def test_paypal_disputes_fallback_demo(test_env):
    """When credentials are not set, disputes endpoint returns demo records

    explicitly marked with is_sandbox=False and source='demo'.
    """
    client = test_env["client"]
    resp = client.get("/api/paypal/disputes")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "demo"
    assert data["is_sandbox"] is False
    assert len(data["items"]) >= 1
    first = data["items"][0]
    assert first["is_sandbox"] is False
    assert "dispute_id" in first


def test_paypal_dispute_details_and_requirements(test_env):
    client = test_env["client"]
    resp = client.get("/api/paypal/disputes/PP-D-849201")
    assert resp.status_code == 200
    data = resp.json()
    assert data["dispute"]["dispute_id"] == "PP-D-849201"
    assert "requirements" in data
    assert data["requirements"]["can_submit_evidence"] is True
    assert "PROOF_OF_FULFILLMENT" in data["requirements"]["recommended_evidence_types"]


def test_paypal_transactions_endpoint(test_env):
    client = test_env["client"]
    resp = client.get("/api/paypal/transactions")
    assert resp.status_code == 200
    data = resp.json()
    assert "transaction_details" in data
    assert len(data["transaction_details"]) >= 1


def test_paypal_evidence_submission_and_audit_trail(test_env):
    client = test_env["client"]

    # Submit evidence via POST /api/paypal/disputes/{id}/provide-evidence
    submission_payload = {
        "evidence_type": "PROOF_OF_FULFILLMENT",
        "carrier_name": "FEDEX",
        "tracking_number": "789456123012",
        "notes": "Package was shipped via FedEx Ground with signed delivery receipt.",
    }
    resp = client.post("/api/paypal/disputes/PP-D-849201/provide-evidence", json=submission_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUBMITTED"
    assert data["dispute_id"] == "PP-D-849201"
    assert data["submission_debug_id"] != ""

    # Verify audit trail logs the submission operation
    audit_resp = client.get("/api/disputes/PP-D-849201/audit-trail")
    assert audit_resp.status_code == 200
    logs = audit_resp.json()
    submission_log = next((l for l in logs if l["action"] == "PAYPAL_EVIDENCE_SUBMITTED"), None)
    assert submission_log is not None
    assert submission_log["details"]["tracking_number"] == "789456123012"
    assert submission_log["details"]["carrier_name"] == "FEDEX"


def test_paypal_import_dispute_to_workspace(test_env):
    client = test_env["client"]

    # Import demo dispute PP-D-849201 into local database
    resp = client.post("/api/paypal/disputes/PP-D-849201/import")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "IMPORTED"
    assert data["dispute"]["dispute_id"] == "PP-D-849201"
    assert data["dispute"]["reason"] == "MERCHANDISE_OR_SERVICE_NOT_RECEIVED"

    # Now verify it appears in local disputes list
    list_resp = client.get("/api/disputes")
    assert list_resp.status_code == 200
    disputes = list_resp.json()
    assert any(d["dispute_id"] == "PP-D-849201" for d in disputes)

    # Calling import again returns ALREADY_IMPORTED
    dup_resp = client.post("/api/paypal/disputes/PP-D-849201/import")
    assert dup_resp.status_code == 200
    assert dup_resp.json()["status"] == "ALREADY_IMPORTED"


# ---------------------------------------------------------------------
# 6. Real PayPal Sandbox Integration Test (Conditional)
# ---------------------------------------------------------------------

@pytest.mark.skipif(
    not os.getenv("PAYPAL_CLIENT_ID") or not os.getenv("PAYPAL_CLIENT_SECRET"),
    reason="PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET not present in environment",
)
def test_real_paypal_sandbox_authentication():
    """Only executed when actual PayPal developer sandbox credentials are configured."""
    settings = Settings(
        paypal_client_id=os.getenv("PAYPAL_CLIENT_ID", ""),
        paypal_client_secret=os.getenv("PAYPAL_CLIENT_SECRET", ""),
        paypal_base_url=os.getenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com"),
    )
    client = PayPalClient(settings)
    try:
        conn = client.check_connection()
        assert conn["connected"] is True
        assert conn["mode"] == "sandbox"
        disputes = client.list_disputes(page_size=2)
        assert isinstance(disputes, dict)
    finally:
        client.close()
