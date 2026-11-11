"""Automated tests for ResolveIQ Core Evidence Intelligence Engine and Evidence Matrix.

Verifies claim identification, evidence matching, conflict detection,
explainable completeness scoring, anti-fabrication gates, and API endpoints.
"""
import io
import shutil
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.ai.evidence_engine import EvidenceIntelligenceEngine
from backend.ai.schemas import (
    EvidenceMatrixReport,
    EvidenceStatus,
    StructuredEvidenceRecord,
)
from backend.config import Settings, get_settings
from backend.main import app
from tests.test_document_pipeline import create_dummy_pdf


# =====================================================================
# 1. Evidence Record Conversion Tests
# =====================================================================

def test_convert_documents_to_structured_evidence_records():
    engine = EvidenceIntelligenceEngine()
    docs = [
        {
            "id": "doc-inv-1",
            "name": "invoice_889.pdf",
            "raw_text": "Invoice #889\nOrder ID: ORD-5544\nTotal: $149.50 USD\nItem: Wireless Headphones",
            "doc_type": "invoice",
            "extracted_fields": {
                "order_id": "ORD-5544",
                "amount": 149.50,
                "currency": "USD",
                "product_or_service": "Wireless Headphones",
            },
        },
        {
            "id": "doc-trk-1",
            "name": "fedex_scan.pdf",
            "raw_text": "FedEx Tracking 940011189922\nDelivered: 2026-05-03\nShipped: 2026-04-30\nSigned by resident",
            "doc_type": "delivery_confirmation",
            "extracted_fields": {
                "tracking_number": "940011189922",
                "delivery_date": "2026-05-03",
                "shipment_date": "2026-04-30",
            },
        },
    ]

    records = engine.build_evidence_records(docs)
    assert len(records) == 2

    r1 = records[0]
    assert r1.evidence_id == "doc-inv-1"
    assert r1.source_document == "invoice_889.pdf"
    assert r1.doc_type == "invoice"
    assert r1.order_id == "ORD-5544"
    assert r1.amount == 149.50
    assert r1.currency == "USD"
    assert any("ORD-5544" in f for f in r1.key_facts)

    r2 = records[1]
    assert r2.evidence_id == "doc-trk-1"
    assert r2.tracking_number == "940011189922"
    assert r2.delivery_date == "2026-05-03"
    assert r2.shipment_date == "2026-04-30"


# =====================================================================
# 2. Claim Identification & Matching Tests
# =====================================================================

def test_identify_claims_from_dispute():
    engine = EvidenceIntelligenceEngine()
    dispute = {
        "dispute_reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        "customer_complaint": "I ordered headphones but I never received my package at my door.",
        "merchant_context": "Dispatched via FedEx Express on April 30.",
    }

    claims = engine.identify_claims(dispute)
    assert len(claims) >= 2

    # Reason claim
    assert any(c["claim_type"] == "paypal_reason" for c in claims)
    # Non-receipt claim
    assert any("never delivered" in c["claim"].lower() or "not received" in c["claim"].lower() for c in claims)
    # Merchant context claim
    assert any(c["claim_type"] == "merchant_position" for c in claims)


def test_evidence_matching_supported_status():
    """Carrier tracking scan verifies delivery, setting status to Supported."""
    engine = EvidenceIntelligenceEngine()
    dispute = {
        "dispute_id": "PP-D-101",
        "dispute_reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        "customer_complaint": "Buyer states parcel was never received.",
        "transaction_details": {"amount": 149.50, "currency": "USD"},
    }
    docs = [
        {
            "id": "doc-fedex",
            "name": "fedex_tracking.pdf",
            "raw_text": "Tracking #940011189922: Delivered May 3 to porch.",
            "doc_type": "delivery_confirmation",
            "extracted_fields": {
                "tracking_number": "940011189922",
                "delivery_date": "2026-05-03",
                "amount": 149.50,
            },
        }
    ]

    report = engine.generate_matrix(dispute, docs)
    assert len(report.matrix_items) > 0

    delivery_item = next(
        item for item in report.matrix_items
        if "delivered" in item.claim.lower() or "received" in item.claim.lower()
    )
    assert delivery_item.evidence_status == EvidenceStatus.SUPPORTED
    assert "fedex_tracking.pdf" in delivery_item.source_documents
    assert "directly disproving" in delivery_item.evidence_relevance_explanation.lower() or "establishes" in delivery_item.evidence_relevance_explanation.lower()
    assert len(delivery_item.supporting_evidence) > 0


