"""Automated tests for ResolveIQ AI Resolution Studio.

Tests response generation from verified evidence only, section categorization,
unsupported claims rejection, missing evidence handling, editing versioning,
mandatory approval gates, and PayPal evidence submission.
"""
import io
import shutil
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.ai.resolution_engine import ResolutionEngine
from backend.ai.schemas import (
    CategorizedClaim,
    DisputeResponseDraft,
    FactSectionType,
    StructuredEvidenceRecord,
)
from backend.config import Settings, get_settings
from backend.main import app
from tests.test_document_pipeline import create_dummy_pdf


# =====================================================================
# 1. Response Generation & Evidence Provenance Unit Tests
# =====================================================================

def test_generate_response_from_verified_evidence():
    engine = ResolutionEngine()
    dispute = {
        "dispute_id": "PP-D-88902",
        "dispute_reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        "customer_complaint": "I never received my package at my doorstep.",
        "transaction_details": {"transaction_id": "TXN-112233", "amount": 189.50},
        "merchant_context": "Dispatched via FedEx Home Delivery with signature required.",
    }
    evidence = [
        StructuredEvidenceRecord(
            evidence_id="ev_fedex",
            source_document="fedex_proof.pdf",
            tracking_number="940011189922",
            delivery_date="2026-05-03",
            order_id="ORD-88902",
            amount=189.50,
            currency="USD",
        )
    ]

    draft = engine.generate_response(dispute, evidence)

    assert isinstance(draft, DisputeResponseDraft)
    assert draft.dispute_id == "PP-D-88902"
    assert draft.version == 1
    assert draft.merchant_approval_required is True
    assert draft.approved_by_merchant is False
    assert draft.submission_status == "DRAFT"

    # Verify section separation
    assert len(draft.verified_facts) > 0
    assert any("940011189922" in f for f in draft.verified_facts)
    assert len(draft.merchant_statements) > 0
    assert any("FedEx Home Delivery" in ms for ms in draft.merchant_statements)
    assert len(draft.ai_recommendations) > 0

    # Every verified claim in categorized_claims must cite a valid evidence_id
    verified_claims = [c for c in draft.categorized_claims if c.section == FactSectionType.VERIFIED_FACT]
    assert len(verified_claims) > 0
    for vc in verified_claims:
        assert len(vc.evidence_ids) > 0
        assert "ev_fedex" in vc.evidence_ids
        assert "fedex_proof.pdf" in vc.source_documents

    # Verify disclaimer is present and explicit
    assert "does not guarantee" in draft.disclaimer.lower()
    assert "explicit merchant approval" in draft.disclaimer.lower()


def test_missing_evidence_is_correctly_flagged_as_unknown():
    """When tracking exists without a delivery scan, delivery is flagged as unknown/uncertain."""
    engine = ResolutionEngine()
    dispute = {
        "dispute_id": "PP-D-99001",
        "dispute_reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        "customer_complaint": "Never received item.",
    }
    # Evidence without delivery date
    evidence = [
        StructuredEvidenceRecord(
            evidence_id="ev_ship",
            source_document="manifest.pdf",
            tracking_number="1Z000111",
            shipment_date="2026-04-20",
        )
    ]

    draft = engine.generate_response(dispute, evidence)

    # Must contain missing warnings and questions
    assert len(draft.missing_evidence_warnings) > 0
    assert len(draft.unknown_or_missing_info) > 0
    assert len(draft.questions_for_merchant) > 0

    # Must NOT invent delivery confirmation
    for f in draft.verified_facts:
        assert "delivered on" not in f.lower()


def test_rejects_unsupported_evidence_references():
    """Engine must reject any claim attempting to cite an unsupplied evidence ID."""
    engine = ResolutionEngine()
    evidence = [StructuredEvidenceRecord(evidence_id="ev_valid", source_document="doc.pdf")]
    fake_claim = CategorizedClaim(
        text="Invented tracking",
        section=FactSectionType.VERIFIED_FACT,
        evidence_ids=["ev_nonexistent"],
    )
    with pytest.raises(ValueError, match="unsupported evidence reference"):
        engine.validate_claims_against_evidence([fake_claim], evidence)


def test_cannot_bypass_merchant_approval_gate():
    """Pydantic validator enforces that merchant_approval_required cannot be set to False."""
    with pytest.raises(ValueError, match="mandatory"):
        DisputeResponseDraft(
            response_id="r1",
            dispute_id="D-1",
            version=1,
            subject_line="Sub",
            official_response_letter="Letter",
            merchant_approval_required=False,  # Prohibited!
        )


