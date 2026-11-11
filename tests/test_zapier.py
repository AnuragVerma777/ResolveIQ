"""Tests for modular Zapier Webhooks Integration:

- Structured JSON payloads & UUID timestamps
- Sensitive customer data sanitation
- 2xx successful delivery & verification
- Non-2xx failure & timeout handling
- Retry behavior (retries on 5xx/timeout, no retries on 4xx)
- Duplicate event deduplication
- HTTPS URL validation
- Automation settings and delivery history API endpoints
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.config import Settings, get_settings
from backend.db import Database
from backend.integrations.zapier import (
    AutomationEvent,
    ZapierWebhookService,
    mask_webhook_url,
    sanitize_payload,
)
from backend.main import app


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------

@pytest.fixture
def zapier_env():
    temp_dir = Path("test_scratch_zapier")
    temp_dir.mkdir(parents=True, exist_ok=True)
    sub_dir = Path(tempfile.mkdtemp(dir=str(temp_dir)))
    test_db = str(sub_dir / "zapier_test.db")
    test_uploads = str(sub_dir / "zapier_uploads")

    settings = Settings(
        db_path=test_db,
        upload_dir=test_uploads,
        zapier_webhook_url="",
    )

    def override_settings():
        return settings

    app.dependency_overrides[get_settings] = override_settings
    with TestClient(app) as client:
        yield {"client": client, "settings": settings, "db_path": test_db}
    app.dependency_overrides.clear()
    shutil.rmtree(sub_dir, ignore_errors=True)


# ---------------------------------------------------------------------
# Core Unit Tests
# ---------------------------------------------------------------------

def test_posts_structured_event_and_reports_2xx_delivery():
    seen = []
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: (seen.append(request) or httpx.Response(200)))
    )
    service = ZapierWebhookService("https://hooks.zapier.com/hooks/catch/test", http=client)
    result = service.emit(AutomationEvent.EVIDENCE_MISSING, {"dispute_id": "D-1", "missing": ["tracking"]})
    payload = json.loads(seen[0].content)
    assert result.delivered and result.status_code == 200
    assert payload["event"] == "evidence.missing"
    assert payload["data"]["dispute_id"] == "D-1"
    assert payload["event_id"] == result.event_id
    assert "occurred_at" in payload


def test_non_2xx_is_not_reported_as_delivered():
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500)))
    service = ZapierWebhookService("https://hooks.zapier.com/test", http=client, max_retries=0)
    result = service.emit(AutomationEvent.HIGH_PRIORITY, {})
    assert not result.delivered and result.status_code == 500


def test_timeout_is_reported_without_success_simulation():
    def timeout(request):
        raise httpx.TimeoutException("timed out")

    service = ZapierWebhookService(
        "https://hooks.zapier.com/test",
        http=httpx.Client(transport=httpx.MockTransport(timeout)),
        max_retries=0,
    )
    result = service.emit(AutomationEvent.SUBMITTED, {})
    assert not result.delivered and result.error == "timeout"


def test_disabled_and_unconfigured_events_do_not_post():
    disabled = ZapierWebhookService("https://hooks.zapier.com/test", enabled_events=set())
    assert disabled.emit(AutomationEvent.SUBMITTED, {}).error == "disabled"
    unconfigured = ZapierWebhookService(None)
    assert unconfigured.emit(AutomationEvent.SUBMITTED, {}).error == "webhook_not_configured"


def test_all_six_supported_events():
    """Verifies that all 6 required event types are supported and serialized correctly."""
    events = [
        AutomationEvent.DISPUTE_CREATED,
        AutomationEvent.HIGH_PRIORITY,
        AutomationEvent.EVIDENCE_MISSING,
        AutomationEvent.EVIDENCE_READY_FOR_REVIEW,
        AutomationEvent.DEADLINE_APPROACHING,
        AutomationEvent.SUBMITTED,
    ]
    seen = []
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: (seen.append(request) or httpx.Response(200)))
    )
    service = ZapierWebhookService("https://hooks.zapier.com/test", http=client, enabled_events=set(events))

    for ev in events:
        res = service.emit(ev, {"dispute_id": f"D-{ev.value}"})
        assert res.delivered is True

    posted_events = [json.loads(req.content)["event"] for req in seen]
    assert posted_events == [
        "dispute.created",
        "dispute.high_priority",
        "evidence.missing",
        "evidence.ready_for_review",
        "dispute.deadline_approaching",
        "dispute.submitted",
    ]


def test_invalid_url_scheme_rejected():
    """Zapier Catch Hook URL must use HTTPS."""
    with pytest.raises(ValueError) as exc:
        ZapierWebhookService("http://insecure-hook.zapier.com/catch")
    assert "https" in str(exc.value).lower()


def test_sensitive_customer_data_sanitization():
    """Confidential documents, raw text, access tokens, and credit card numbers are stripped."""
    raw_data = {
        "dispute_id": "PP-D-9988",
        "amount": 250.00,
        "customer_email": "john.doe@corporate.com",
        "raw_text": "CONFIDENTIAL FULL OCR OF INVOICE WITH PRIVATE DATA",
        "client_secret": "secret_abc123",
        "access_token": "token_xyz",
        "credit_card": "4111111111111111",
        "file_content": "binary-blob",
    }
    sanitized = sanitize_payload(raw_data)
    assert sanitized["dispute_id"] == "PP-D-9988"
    assert sanitized["amount"] == 250.00
    assert sanitized["customer_email"] == "jo***@corporate.com"  # Masked
    assert "raw_text" not in sanitized
    assert "client_secret" not in sanitized
    assert "access_token" not in sanitized
    assert "credit_card" not in sanitized
    assert "file_content" not in sanitized


def test_retry_behavior_on_server_error():
    """Transient 5xx errors are retried up to max_retries."""
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls < 3:
            return httpx.Response(502)
        return httpx.Response(200)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ZapierWebhookService(
        "https://hooks.zapier.com/catch",
        http=client,
        max_retries=2,
    )
    result = service.emit(AutomationEvent.DISPUTE_CREATED, {"dispute_id": "RETRY-TEST"})
    assert result.delivered is True
    assert result.attempts == 3
    assert calls == 3


def test_no_retry_on_client_error():
    """Client errors (e.g. 400 Bad Request / 404 Not Found) are not retried."""
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(400)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ZapierWebhookService(
        "https://hooks.zapier.com/catch",
        http=client,
        max_retries=3,
    )
    result = service.emit(AutomationEvent.DISPUTE_CREATED, {"dispute_id": "CLIENT-ERR-TEST"})
    assert result.delivered is False
    assert result.attempts == 1
    assert calls == 1


def test_duplicate_event_suppressed():
    """Duplicate events for the same dispute within the window are suppressed."""
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ZapierWebhookService(
        "https://hooks.zapier.com/catch",
        http=client,
        dedup_window_seconds=10.0,
    )
    res1 = service.emit(AutomationEvent.EVIDENCE_MISSING, {"dispute_id": "D-DUP-1"})
    assert res1.delivered is True
    assert calls == 1

    # Immediate second call for same dispute & event should be suppressed
    res2 = service.emit(AutomationEvent.EVIDENCE_MISSING, {"dispute_id": "D-DUP-1"})
    assert res2.delivered is False
    assert res2.error == "duplicate_event_suppressed"
    assert calls == 1


def test_delivery_history_logged_in_database(zapier_env):
    """Deliveries are persistently recorded in SQLite webhook_deliveries table."""
    db = Database(zapier_env["db_path"])
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200)))
    service = ZapierWebhookService(
        "https://hooks.zapier.com/catch/test12345",
        http=client,
        db=db,
    )
    res = service.emit(AutomationEvent.DISPUTE_CREATED, {"dispute_id": "D-DB-TEST"})
    assert res.delivered is True

    # Check delivery log in DB
    deliveries = db.list_webhook_deliveries()
    assert len(deliveries) >= 1
    first = deliveries[0]
    assert first["event_name"] == "dispute.created"
    assert first["dispute_id"] == "D-DB-TEST"
    assert first["delivered"] is True
    assert "https://hooks.zapier.com" in first["target_url_masked"]


def test_mask_webhook_url():
    url = "https://hooks.zapier.com/hooks/catch/123456/abcdef7890/"
    masked = mask_webhook_url(url)
    assert "123456" not in masked
    assert masked.startswith("https://hooks.zapier.com")


# ---------------------------------------------------------------------
# FastAPI Endpoints Tests
# ---------------------------------------------------------------------

def test_automation_settings_endpoints(zapier_env):
    test_client: TestClient = zapier_env["client"]

    # 1. Get default settings
    resp = test_client.get("/api/automation/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_configured"] is False
    assert data["is_verified"] is False
    assert len(data["all_supported_events"]) == 6

    # 2. Update settings with HTTPS URL
    update_payload = {
        "webhook_url": "https://hooks.zapier.com/hooks/catch/9999/8888/",
        "enabled_events": ["dispute.created", "dispute.submitted"],
        "timeout_seconds": 6.0,
        "max_retries": 1,
    }
    put_resp = test_client.put("/api/automation/settings", json=update_payload)
    assert put_resp.status_code == 200
    updated = put_resp.json()
    assert updated["is_configured"] is True
    assert updated["is_verified"] is False  # Must not claim verified until tested!
    assert len(updated["enabled_events"]) == 2

    # 3. Insecure HTTP URL is rejected
    bad_payload = {"webhook_url": "http://insecure.zapier.com/catch"}
    bad_resp = test_client.put("/api/automation/settings", json=bad_payload)
    assert bad_resp.status_code == 400


def test_automation_test_endpoint_updates_verification(zapier_env, monkeypatch):
    test_client: TestClient = zapier_env["client"]

    # Configure URL
    test_client.put(
        "/api/automation/settings",
        json={"webhook_url": "https://hooks.zapier.com/hooks/catch/test/test"},
    )

    # Mock ZapierWebhookService.emit to simulate successful Zapier delivery
    def mock_emit(self, event, data, **kwargs):
        from backend.integrations.zapier import DeliveryResult
        res = DeliveryResult(
            event_id="test_ev_123",
            event=event,
            delivered=True,
            status_code=200,
            response_time_ms=45.0,
        )
        if self.db:
            self.db.save_webhook_delivery({
                "event_id": "test_ev_123",
                "event_name": event.value,
                "dispute_id": str(data.get("dispute_id") or ""),
                "payload": data,
                "target_url_masked": "https://hooks.zapier.com/...",
                "delivered": True,
                "status_code": 200,
                "response_time_ms": 45.0,
            })
        return res

    monkeypatch.setattr(ZapierWebhookService, "emit", mock_emit)

    test_resp = test_client.post("/api/automation/test", json={})
    assert test_resp.status_code == 200
    test_data = test_resp.json()
    assert test_data["success"] is True
    assert test_data["status_code"] == 200
    assert "verified" in test_data["message"].lower()

    # Now verify that GET settings reports is_verified=True
    get_resp = test_client.get("/api/automation/settings")
    assert get_resp.status_code == 200
    assert get_resp.json()["is_verified"] is True