def test_evidence_matching_partially_supported_and_unsupported():
    """Dispatch notice without final delivery scan yields Partially Supported."""
    engine = EvidenceIntelligenceEngine()
    dispute = {
        "dispute_id": "PP-D-102",
        "dispute_reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        "customer_complaint": "Item was never received.",
    }
    # Only dispatch document, no delivery date
    docs = [
        {
            "id": "doc-dispatch",
            "name": "shipping_manifest.pdf",
            "raw_text": "Manifest: Dispatched to Carrier. In transit.",
            "doc_type": "shipping_receipt",
            "extracted_fields": {"tracking_number": "1Z999999"},
        }
    ]

    report = engine.generate_matrix(dispute, docs)
    delivery_item = next(
        item for item in report.matrix_items
        if "delivered" in item.claim.lower() or "received" in item.claim.lower()
    )

    assert delivery_item.evidence_status == EvidenceStatus.PARTIALLY_SUPPORTED
    assert len(delivery_item.missing_information) > 0
    assert "delivery" in delivery_item.missing_information[0].lower()


def test_unsupported_claim_when_no_documents_exist():
    engine = EvidenceIntelligenceEngine()
    dispute = {
        "dispute_id": "PP-D-103",
        "dispute_reason": "UNAUTHORIZED_TRANSACTION",
        "customer_complaint": "I did not authorize this charge.",
    }

    report = engine.generate_matrix(dispute, [])
    auth_item = next(
        item for item in report.matrix_items
        if "unauthorized" in item.claim.lower()
    )

    assert auth_item.evidence_status == EvidenceStatus.UNSUPPORTED
    assert len(auth_item.missing_information) > 0
    assert len(report.unsupported_factual_claims) > 0


# =====================================================================
# 3. Conflict and Contradiction Detection Tests
# =====================================================================

def test_detect_conflicting_amounts():
    engine = EvidenceIntelligenceEngine()
    dispute = {
        "dispute_id": "PP-D-201",
        "transaction_details": {"amount": 250.00},
    }
    records = [
        StructuredEvidenceRecord(
            evidence_id="e1",
            source_document="invoice.pdf",
            amount=180.00,
        )
    ]

    conflicts = engine.detect_conflicts(dispute, records)
    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == "amount_mismatch"
    assert conflicts[0].disputed_value == "250.00"
    assert conflicts[0].evidence_value == "180.00"
    assert "invoice.pdf" in conflicts[0].explanation


def test_detect_conflicting_order_ids():
    engine = EvidenceIntelligenceEngine()
    dispute = {
        "dispute_id": "PP-D-202",
        "order_id": "ORD-1111",
    }
    records = [
        StructuredEvidenceRecord(
            evidence_id="e1",
            source_document="packing_slip.pdf",
            order_id="ORD-9999",
        )
    ]

    conflicts = engine.detect_conflicts(dispute, records)
    assert any(c.conflict_type == "order_id_mismatch" for c in conflicts)


def test_detect_conflicting_date_sequence():
    """Delivery date precedes shipment date."""
    engine = EvidenceIntelligenceEngine()
    dispute = {"dispute_id": "PP-D-203"}
    records = [
        StructuredEvidenceRecord(
            evidence_id="e1",
            source_document="carrier_scan.pdf",
            shipment_date="2026-05-10",
            delivery_date="2026-05-02",  # Precedes shipment!
        )
    ]

    conflicts = engine.detect_conflicts(dispute, records)
    assert any(c.conflict_type == "date_mismatch" for c in conflicts)


def test_detect_conflicting_tracking_numbers():
    engine = EvidenceIntelligenceEngine()
    dispute = {"dispute_id": "PP-D-204"}
    records = [
        StructuredEvidenceRecord(evidence_id="e1", source_document="doc1.pdf", tracking_number="TRACK-A"),
        StructuredEvidenceRecord(evidence_id="e2", source_document="doc2.pdf", tracking_number="TRACK-B"),
    ]

    conflicts = engine.detect_conflicts(dispute, records)
    assert any(c.conflict_type == "tracking_mismatch" for c in conflicts)


