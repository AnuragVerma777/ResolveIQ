"""Automated tests evaluating the 5 dispute scenarios against the 9 AI quality requirements."""
import pytest
from backend.ai.classifier import DisputeClassifier
from backend.ai.evidence_engine import EvidenceIntelligenceEngine
from backend.ai.resolution_engine import ResolutionEngine
from backend.ai.schemas import (
    DisputeCategory,
    EvidenceStatus,
    FactSectionType,
)


@pytest.fixture
def engines():
    return {
        "classifier": DisputeClassifier(generator=None),
        "evidence": EvidenceIntelligenceEngine(generator=None),
        "resolution": ResolutionEngine(generator=None),
    }


# =====================================================================
# Scenario 1: Product Not Received (INR)
# =====================================================================
def test_scenario_1_product_not_received(engines):
    dispute = {
        "dispute_id": "PP-D-INR-001",
        "dispute_reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        "customer_complaint": "I ordered an ergonomic keyboard 3 weeks ago for $189.50 and the package never arrived at my house.",
        "amount": 189.50,
        "currency": "USD",
        "transaction_id": "TXN-849201",
        "order_id": "ORD-77410",
        "merchant_context": "Dispatched via FedEx ground with geo-stamped signature on porch scan.",
    }
    docs = [
        {
            "id": "doc-fedex-01",
            "filename": "FedEx_Proof_Of_Delivery.pdf",
            "doc_type": "delivery_confirmation",
            "text": "FEDEX DELIVERY RECEIPT Tracking: 789456123012 Delivered: 2026-10-14 Status: DELIVERED",
            "extracted_fields": {
                "tracking_number": "789456123012",
                "carrier": "FedEx",
                "delivery_date": "2026-10-14",
                "shipment_date": "2026-10-11",
                "amount": 189.50,
            },
        },
        {
            "id": "doc-inv-01",
            "filename": "Invoice_INV-77410.pdf",
            "doc_type": "invoice",
            "text": "TAX INVOICE Order: ORD-77410 Amount: $189.50 USD Tracking: 789456123012",
            "extracted_fields": {
                "order_id": "ORD-77410",
                "amount": 189.50,
                "currency": "USD",
                "tracking_number": "789456123012",
            },
        },
    ]

    # 1. Classification
    classification = engines["classifier"].classify(dispute, docs)
    assert classification.dispute_category == DisputeCategory.ITEM_NOT_RECEIVED

    # 2. Evidence Matrix
    matrix = engines["evidence"].generate_matrix(dispute, docs)
    assert matrix.completeness_score.overall_score >= 70
    assert any(item.evidence_status == EvidenceStatus.SUPPORTED for item in matrix.matrix_items)

    # 3. Response Generation
    records = engines["evidence"].build_evidence_records(docs)
    response = engines["resolution"].generate_response(dispute, records, matrix)
    assert len(response.verified_facts) >= 2
    assert response.merchant_approval_required is True
    assert response.approved_by_merchant is False
    assert "guarantee" not in response.official_response_letter.lower()
    engines["resolution"].validate_claims_against_evidence(response.categorized_claims, records)


# =====================================================================
# Scenario 2: Unauthorized Transaction (supports UNAUTHORISED spelling)
# =====================================================================
def test_scenario_2_unauthorized_transaction(engines):
    dispute = {
        "dispute_id": "PP-D-UNAUTH-002",
        "dispute_reason": "UNAUTHORISED",  # UK/EU PayPal spelling
        "customer_complaint": "I woke up to a charge of $75.25 that I never authorized from my PayPal wallet.",
        "amount": 75.25,
        "currency": "USD",
        "transaction_id": "TXN-391048",
        "order_id": "ORD-88120",
        "merchant_context": "User logged in with 2FA from their registered IP and ordered digital game credits.",
    }
    docs = [
        {
            "id": "doc-auth-01",
            "filename": "Authentication_Audit_Log.txt",
            "doc_type": "auth_log",
            "text": "USER LOGIN 2FA VERIFICATION User: buyer_9921 IP: 198.51.100.45 2FA: SMS OTP Verified Time: 2026-11-01T04:12:00Z",
            "extracted_fields": {
                "order_id": "ORD-88120",
                "transaction_id": "TXN-391048",
                "amount": 75.25,
            },
        }
    ]

    classification = engines["classifier"].classify(dispute, docs)
    assert classification.dispute_category == DisputeCategory.UNAUTHORIZED_TRANSACTION

    matrix = engines["evidence"].generate_matrix(dispute, docs)
    records = engines["evidence"].build_evidence_records(docs)
    response = engines["resolution"].generate_response(dispute, records, matrix)

    assert any("2fa" in r.lower() or "seller protection" in r.lower() for r in response.ai_recommendations)
    engines["resolution"].validate_claims_against_evidence(response.categorized_claims, records)


# =====================================================================
# Scenario 3: Product Significantly Not As Described (SNAD)
# =====================================================================
def test_scenario_3_significantly_not_as_described(engines):
    dispute = {
        "dispute_id": "PP-D-SNAD-003",
        "dispute_reason": "NOT_AS_DESCRIBED",
        "customer_complaint": "The monitor arrived with shattered glass and severe display artifacts. It is defective and unusable.",
        "amount": 450.00,
        "currency": "USD",
        "transaction_id": "TXN-910482",
        "order_id": "ORD-99301",
        "merchant_context": "Tested before dispatch. Warehouse inspection showed pristine condition. Buyer refused to return the unit.",
    }
    docs = [
        {
            "id": "doc-qa-01",
            "filename": "Pre_Shipment_QA_Certificate.pdf",
            "doc_type": "inspection",
            "text": "QUALITY ASSURANCE DISPATCH INSPECTION Serial: MON-4K-98102 Panel: 100% Functional Date: 2026-10-25",
            "extracted_fields": {
                "order_id": "ORD-99301",
                "amount": 450.00,
            },
        }
    ]

    classification = engines["classifier"].classify(dispute, docs)
    assert classification.dispute_category == DisputeCategory.SIGNIFICANTLY_NOT_AS_DESCRIBED

    matrix = engines["evidence"].generate_matrix(dispute, docs)
    # Check that missing documentation is properly identified
    damaged_claim = next((item for item in matrix.matrix_items if "damaged" in item.claim.lower() or "described" in item.claim.lower()), None)
    assert damaged_claim is not None
    assert len(damaged_claim.missing_information) > 0


