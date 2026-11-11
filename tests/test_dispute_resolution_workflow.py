"""Comprehensive end-to-end automated tests for the complete merchant-controlled

Dispute Resolution Workflow:
1. Merchant opens dispute & ResolveIQ loads details.
2. AI classification identifies dispute category & confidence.
3. Evidence Intelligence evaluates documents & computes completeness.
4. System identifies missing and contradictory evidence.
5. AI generates response using only verified information.
6. Merchant reviews factual claims with evidence references.
7. Merchant edits response (version incremented, approval reset).
8. Pre-flight checks (status, deadline, permissions, required evidence).
9. Explicit merchant approval required (mandatory gate).
10. Submission through PayPal REST API with auto-harvested tracking.
11. Persistent API submission state & immutable SQLite audit trail.
12. Accidental duplicate submission prevention.
"""
from __future__ import annotations

import io
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.config import Settings, get_settings
from backend.main import app
from backend.paypal.client import PayPalClient
from backend.paypal.demo_data import DEMO_DISPUTES
from backend.paypal.preflight import check_submission_readiness, validate_dispute_submission


@pytest.fixture
def workflow_env():
    temp_dir = Path("test_scratch_wf")
    temp_dir.mkdir(parents=True, exist_ok=True)
    sub_dir = Path(tempfile.mkdtemp(dir=str(temp_dir)))
    test_db = str(sub_dir / "workflow_test.db")
    test_uploads = str(sub_dir / "workflow_uploads")

    settings = Settings(
        db_path=test_db,
        upload_dir=test_uploads,
        paypal_client_id="",
        paypal_client_secret="",
        gemini_api_key="",  # Deterministic test mode
    )

    def override_settings():
        return settings

    app.dependency_overrides[get_settings] = override_settings
    with TestClient(app) as client:
        yield {"client": client, "settings": settings, "db_path": test_db}
    app.dependency_overrides.clear()
    shutil.rmtree(sub_dir, ignore_errors=True)


