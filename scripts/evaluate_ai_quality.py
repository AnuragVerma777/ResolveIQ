"""Test runner to audit the AI quality across all 5 dispute scenarios."""
import json
import sys
from pathlib import Path
from pprint import pprint

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.ai.classifier import DisputeClassifier
from backend.ai.engine import StructuredGenerator
from backend.ai.evidence_engine import EvidenceIntelligenceEngine
from backend.ai.resolution_engine import ResolutionEngine
from backend.ai.schemas import EvidenceStatus

def run_audit():
    # We test both with mock generator (deterministic fallback/rules) and check prompt/rule consistency
    classifier = DisputeClassifier(generator=None)
    evidence_engine = EvidenceIntelligenceEngine(generator=None)
    resolution_engine = ResolutionEngine(generator=None)

    scenarios = [
        {
            "id": 1,
            "name": "Product Not Received (INR)",
            "dispute": {
                "dispute_id": "PP-D-INR-001",
                "dispute_reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
                "customer_complaint": "I ordered an ergonomic keyboard 3 weeks ago for $189.50 and the package never arrived at my house.",
                "amount": 189.50,
                "currency": "USD",
                "transaction_id": "TXN-849201",
                "order_id": "ORD-77410",
                "merchant_context": "Dispatched via FedEx ground with geo-stamped signature on porch scan.",
            },
            "documents": [
                {
                    "id": "doc-fedex-01",
                    "filename": "FedEx_Proof_Of_Delivery.pdf",
                    "doc_type": "delivery_confirmation",
                    "text": "FEDEX EXPRESS DELIVERY CONFIRMATION RECEIPT\nTracking Number: 789456123012\nDelivered: October 14, 2026 at 14:32:00 PST\nRecipient: Eleanor Vance\nAddress: 742 Evergreen Terrace, Springfield, OR\nStatus: DELIVERED (Front Porch Scan)",
                    "extracted_fields": {
                        "tracking_number": "789456123012",
                        "carrier": "FedEx",
                        "delivery_date": "2026-10-14",
                        "shipment_date": "2026-10-11",
                        "customer_name": "Eleanor Vance",
                        "amount": 189.50,
                    }
                },
                {
                    "id": "doc-inv-01",
                    "filename": "Commercial_Invoice_INV-77410.pdf",
                    "doc_type": "invoice",
                    "text": "TAX INVOICE INV-77410\nOrder ID: ORD-77410\nCustomer: Eleanor Vance\nAmount: $189.50 USD\nTracking: 789456123012",
                    "extracted_fields": {
                        "order_id": "ORD-77410",
                        "amount": 189.50,
                        "currency": "USD",
                        "tracking_number": "789456123012",
                    }
                }
            ],
            "expected_category": "item_not_received",
        },
        {
            "id": 2,
            "name": "Unauthorized Transaction",
            "dispute": {
                "dispute_id": "PP-D-UNAUTH-002",
                "dispute_reason": "UNAUTHORISED",
                "customer_complaint": "I woke up to a charge of $75.25 that I never authorized from my PayPal wallet.",
                "amount": 75.25,
                "currency": "USD",
                "transaction_id": "TXN-391048",
                "order_id": "ORD-88120",
                "merchant_context": "User logged in with 2FA from their registered IP and ordered digital game credits.",
            },
            "documents": [
                {
                    "id": "doc-auth-01",
                    "filename": "Authentication_Audit_Log.txt",
                    "doc_type": "auth_log",
                    "text": "USER LOGIN & 2FA VERIFICATION AUDIT\nUser ID: buyer_9921\nIP Address: 198.51.100.45\n2FA Method: SMS OTP Verified\nTimestamp: 2026-11-01T04:12:00Z\nDevice: iPhone Safari (Known Device)\nOrder ID: ORD-88120",
                    "extracted_fields": {
                        "order_id": "ORD-88120",
                        "transaction_id": "TXN-391048",
                        "amount": 75.25,
                    }
                }
            ],
            "expected_category": "unauthorized_transaction",
        },
        {
            "id": 3,
            "name": "Product Significantly Not As Described (SNAD)",
            "dispute": {
                "dispute_id": "PP-D-SNAD-003",
                "dispute_reason": "NOT_AS_DESCRIBED",
                "customer_complaint": "The monitor arrived with shattered glass and severe display artifacts. It looks defective and unusable.",
                "amount": 450.00,
                "currency": "USD",
                "transaction_id": "TXN-910482",
                "order_id": "ORD-99301",
                "merchant_context": "Tested before dispatch. Warehouse inspection showed pristine condition. Buyer refused to return the unit.",
            },
            "documents": [
                {
                    "id": "doc-qa-01",
                    "filename": "Pre_Shipment_QA_Certificate.pdf",
                    "doc_type": "inspection",
                    "text": "QUALITY ASSURANCE DISPATCH INSPECTION\nSerial Number: MON-4K-98102\nPanel Condition: 100% Functional, Zero Pixel Defects, No Glass Scratches\nInspected By: QA Inspector #4\nDate: 2026-10-25\nOrder ID: ORD-99301",
                    "extracted_fields": {
                        "order_id": "ORD-99301",
                        "amount": 450.00,
                    }
                }
            ],
            "expected_category": "significantly_not_as_described",
        },
        {
            "id": 4,
            "name": "Duplicate Transaction",
            "dispute": {
                "dispute_id": "PP-D-DUP-004",
                "dispute_reason": "DUPLICATE_TRANSACTION",
                "customer_complaint": "I was charged twice $89.00 for the same item on November 2nd.",
                "amount": 89.00,
                "currency": "USD",
                "transaction_id": "TXN-552011",
                "order_id": "ORD-44101",
                "merchant_context": "Buyer actually placed two distinct orders for different colors 4 hours apart.",
            },
            "documents": [
                {
                    "id": "doc-order1-01",
                    "filename": "Invoice_Order_44101.pdf",
                    "doc_type": "invoice",
                    "text": "TAX INVOICE 44101\nOrder ID: ORD-44101\nTime: 10:15 AM Nov 2, 2026\nItem: Smart Hub (Black Edition)\nAmount: $89.00 USD\nTransaction ID: TXN-552011",
                    "extracted_fields": {
                        "order_id": "ORD-44101",
                        "transaction_id": "TXN-552011",
                        "amount": 89.00,
                    }
                },
                {
                    "id": "doc-order2-01",
                    "filename": "Invoice_Order_44102.pdf",
                    "doc_type": "invoice",
                    "text": "TAX INVOICE 44102\nOrder ID: ORD-44102\nTime: 02:30 PM Nov 2, 2026\nItem: Smart Hub (White Edition)\nAmount: $89.00 USD\nTransaction ID: TXN-552012",
                    "extracted_fields": {
                        "order_id": "ORD-44102",
                        "transaction_id": "TXN-552012",
                        "amount": 89.00,
                    }
                }
            ],
            "expected_category": "duplicate_charge",
        },
        {
            "id": 5,
            "name": "Refund-Related Dispute (Credit Not Processed)",
            "dispute": {
                "dispute_id": "PP-D-REFUND-005",
                "dispute_reason": "CREDIT_NOT_PROCESSED",
                "customer_complaint": "I returned the shoes two weeks ago and merchant agreed to refund $120.00 but never sent the refund.",
                "amount": 120.00,
                "currency": "USD",
                "transaction_id": "TXN-773019",
                "order_id": "ORD-66201",
                "merchant_context": "Merchant policy requires return package delivered to warehouse before credit. No package received yet.",
            },
            "documents": [
                {
                    "id": "doc-rma-01",
                    "filename": "Return_Policy_Agreement.pdf",
                    "doc_type": "return_policy",
                    "text": "MERCHANT RETURN & CREDIT POLICY\nSection 4: Returns must be scanned as delivered by the carrier at our fulfillment depot before credit processing.\nRMA Number: RMA-88910\nOrder: ORD-66201",
                    "extracted_fields": {
                        "order_id": "ORD-66201",
                        "amount": 120.00,
                    }
                },
                {
                    "id": "doc-depot-01",
                    "filename": "Warehouse_Inbound_Scan_Log.pdf",
                    "doc_type": "warehouse_log",
                    "text": "DEPOT INBOUND LOG FOR RMA-88910\nOrder: ORD-66201\nStatus: AWAITING_PACKAGE\nCarrier Scans: No inbound delivery recorded to date.\nDate: November 8, 2026",
                    "extracted_fields": {
                        "order_id": "ORD-66201",
                        "amount": 120.00,
                    }
                }
            ],
            "expected_category": "credit_not_processed",
        }
    ]

    for sc in scenarios:
        print(f"\n=======================================================")
        print(f"SCENARIO {sc['id']}: {sc['name']}")
        print(f"=======================================================")
        
        # 1. Classification
        classification = classifier.classify(sc["dispute"], sc["documents"])
        cat_match = classification.dispute_category.value == sc["expected_category"]
        print(f"1. Classification:")
        print(f"   Expected: {sc['expected_category']}")
        print(f"   Actual:   {classification.dispute_category.value} -> {'PASS' if cat_match else 'FAIL'}")
        print(f"   Explanation: {classification.explanation[:100]}...")
        
        # 2. Evidence Matrix
        matrix = evidence_engine.generate_matrix(sc["dispute"], sc["documents"])
        print(f"2. Evidence Matrix & Completeness Score:")
        print(f"   Score: {matrix.completeness_score.overall_score}/100")
        print(f"   Claims Evaluated: {len(matrix.matrix_items)}")
        for idx, item in enumerate(matrix.matrix_items, 1):
            print(f"     [{idx}] Status: {item.evidence_status.value} | Claim: {item.claim[:60]}...")
            if item.missing_information:
                print(f"         Missing: {item.missing_information}")
            if item.contradiction_warnings:
                print(f"         Conflicts: {item.contradiction_warnings}")
        print(f"   Conflict Warnings: {len(matrix.conflict_warnings)}")
        
        # 3. Response Generation
        records = evidence_engine.build_evidence_records(sc["documents"])
        response = resolution_engine.generate_response(sc["dispute"], records, matrix)
        print(f"3. Response Generation:")
        print(f"   Response ID: {response.response_id} (Version: {response.version})")
        print(f"   Verified Facts Count: {len(response.verified_facts)}")
        print(f"   Categorized Claims: {len(response.categorized_claims)}")
        print(f"   Missing Warnings: {len(response.missing_evidence_warnings)}")
        print(f"   Subject Line: {response.subject_line}")
        print(f"   Approval Gate Enforced: approved_by_merchant={response.approved_by_merchant}, required={response.merchant_approval_required}")

if __name__ == "__main__":
    run_audit()