# =====================================================================
# Scenario 4: Duplicate Transaction
# =====================================================================
def test_scenario_4_duplicate_transaction(engines):
    dispute = {
        "dispute_id": "PP-D-DUP-004",
        "dispute_reason": "DUPLICATE_TRANSACTION",
        "customer_complaint": "I was charged twice $89.00 for the same item on November 2nd.",
        "amount": 89.00,
        "currency": "USD",
        "transaction_id": "TXN-552011",
        "order_id": "ORD-44101",
        "merchant_context": "Buyer actually placed two distinct orders for different colors 4 hours apart.",
    }
    docs = [
        {
            "id": "doc-order1-01",
            "filename": "Invoice_Order_44101.pdf",
            "doc_type": "invoice",
            "text": "TAX INVOICE 44101 Order ID: ORD-44101 Time: 10:15 AM Item: Smart Hub Black Amount: $89.00 USD Txn: TXN-552011",
            "extracted_fields": {
                "order_id": "ORD-44101",
                "transaction_id": "TXN-552011",
                "amount": 89.00,
            },
        },
        {
            "id": "doc-order2-01",
            "filename": "Invoice_Order_44102.pdf",
            "doc_type": "invoice",
            "text": "TAX INVOICE 44102 Order ID: ORD-44102 Time: 02:30 PM Item: Smart Hub White Amount: $89.00 USD Txn: TXN-552012",
            "extracted_fields": {
                "order_id": "ORD-44102",
                "transaction_id": "TXN-552012",
                "amount": 89.00,
            },
        },
    ]

    classification = engines["classifier"].classify(dispute, docs)
    assert classification.dispute_category == DisputeCategory.DUPLICATE_CHARGE

    matrix = engines["evidence"].generate_matrix(dispute, docs)
    dup_claim = next((item for item in matrix.matrix_items if "duplicate" in item.claim.lower() or "billing" in item.claim.lower()), None)
    assert dup_claim is not None
    # Multiple distinct orders support the defense that this wasn't a duplicate billing glitch
    assert dup_claim.evidence_status == EvidenceStatus.SUPPORTED


# =====================================================================
# Scenario 5: Refund-Related Dispute (Credit Not Processed)
# =====================================================================
def test_scenario_5_refund_credit_not_processed(engines):
    dispute = {
        "dispute_id": "PP-D-REFUND-005",
        "dispute_reason": "CREDIT_NOT_PROCESSED",
        "customer_complaint": "I returned the shoes two weeks ago and merchant agreed to refund $120.00 but never sent the refund.",
        "amount": 120.00,
        "currency": "USD",
        "transaction_id": "TXN-773019",
        "order_id": "ORD-66201",
        "merchant_context": "Merchant policy requires return package delivered to warehouse before credit. No package received yet.",
    }
    docs = [
        {
            "id": "doc-rma-01",
            "filename": "Return_Policy_Agreement.pdf",
            "doc_type": "return_policy",
            "text": "MERCHANT RETURN POLICY Returns must be delivered by carrier to warehouse before credit. RMA: RMA-88910 Order: ORD-66201",
            "extracted_fields": {
                "order_id": "ORD-66201",
                "amount": 120.00,
            },
        },
        {
            "id": "doc-depot-01",
            "filename": "Warehouse_Inbound_Scan_Log.pdf",
            "doc_type": "warehouse_log",
            "text": "DEPOT INBOUND LOG RMA-88910 Order: ORD-66201 Status: AWAITING_PACKAGE No inbound delivery recorded to date.",
            "extracted_fields": {
                "order_id": "ORD-66201",
                "amount": 120.00,
            },
        },
    ]

    classification = engines["classifier"].classify(dispute, docs)
    assert classification.dispute_category == DisputeCategory.CREDIT_NOT_PROCESSED

    matrix = engines["evidence"].generate_matrix(dispute, docs)
    refund_claim = next((item for item in matrix.matrix_items if "refund" in item.claim.lower() or "credit" in item.claim.lower()), None)
    assert refund_claim is not None
    assert len(refund_claim.missing_information) > 0
    assert any("return tracking" in m.lower() for m in refund_claim.missing_information)


# =====================================================================
# Quality Requirements Guardrails Verification
# =====================================================================
def test_anti_hallucination_and_approval_invariants(engines):
    # Requirement 1 & 7: Zero fabricated tracking or records
    dispute = {
        "dispute_id": "PP-D-EMPTY-006",
        "dispute_reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        "customer_complaint": "I never got it.",
        "amount": 50.00,
        "currency": "USD",
    }
    # No documents provided
    matrix = engines["evidence"].generate_matrix(dispute, [])
    records = engines["evidence"].build_evidence_records([])
    response = engines["resolution"].generate_response(dispute, records, matrix)

    # Must contain zero verified facts
    assert len(response.verified_facts) == 0
    # Must explicitly flag missing carrier proof
    assert len(response.missing_evidence_warnings) > 0
    # Requirement 9: Merchant approval must remain mandatory
    assert response.merchant_approval_required is True
    assert response.approved_by_merchant is False
