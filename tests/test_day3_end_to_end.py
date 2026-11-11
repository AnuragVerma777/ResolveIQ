"""ResolveIQ Day 3 Comprehensive End-to-End Integration & Scenario Test Suite.

Covers the full 15-step merchant dispute adjudication journey:
1. Open ResolveIQ & verify system health.
2. Connect to PayPal sandbox if credentials are configured (or graceful demo mode).
3. Load an actual sandbox dispute or select an explicitly labelled demo scenario.
4. Open the dispute investigation workspace & check requirements.
5. Upload an invoice and a tracking document.
6. Extract structured document information & text.
7. Classify the dispute category with Gemini/rule AI.
8. Match evidence to dispute claims.
9. Identify missing and contradictory evidence.
10. Calculate the explainable completeness score.
11. Generate an evidence-backed response draft.
12. Review, edit, and approve the response (mandatory approval gate).
13. Submit through the PayPal API with auto-harvested tracking.
14. Trigger a Zapier automation webhook.
15. Verify immutable unified audit history.
"""
from __future__ import annotations

import io
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.db import Database, init_db
from backend.integrations.zapier import AutomationEvent, ZapierWebhookService
from backend.main import app
from backend.security import reset_rate_limits, reset_submission_locks


@pytest.fixture(autouse=True)
def reset_security_environment():
    reset_rate_limits()
    reset_submission_locks()
    yield
    reset_rate_limits()
    reset_submission_locks()


@pytest.fixture
def day3_env():
    """Isolated test environment with temporary directory in the workspace."""
    base_tmp = Path("test_scratch_day3")
    base_tmp.mkdir(parents=True, exist_ok=True)
    sub_dir = Path(tempfile.mkdtemp(dir=str(base_tmp)))
    test_db = sub_dir / "day3_test.db"
    test_uploads = sub_dir / "uploads"
    test_uploads.mkdir(parents=True, exist_ok=True)
    init_db(str(test_db))

    settings = Settings(
        db_path=str(test_db),
        upload_dir=str(test_uploads),
        paypal_client_id="sandbox_client_id_day3",
        paypal_client_secret="sandbox_client_secret_day3",
        gemini_api_key="",  # Deterministic test mode
        zapier_webhook_url="https://hooks.zapier.com/hooks/catch/111222/xyz789/",
        max_upload_size_mb=15,
        max_request_body_size_mb=20,
        rate_limit_enabled=True,
    )

    from backend.config import get_settings
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app)

    try:
        yield {
            "client": client,
            "db": Database(str(test_db)),
            "settings": settings,
            "sub_dir": sub_dir,
        }
    finally:
        app.dependency_overrides.clear()
        try:
            shutil.rmtree(str(sub_dir), ignore_errors=True)
        except Exception:
            pass