# =====================================================================
# 4. Explainable Completeness Score & Anti-Fabrication Tests
# =====================================================================

def test_explainable_completeness_score():
    engine = EvidenceIntelligenceEngine()
    dispute = {
        "dispute_id": "PP-D-301",
        "dispute_reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        "customer_complaint": "Never received item.",
        "transaction_details": {"amount": 120.00},
    }
    docs = [
        {
            "id": "doc1",
            "name": "invoice.pdf",
            "raw_text": "Invoice #12 Total: $120.00 Order: ORD-12",
            "doc_type": "invoice",
            "extracted_fields": {"amount": 120.00, "order_id": "ORD-12"},
        },
        {
            "id": "doc2",
            "name": "fedex.pdf",
            "raw_text": "Delivered May 3 Tracking #9400123",
            "doc_type": "delivery_confirmation",
            "extracted_fields": {"tracking_number": "9400123", "delivery_date": "2026-05-03"},
        },
    ]

    report = engine.generate_matrix(dispute, docs)
    score_breakdown = report.completeness_score

    assert 0 <= score_breakdown.overall_score <= 100
    assert score_breakdown.claim_coverage_points > 0
    assert score_breakdown.core_evidence_points > 0
    assert score_breakdown.data_consistency_points == 20  # No conflicts!
    assert "Score:" in score_breakdown.explanation
    assert "not an invented probability of winning" in score_breakdown.disclaimer.lower()


def test_missing_evidence_is_not_treated_as_proof_of_negative():
    """Verify that absent evidence leaves claim unsupported, but does NOT assert item was stolen/not sent."""
    engine = EvidenceIntelligenceEngine()
    dispute = {
        "dispute_id": "PP-D-302",
        "customer_complaint": "I never got the package.",
    }

    report = engine.generate_matrix(dispute, [])
    assert report.completeness_score.overall_score < 30
    # Engine must not fabricate a conclusion that merchant lied
    for item in report.matrix_items:
        assert item.evidence_status == EvidenceStatus.UNSUPPORTED
        assert "no shipping receipts" in item.evidence_relevance_explanation.lower() or "no supporting" in item.evidence_relevance_explanation.lower()


# =====================================================================
# 5. FastAPI Endpoints Integration Tests
# =====================================================================

@pytest.fixture
def api_client():
    temp_dir = Path("test_scratch_evidence")
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


def test_api_generate_and_get_evidence_matrix(api_client):
    # 1. Upload a PDF evidence document
    pdf_bytes = create_dummy_pdf("Tracking Number: 940011189922\nDelivered: 2026-05-03\nOrder ID: ORD-4455\nTotal: $89.00 USD")
    files = {"file": ("tracking.pdf", pdf_bytes, "application/pdf")}
    up_res = api_client.post("/api/documents/upload", files=files, data={"dispute_id": "DISP-MATRIX-1", "doc_type": "delivery_confirmation"})
    assert up_res.status_code == 201

    # 2. Generate Evidence Matrix via API
    matrix_req = {
        "dispute_reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        "customer_complaint": "Buyer states parcel never arrived.",
        "transaction_details": {"amount": 89.00, "currency": "USD"},
        "merchant_context": "Shipped with tracking.",
    }
    post_res = api_client.post("/api/disputes/DISP-MATRIX-1/evidence-matrix", json=matrix_req)
    assert post_res.status_code == 200
    data = post_res.json()

    assert data["dispute_id"] == "DISP-MATRIX-1"
    assert len(data["matrix_items"]) > 0
    assert len(data["evidence_records"]) == 1
    assert "completeness_score" in data
    assert "overall_score" in data["completeness_score"]
    assert data["completeness_score"]["overall_score"] > 50

    # 3. Retrieve Evidence Matrix via GET
    get_res = api_client.get("/api/disputes/DISP-MATRIX-1/evidence-matrix")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["dispute_id"] == "DISP-MATRIX-1"
    assert len(get_data["matrix_items"]) == len(data["matrix_items"])