# =====================================================================
# 2. Review Interface, Editing & PayPal Submission API Tests
# =====================================================================

@pytest.fixture
def resolution_client():
    temp_dir = Path("test_scratch_resolution")
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


def test_full_resolution_studio_api_workflow(resolution_client):
    # 1. Upload proof document
    pdf_bytes = create_dummy_pdf("Tracking Number: 940011189922\nDelivered: 2026-05-03\nOrder ID: ORD-88902\nTotal: $189.50 USD")
    files = {"file": ("delivery_proof.pdf", pdf_bytes, "application/pdf")}
    up_res = resolution_client.post(
        "/api/documents/upload",
        files=files,
        data={"dispute_id": "DISP-RES-1", "doc_type": "delivery_confirmation"},
    )
    assert up_res.status_code == 201

    # 2. Register dispute record
    create_res = resolution_client.post(
        "/api/disputes",
        json={
            "dispute_id": "DISP-RES-1",
            "reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
            "customer_complaint": "I never got the item.",
            "transaction_id": "TXN-88902",
            "amount": 189.50,
            "currency": "USD",
            "merchant_context": "Delivered to porch with tracking scan.",
        },
    )
    assert create_res.status_code == 201

    # 3. Generate Draft Response (POST /api/disputes/{id}/resolution/generate)
    gen_res = resolution_client.post("/api/disputes/DISP-RES-1/resolution/generate")
    assert gen_res.status_code == 200
    draft = gen_res.json()
    response_id = draft["response_id"]
    assert draft["version"] == 1
    assert draft["is_approved"] is False if "is_approved" in draft else draft["approved_by_merchant"] is False
    assert draft["submission_status"] == "DRAFT"
    assert "940011189922" in draft["official_response_letter"]

    # 4. Attempt submission before approval -> Must Fail with HTTP 400!
    unapproved_sub = resolution_client.post(f"/api/disputes/DISP-RES-1/resolution/{response_id}/submit")
    assert unapproved_sub.status_code == 400
    assert "mandatory" in unapproved_sub.json()["detail"].lower()

    # 5. Merchant edits the response letter (PUT /api/disputes/{id}/resolution/{response_id})
    edited_text = draft["official_response_letter"] + "\n\nMerchant Note: Buyer was contacted via email."
    edit_res = resolution_client.put(
        f"/api/disputes/DISP-RES-1/resolution/{response_id}",
        json={"official_response_letter": edited_text, "edit_notes": "Added customer service note"},
    )
    assert edit_res.status_code == 200
    edited_draft = edit_res.json()
    new_response_id = edited_draft["response_id"]
    assert edited_draft["version"] == 2
    assert "Buyer was contacted via email" in edited_draft["official_response_letter"]
    assert edited_draft["approved_by_merchant"] is False  # Editing resets approval!

    # 6. Merchant approves the response (POST /api/disputes/{id}/resolution/{new_response_id}/approve)
    approve_res = resolution_client.post(
        f"/api/disputes/DISP-RES-1/resolution/{new_response_id}/approve",
        json={"approver_name": "Sarah Connor - Operations Manager", "confirmed": True},
    )
    assert approve_res.status_code == 200
    approved_draft = approve_res.json()
    assert approved_draft["approved_by_merchant"] is True
    assert approved_draft["approved_by"] == "Sarah Connor - Operations Manager"
    assert approved_draft["submission_status"] == "APPROVED"

    # 7. Submit approved response to PayPal (POST /api/disputes/{id}/resolution/{new_response_id}/submit)
    submit_res = resolution_client.post(f"/api/disputes/DISP-RES-1/resolution/{new_response_id}/submit")
    assert submit_res.status_code == 200
    sub_data = submit_res.json()
    assert sub_data["status"] == "SUBMITTED"
    assert sub_data["response_id"] == new_response_id

    # 8. Verify Audit Trail records all actions
    audit_res = resolution_client.get("/api/disputes/DISP-RES-1/audit-trail")
    assert audit_res.status_code == 200
    logs = audit_res.json()
    actions = [l["action"] for l in logs]
    assert "RESPONSE_GENERATED" in actions
    assert "RESPONSE_EDITED" in actions
    assert "MERCHANT_APPROVED" in actions
    assert "PAYPAL_SUBMITTED" in actions