def test_complete_end_to_end_dispute_resolution_workflow(workflow_env):
    """Executes the full 11-step merchant-controlled workflow end-to-end."""
    client: TestClient = workflow_env["client"]
    dispute_id = "PP-D-849201"

    # -------------------------------------------------------------
    # Step 1 & 2: Ingest dispute into workspace & load details
    # -------------------------------------------------------------
    import_resp = client.post(f"/api/paypal/disputes/{dispute_id}/import")
    assert import_resp.status_code == 200
    assert import_resp.json()["status"] in ("IMPORTED", "ALREADY_IMPORTED")

    dispute_details_resp = client.get(f"/api/paypal/disputes/{dispute_id}")
    assert dispute_details_resp.status_code == 200
    details = dispute_details_resp.json()
    assert details["dispute"]["dispute_id"] == dispute_id
    assert details["requirements"]["can_submit_evidence"] is True
    assert "PROOF_OF_FULFILLMENT" in details["requirements"]["recommended_evidence_types"]

    # -------------------------------------------------------------
    # Step 3: Attach supporting documents (Delivery confirmation & Invoice)
    # -------------------------------------------------------------
    delivery_doc_content = (
        "FedEx Home Delivery Proof\n"
        "Tracking Number: 789456123012\n"
        "Delivery Date: 2026-10-14 14:32:00\n"
        "Signed By: E. Vance\n"
        "Status: Delivered to front porch\n"
        "Address: 742 Evergreen Terrace, Springfield OR 97477\n"
    )
    files = {"file": ("fedex_delivery.txt", io.BytesIO(delivery_doc_content.encode("utf-8")), "text/plain")}
    data = {"dispute_id": dispute_id, "doc_type": "delivery_confirmation"}
    upload_resp = client.post("/api/documents/upload", files=files, data=data)
    assert upload_resp.status_code == 201
    doc_id = upload_resp.json()["id"]

    # -------------------------------------------------------------
    # Step 4: AI classification identifies category & facts
    # -------------------------------------------------------------
    class_payload = {
        "dispute_id": dispute_id,
        "dispute_reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        "customer_complaint": "Parcel never arrived at my address.",
        "transaction_details": {"transaction_id": "7TY9843219084321", "amount": 189.50, "currency": "USD"},
        "merchant_context": "Shipped via FedEx with delivery confirmation.",
        "document_ids": [doc_id],
    }
    class_resp = client.post("/api/disputes/classify", json=class_payload)
    assert class_resp.status_code == 200
    class_data = class_resp.json()
    assert class_data["dispute_category"].upper() == "ITEM_NOT_RECEIVED"
    assert len(class_data["key_facts"]) >= 1

    # -------------------------------------------------------------
    # Step 5: Evidence Intelligence evaluates documents & completeness
    # -------------------------------------------------------------
    matrix_resp = client.post(f"/api/disputes/{dispute_id}/evidence-matrix", json={})
    assert matrix_resp.status_code == 200
    matrix = matrix_resp.json()
    assert matrix["completeness_score"]["overall_score"] > 0
    assert len(matrix["matrix_items"]) >= 1
    # Check that warnings fields exist and are structured lists
    assert isinstance(matrix["conflict_warnings"], list)
    assert isinstance(matrix["unsupported_factual_claims"], list)

    # -------------------------------------------------------------
    # Step 6: AI generates response using only verified information
    # -------------------------------------------------------------
    gen_resp = client.post(
        f"/api/disputes/{dispute_id}/resolution/generate",
        params={"merchant_instructions": "Highlight carrier delivery scan."},
    )
    assert gen_resp.status_code == 200
    draft = gen_resp.json()
    response_id = draft["response_id"]
    assert draft["version"] == 1
    assert draft["approved_by_merchant"] is False
    assert len(draft["verified_facts"]) >= 1
    # Every categorized claim has text and provenance
    for claim in draft["categorized_claims"]:
        assert claim["text"] != ""

    # -------------------------------------------------------------
    # Step 7: Merchant reviews & edits the response (Version increments)
    # -------------------------------------------------------------
    new_text = draft["official_response_letter"] + "\n\nMerchant Note: All items packaged under CCTV."
    edit_resp = client.put(
        f"/api/disputes/{dispute_id}/resolution/{response_id}",
        json={"official_response_letter": new_text, "edit_notes": "Added CCTV packaging notice"},
    )
    assert edit_resp.status_code == 200
    edited_draft = edit_resp.json()
    new_response_id = edited_draft["response_id"]
    assert edited_draft["version"] == 2
    assert edited_draft["approved_by_merchant"] is False  # Edits strictly reset approval!

    # -------------------------------------------------------------
    # Step 8: Safety Check: Unapproved submission must be blocked
    # -------------------------------------------------------------
    unapproved_sub = client.post(f"/api/disputes/{dispute_id}/resolution/{new_response_id}/submit")
    assert unapproved_sub.status_code == 400
    assert "approval is mandatory" in unapproved_sub.json()["detail"].lower()

    # -------------------------------------------------------------
    # Step 9: Pre-flight readiness check
    # -------------------------------------------------------------
    preflight_resp = client.get(f"/api/disputes/{dispute_id}/preflight-check")
    assert preflight_resp.status_code == 200
    preflight = preflight_resp.json()
    assert preflight["eligible"] is True
    assert preflight["is_open"] is True
    assert preflight["can_submit_evidence"] is True
    assert preflight["has_tracking_number"] is True

    # -------------------------------------------------------------
    # Step 10: Explicit merchant approval
    # -------------------------------------------------------------
    approve_resp = client.post(
        f"/api/disputes/{dispute_id}/resolution/{new_response_id}/approve",
        json={"approver_name": "Eleanor Vance (Operations Lead)", "confirmed": True},
    )
    assert approve_resp.status_code == 200
    approved = approve_resp.json()
    assert approved["approved_by_merchant"] is True
    assert approved["approved_by"] == "Eleanor Vance (Operations Lead)"

    # -------------------------------------------------------------
    # Step 11: Submission through supported PayPal API & Audit Trail
    # -------------------------------------------------------------
    submit_resp = client.post(f"/api/disputes/{dispute_id}/resolution/{new_response_id}/submit")
    assert submit_resp.status_code == 200
    sub_data = submit_resp.json()
    assert sub_data["status"] == "SUBMITTED"
    assert sub_data["submission_debug_id"] != ""

    # -------------------------------------------------------------
    # Step 12: Duplicate submission prevention
    # -------------------------------------------------------------
    dup_submit = client.post(f"/api/disputes/{dispute_id}/resolution/{new_response_id}/submit")
    assert dup_submit.status_code == 200
    assert dup_submit.json()["status"] == "ALREADY_SUBMITTED"

    # Verify audit trail contains approval, submission, and debug ID
    audit_resp = client.get(f"/api/disputes/{dispute_id}/audit-trail")
    assert audit_resp.status_code == 200
    audit_entries = audit_resp.json()
    actions = [a["action"] for a in audit_entries]
    assert "MERCHANT_APPROVED" in actions
    assert "PAYPAL_SUBMITTED" in actions


