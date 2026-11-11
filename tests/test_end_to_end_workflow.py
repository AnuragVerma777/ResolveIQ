"""Complete end-to-end integration test for ResolveIQ Day 2 workflow:

PayPal dispute -> Classification -> Upload Evidence -> Document Extraction ->
Evidence Matching -> Missing Evidence Detection -> Completeness Calculation ->
AI Response Generation -> Merchant Review, Edit & Approval -> PayPal Submission.
"""
import io
import shutil
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.config import Settings, get_settings
from backend.main import app
from tests.test_document_pipeline import create_dummy_docx, create_dummy_pdf


@pytest.fixture
def workflow_client():
    temp_dir = Path("test_scratch_e2e")
    temp_dir.mkdir(parents=True, exist_ok=True)
    sub_dir = Path(tempfile.mkdtemp(dir=str(temp_dir)))
    test_db = str(sub_dir / "test_resolveiq.db")
    test_uploads = str(sub_dir / "test_uploads")

    def override_settings():
        return Settings(
            db_path=test_db,
            upload_dir=test_uploads,
            max_upload_size_mb=2,
            gemini_api_key="",
        )

    app.dependency_overrides[get_settings] = override_settings
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    shutil.rmtree(sub_dir, ignore_errors=True)


def test_complete_end_to_end_investigation_workflow(workflow_client):
    dispute_id = "PP-E2E-99001"

    # Step 1: Register incoming PayPal dispute
    create_res = workflow_client.post(
        "/api/disputes",
        json={
            "dispute_id": dispute_id,
            "reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
            "customer_complaint": "I ordered an electronic keyboard two weeks ago and it never arrived.",
            "transaction_id": "TXN-E2E-77",
            "amount": 299.99,
            "currency": "USD",
            "merchant_context": "Dispatched via FedEx Express with tracking. Warehouse recorded serial number.",
        },
    )
    assert create_res.status_code == 201

    # Step 2: Dispute Classification Engine (initial assessment)
    classify_res = workflow_client.post(
        "/api/disputes/classify",
        json={
            "dispute_id": dispute_id,
            "dispute_reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
            "customer_complaint": "Never received item.",
            "transaction_details": {"amount": 299.99, "currency": "USD"},
        },
    )
    assert classify_res.status_code == 200
    classification = classify_res.json()
    assert classification["dispute_category"] == "item_not_received"
    assert classification["original_paypal_reason"] == "MERCHANDISE_OR_SERVICE_NOT_RECEIVED"
    assert len(classification["missing_information"]) > 0

    # Step 3: Merchant uploads evidence (PDF invoice & Delivery scan)
    pdf_invoice = create_dummy_pdf("Invoice #INV-E2E\nOrder ID: ORD-99001\nTotal: $299.99 USD\nItem: Electronic Keyboard")
    up_inv = workflow_client.post(
        "/api/documents/upload",
        files={"file": ("invoice.pdf", pdf_invoice, "application/pdf")},
        data={"dispute_id": dispute_id, "doc_type": "invoice"},
    )
    assert up_inv.status_code == 201
    assert up_inv.json()["status"] == "COMPLETED"
    assert up_inv.json()["extracted_fields"]["order_id"] == "ORD-99001"

    pdf_tracking = create_dummy_pdf("FedEx Express Tracking #940011189922\nDelivered: 2026-05-02\nSigned: Porch Delivery")
    up_trk = workflow_client.post(
        "/api/documents/upload",
        files={"file": ("fedex_delivery.pdf", pdf_tracking, "application/pdf")},
        data={"dispute_id": dispute_id, "doc_type": "delivery_confirmation"},
    )
    assert up_trk.status_code == 201
    assert up_trk.json()["extracted_fields"]["tracking_number"] == "940011189922"
    assert up_trk.json()["extracted_fields"]["delivery_date"] == "2026-05-02"

    # Step 4: Verify documents are associated with dispute
    docs_res = workflow_client.get(f"/api/disputes/{dispute_id}/documents")
    assert docs_res.status_code == 200
    docs = docs_res.json()
    assert len(docs) == 2

    # Step 5: Evidence Matching & Completeness Calculation (Evidence Matrix)
    matrix_res = workflow_client.post(f"/api/disputes/{dispute_id}/evidence-matrix")
    assert matrix_res.status_code == 200
    matrix = matrix_res.json()
    assert matrix["dispute_id"] == dispute_id
    assert len(matrix["matrix_items"]) >= 2
    assert matrix["completeness_score"]["overall_score"] > 60

    # Delivery claim should now be Supported by the FedEx document
    delivery_item = next(
        item for item in matrix["matrix_items"]
        if "delivered" in item["claim"].lower() or "received" in item["claim"].lower()
    )
    assert delivery_item["evidence_status"] == "Supported"
    assert len(delivery_item["supporting_evidence"]) > 0

    # Step 6: AI Response Generation (Resolution Studio)
    gen_res = workflow_client.post(f"/api/disputes/{dispute_id}/resolution/generate")
    assert gen_res.status_code == 200
    draft = gen_res.json()
    response_id = draft["response_id"]
    assert draft["version"] == 1
    assert draft["submission_status"] == "DRAFT"
    assert "940011189922" in draft["official_response_letter"]
    assert len(draft["verified_facts"]) > 0

    # Step 7: Verification of security gates: Cannot submit unapproved draft
    bad_submit = workflow_client.post(f"/api/disputes/{dispute_id}/resolution/{response_id}/submit")
    assert bad_submit.status_code == 400
    assert "mandatory" in bad_submit.json()["detail"].lower()

    # Step 8: Merchant edits draft
    edited_text = draft["official_response_letter"] + "\n\nAdditional Merchant Proof: Warehouse dispatch scan confirmed intact."
    edit_res = workflow_client.put(
        f"/api/disputes/{dispute_id}/resolution/{response_id}",
        json={"official_response_letter": edited_text, "edit_notes": "Added warehouse dispatch log reference"},
    )
    assert edit_res.status_code == 200
    edited_draft = edit_res.json()
    new_response_id = edited_draft["response_id"]
    assert edited_draft["version"] == 2
    assert "Warehouse dispatch scan" in edited_draft["official_response_letter"]

    # Step 9: Explicit Merchant Approval
    approve_res = workflow_client.post(
        f"/api/disputes/{dispute_id}/resolution/{new_response_id}/approve",
        json={"approver_name": "Compliance Lead / Alex Rivera", "confirmed": True},
    )
    assert approve_res.status_code == 200
    assert approve_res.json()["approved_by_merchant"] is True
    assert approve_res.json()["submission_status"] == "APPROVED"

    # Step 10: Official Submission to PayPal
    submit_res = workflow_client.post(f"/api/disputes/{dispute_id}/resolution/{new_response_id}/submit")
    assert submit_res.status_code == 200
    sub_res = submit_res.json()
    assert sub_res["status"] == "SUBMITTED"

    # Step 11: Audit trail verification
    audit_res = workflow_client.get(f"/api/disputes/{dispute_id}/audit-trail")
    assert audit_res.status_code == 200
    actions = [log["action"] for log in audit_res.json()]
    assert "RESPONSE_GENERATED" in actions
    assert "RESPONSE_EDITED" in actions
    assert "MERCHANT_APPROVED" in actions
    assert "PAYPAL_SUBMITTED" in actions