def test_complete_day3_15_step_end_to_end_scenario(day3_env):
    """Execute all 15 steps of the Day 3 integration workflow sequentially."""
    client: TestClient = day3_env["client"]
    db: Database = day3_env["db"]

    # =========================================================================
    # Step 1: Open ResolveIQ & verify system health
    # =========================================================================
    health_resp = client.get("/api/health")
    assert health_resp.status_code == 200
    health = health_resp.json()
    assert health["status"] == "healthy"
    assert health["service"] == "ResolveIQ Intelligence Engine"
    assert health["version"] == "2.0.0"

    # =========================================================================
    # Step 2: Connect to PayPal Sandbox or report active mode
    # =========================================================================
    status_resp = client.get("/api/paypal/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["base_url"] == "https://api-m.sandbox.paypal.com"
    assert status_data["mode"] in ("sandbox", "demo", "demo_fallback")
    assert "token_valid" in status_data

    # =========================================================================
    # Step 3: Load an actual sandbox dispute or select an explicitly labelled demo scenario
    # =========================================================================
    disputes_resp = client.get("/api/paypal/disputes")
    assert disputes_resp.status_code == 200
    dispute_list = disputes_resp.json()
    assert "items" in dispute_list
    assert len(dispute_list["items"]) >= 1

    # Verify that records are explicitly labelled as sandbox or demo
    for item in dispute_list["items"]:
        assert "is_sandbox" in item
        assert "source" in item
        assert item["source"] in ("sandbox", "demo")

    selected_dispute = dispute_list["items"][0]
    dispute_id = selected_dispute["dispute_id"]

    # Import dispute into ResolveIQ workspace
    import_resp = client.post(f"/api/paypal/disputes/{dispute_id}/import")
    assert import_resp.status_code == 200
    import_data = import_resp.json()
    assert import_data["status"] in ("IMPORTED", "ALREADY_IMPORTED")

    # =========================================================================
    # Step 4: Open the dispute investigation workspace & check requirements
    # =========================================================================
    ws_resp = client.get(f"/api/disputes/{dispute_id}")
    assert ws_resp.status_code == 200
    ws_data = ws_resp.json()
    assert ws_data["dispute_id"] == dispute_id
    assert ws_data["dispute"] is not None

    req_resp = client.get(f"/api/paypal/disputes/{dispute_id}/requirements")
    assert req_resp.status_code == 200
    req_data = req_resp.json()
    assert "can_submit_evidence" in req_data
    assert "recommended_evidence_types" in req_data
    assert "supported_actions" in req_data

    # =========================================================================
    # Step 5: Upload an invoice and a tracking document
    # =========================================================================
    # 5A: Invoice document
    invoice_content = (
        "ACME Commerce Official Tax Invoice\n"
        "Order ID: ORD-987654\n"
        "Transaction ID: TXN-PP-554433\n"
        "Customer Name: Alex Morgan\n"
        "Purchase Date: 2026-10-10\n"
        "Product: Ultra Wireless Ergonomic Keyboard\n"
        "Total Amount: $189.50 USD\n"
    )
    inv_file = {
        "file": ("invoice_ord987654.txt", io.BytesIO(invoice_content.encode("utf-8")), "text/plain")
    }
    inv_resp = client.post(
        "/api/documents/upload",
        files=inv_file,
        data={"dispute_id": dispute_id, "doc_type": "invoice"},
    )
    assert inv_resp.status_code == 201
    invoice_doc_id = inv_resp.json()["id"]

    # 5B: Carrier tracking / delivery confirmation document
    tracking_content = (
        "FedEx Express Proof of Delivery\n"
        "Tracking Number: 794822019483\n"
        "Shipment Date: 2026-10-11\n"
        "Delivery Date: 2026-10-14\n"
        "Carrier: FedEx Priority Home\n"
        "Recipient: Alex Morgan\n"
        "Status: Delivered - Left at Front Porch\n"
    )
    track_file = {
        "file": ("fedex_delivery_proof.txt", io.BytesIO(tracking_content.encode("utf-8")), "text/plain")
    }
    track_resp = client.post(
        "/api/documents/upload",
        files=track_file,
        data={"dispute_id": dispute_id, "doc_type": "delivery_confirmation"},
    )
    assert track_resp.status_code == 201
    tracking_doc_id = track_resp.json()["id"]

    # =========================================================================
    # Step 6: Extract document information & verify fields
    # =========================================================================
    doc_inv_check = client.get(f"/api/documents/{invoice_doc_id}")
    assert doc_inv_check.status_code == 200
    inv_fields = doc_inv_check.json()["extracted_fields"]
    assert inv_fields["order_id"] == "ORD-987654"
    assert inv_fields["amount"] == 189.50
    assert inv_fields["currency"] == "USD"

    doc_track_check = client.get(f"/api/documents/{tracking_doc_id}")
    assert doc_track_check.status_code == 200
    track_fields = doc_track_check.json()["extracted_fields"]
    assert track_fields["tracking_number"] == "794822019483"
    assert track_fields["delivery_date"] == "2026-10-14"

    # Preview raw extracted text
    text_preview = client.get(f"/api/documents/{tracking_doc_id}/text")
    assert text_preview.status_code == 200
    assert "794822019483" in text_preview.json()["text"]

    # =========================================================================
    # Step 7: Classify the dispute category with AI
    # =========================================================================
    classify_payload = {
        "dispute_id": dispute_id,
        "dispute_reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        "customer_complaint": "Buyer claims package never arrived at address.",
        "transaction_details": {
            "transaction_id": "TXN-PP-554433",
            "amount": 189.50,
            "currency": "USD",
        },
        "merchant_context": "Shipped with FedEx Priority tracking.",
        "document_ids": [invoice_doc_id, tracking_doc_id],
    }
    classify_resp = client.post("/api/disputes/classify", json=classify_payload)
    assert classify_resp.status_code == 200
    class_data = classify_resp.json()
    assert class_data["dispute_category"].upper() == "ITEM_NOT_RECEIVED"
    assert len(class_data["key_facts"]) >= 1
    assert "confidence" in class_data
    assert "disclaimer" in class_data

    # =========================================================================
    # Step 8: Match evidence to dispute claims
    # =========================================================================
    matrix_resp = client.post(f"/api/disputes/{dispute_id}/evidence-matrix", json={})
    assert matrix_resp.status_code == 200
    matrix_report = matrix_resp.json()
    assert matrix_report["dispute_id"] == dispute_id
    assert len(matrix_report["matrix_items"]) >= 1

    # =========================================================================
    # Step 9: Identify missing and contradictory evidence
    # =========================================================================
    assert "conflict_warnings" in matrix_report
    assert "unsupported_factual_claims" in matrix_report
    assert "recommended_next_actions" in matrix_report

    # =========================================================================
    # Step 10: Calculate the explainable completeness score
    # =========================================================================
    score_breakdown = matrix_report["completeness_score"]
    assert 0 <= score_breakdown["overall_score"] <= 100
    assert "claim_coverage_points" in score_breakdown
    assert "core_evidence_points" in score_breakdown
    assert "explanation" in score_breakdown
    assert "probability of winning" in score_breakdown["disclaimer"].lower()

    # =========================================================================
    # Step 11: Generate an evidence-backed response draft
    # =========================================================================
    gen_resp = client.post(
        f"/api/disputes/{dispute_id}/resolution/generate",
        params={"merchant_instructions": "Emphasize FedEx delivery scan and signature."},
    )
    assert gen_resp.status_code == 200
    draft = gen_resp.json()
    assert draft["version"] == 1
    assert draft["approved_by_merchant"] is False
    assert len(draft["verified_facts"]) >= 1
    assert "794822019483" in draft["official_response_letter"]
    response_id = draft["response_id"]

    # =========================================================================
    # Step 12: Review, edit, and approve the response (mandatory gate)
    # =========================================================================
    # 12A: Unapproved submission must be blocked by safety gate
    unapproved_submit = client.post(f"/api/disputes/{dispute_id}/resolution/{response_id}/submit")
    assert unapproved_submit.status_code == 400
    assert "approval is mandatory" in unapproved_submit.json()["detail"].lower()

    # 12B: Merchant edits response text
    edit_resp = client.put(
        f"/api/disputes/{dispute_id}/resolution/{response_id}",
        json={
            "official_response_letter": draft["official_response_letter"] + "\nReviewed and certified by Merchant Operations.",
            "edit_notes": "Added certification statement.",
        },
    )
    assert edit_resp.status_code == 200
    edited_draft = edit_resp.json()
    assert edited_draft["version"] == 2
    assert edited_draft["approved_by_merchant"] is False
    edited_response_id = edited_draft["response_id"]

    # 12C: Explicit merchant approval
    approve_resp = client.post(
        f"/api/disputes/{dispute_id}/resolution/{edited_response_id}/approve",
        json={"approver_name": "Chief Risk Officer", "confirmed": True},
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["approved_by_merchant"] is True

    # =========================================================================
    # Step 13: Submit through the PayPal API
    # =========================================================================
    # Preflight check must pass
    preflight = client.get(f"/api/disputes/{dispute_id}/preflight-check")
    assert preflight.status_code == 200
    assert preflight.json()["eligible"] is True

    # Submit approved rebuttal package
    mock_pp_result = {"status": "SUBMITTED", "debug_id": "pp-dbg-e2e-live-12345"}
    with patch("backend.paypal.client.PayPalClient.submit_evidence", return_value=mock_pp_result):
        submit_resp = client.post(f"/api/disputes/{dispute_id}/resolution/{edited_response_id}/submit")
        assert submit_resp.status_code == 200
        submit_data = submit_resp.json()
        assert submit_data["status"] == "SUBMITTED"
        assert submit_data["submission_debug_id"] is not None

    # Accidental duplicate submission must be prevented
    dup_resp = client.post(f"/api/disputes/{dispute_id}/resolution/{edited_response_id}/submit")
    assert dup_resp.status_code == 200
    assert dup_resp.json()["status"] == "ALREADY_SUBMITTED"

    # =========================================================================
    # Step 14: Trigger a Zapier webhook
    # =========================================================================
    # Send verification test webhook ping
    from backend.integrations.zapier import DeliveryResult
    mock_delivery = DeliveryResult(
        event_id="e2e_zap_event_999",
        event=AutomationEvent.DISPUTE_CREATED,
        delivered=True,
        status_code=200,
        attempts=1,
        response_time_ms=55.0,
    )
    with patch.object(ZapierWebhookService, "emit", return_value=mock_delivery):
        test_zap_resp = client.post(
            "/api/automation/test",
            json={"webhook_url": "https://hooks.zapier.com/hooks/catch/111222/xyz789/"},
        )
        assert test_zap_resp.status_code == 200
        assert test_zap_resp.json()["success"] is True
        assert test_zap_resp.json()["status_code"] == 200

    # =========================================================================
    # Step 15: Verify unified audit history
    # =========================================================================
    audit_resp = client.get(f"/api/disputes/{dispute_id}/audit-trail")
    assert audit_resp.status_code == 200
    audit_trail = audit_resp.json()
    assert len(audit_trail) >= 5

    recorded_actions = [entry["action"] for entry in audit_trail]
    assert "EVIDENCE_UPLOADED" in recorded_actions
    assert "AI_ANALYSIS_GENERATED" in recorded_actions
    assert "RESPONSE_GENERATED" in recorded_actions
    assert "RESPONSE_EDITED" in recorded_actions
    assert "MERCHANT_APPROVED" in recorded_actions
    assert "PAYPAL_SUBMISSION_ATTEMPTED" in recorded_actions
    assert "PAYPAL_SUBMISSION_SUCCEEDED" in recorded_actions

    # Verify timestamps and actors on all entries
    for log_item in audit_trail:
        assert log_item["timestamp"] is not None
        assert log_item["actor"] is not None
        assert isinstance(log_item["details"], dict)