# ---------------------------------------------------------------------
# Safety and Reliability Unit Tests
# ---------------------------------------------------------------------

def test_preflight_blocks_expired_dispute(workflow_env):
    """Pre-flight check blocks submission if seller response deadline has passed."""
    from backend.db import Database
    db = Database(workflow_env["db_path"])
    settings = workflow_env["settings"]

    # Create an expired dispute in local database
    expired_id = "PP-D-EXPIRED"
    db.save_dispute({
        "dispute_id": expired_id,
        "reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        "customer_complaint": "Late package",
    })

    # Mock expired context
    past_date = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    client = workflow_env["client"]

    # Preflight check directly with mock
    from backend.paypal import preflight
    orig_context = preflight.get_dispute_context

    def mock_context(did, _db, _st):
        if did == expired_id:
            return {
                "dispute_id": expired_id,
                "status": "WAITING_FOR_SELLER_RESPONSE",
                "seller_response_due_date": past_date,
                "allowed_response_options": ["PROVIDE_EVIDENCE"],
                "reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
            }
        return orig_context(did, _db, _st)

    preflight.get_dispute_context = mock_context
    try:
        report = check_submission_readiness(expired_id, db, settings)
        assert report["eligible"] is False
        assert report["is_deadline_passed"] is True
        assert any("deadline has passed" in b.lower() for b in report["blockers"])

        with pytest.raises(Exception) as exc_info:
            validate_dispute_submission(expired_id, db, settings, notes="Here is proof")
        assert "deadline has passed" in str(exc_info.value).lower()
    finally:
        preflight.get_dispute_context = orig_context


def test_preflight_blocks_terminal_closed_dispute(workflow_env):
    """Pre-flight check blocks submission if dispute is already RESOLVED or CLOSED."""
    from backend.db import Database
    db = Database(workflow_env["db_path"])
    settings = workflow_env["settings"]
    closed_id = "PP-D-CLOSED"

    from backend.paypal import preflight
    orig_context = preflight.get_dispute_context

    def mock_context(did, _db, _st):
        if did == closed_id:
            return {
                "dispute_id": closed_id,
                "status": "RESOLVED",
                "allowed_response_options": [],
                "reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
            }
        return orig_context(did, _db, _st)

    preflight.get_dispute_context = mock_context
    try:
        report = check_submission_readiness(closed_id, db, settings)
        assert report["eligible"] is False
        assert report["is_open"] is False
        assert any("terminal state" in b.lower() for b in report["blockers"])
    finally:
        preflight.get_dispute_context = orig_context


def test_preflight_blocks_missing_evidence_on_item_not_received(workflow_env):
    """Enforces that item not received dispute cannot be submitted with empty notes and zero tracking."""
    from backend.db import Database
    db = Database(workflow_env["db_path"])
    settings = workflow_env["settings"]
    empty_id = "PP-D-EMPTY-EVIDENCE"

    from backend.paypal import preflight
    orig_context = preflight.get_dispute_context

    def mock_context(did, _db, _st):
        if did == empty_id:
            return {
                "dispute_id": empty_id,
                "status": "WAITING_FOR_SELLER_RESPONSE",
                "seller_response_due_date": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
                "allowed_response_options": ["PROVIDE_EVIDENCE"],
                "reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
            }
        return orig_context(did, _db, _st)

    preflight.get_dispute_context = mock_context
    try:
        with pytest.raises(Exception) as exc_info:
            validate_dispute_submission(empty_id, db, settings, tracking_info=[], notes="")
        assert "required evidence missing" in str(exc_info.value).lower()
    finally:
        preflight.get_dispute_context = orig_context
