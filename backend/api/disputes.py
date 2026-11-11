"""Dispute classification, management, and intelligence endpoints."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.ai.classifier import DisputeClassifier
from backend.ai.engine import GeminiGenerator
from backend.ai.schemas import (
    DisputeClassification,
    DisputeClassificationRequest,
    DocumentMetadata,
    DocumentType,
    ExtractedDocumentFields,
    ProcessingStatus,
)
from backend.config import Settings, get_settings
from backend.db import Database
from backend.security import RateLimit, get_current_merchant_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/disputes", tags=["disputes"])


def get_db(settings: Settings = Depends(get_settings)) -> Database:
    return Database(settings.db_path)


class DisputeCreateRequest(BaseModel):
    dispute_id: str = Field(..., min_length=1, max_length=120)
    reason: str = Field(..., min_length=1, max_length=255)
    customer_complaint: str = Field(default="", max_length=10000)
    transaction_id: str = Field(default="", max_length=120)
    amount: float = Field(default=0.0, ge=0.0)
    currency: str = Field(default="USD", max_length=10)
    merchant_context: str = Field(default="", max_length=10000)


@router.post("/classify", response_model=DisputeClassification)
def classify_dispute(
    req: DisputeClassificationRequest,
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_db),
    merchant_id: str = Depends(get_current_merchant_id),
    _rate_limit: None = Depends(RateLimit(max_requests=40, window_seconds=60.0, scope="dispute_classification")),
):
    """Classify a PayPal dispute using Gemini AI and attached evidence documents.

    Extracts key facts, identifies contradictions and missing information,
    provides recommended actions, assesses confidence, and logs audit record.
    Enforces that original PayPal reason is preserved and no dispute outcome is guaranteed.
    """
    # 1. Fetch relevant evidence documents
    documents: list[dict[str, Any]] = []

    # Get documents explicitly listed
    if req.document_ids:
        for doc_id in req.document_ids:
            doc = db.get_document(doc_id)
            if doc:
                documents.append(doc)

    # Also automatically include any documents linked to this dispute_id in DB
    if req.dispute_id:
        existing_docs = db.list_documents(dispute_id=req.dispute_id)
        known_ids = {d["id"] for d in documents}
        for d in existing_docs:
            if d["id"] not in known_ids:
                documents.append(d)

    # 2. Instantiate generator
    if settings.gemini_api_key:
        generator = GeminiGenerator(settings.gemini_api_key, settings.gemini_model)
    else:
        # Fallback fake generator that triggers the robust fallback classifier
        class DummyGenerator:
            def generate(self, prompt: str, schema: type):
                raise RuntimeError("GEMINI_API_KEY is not configured on the backend")

        generator = DummyGenerator()  # type: ignore

    classifier = DisputeClassifier(generator)

    dispute_payload = {
        "dispute_id": req.dispute_id,
        "dispute_reason": req.dispute_reason,
        "customer_complaint": req.customer_complaint,
        "transaction_details": req.transaction_details,
        "order_information": req.order_information,
        "merchant_context": req.merchant_context,
    }

    classification = classifier.classify(dispute_payload, documents)

    # 3. Store dispute and classification in DB
    db.save_dispute({
        "dispute_id": req.dispute_id,
        "reason": req.dispute_reason,
        "customer_complaint": req.customer_complaint,
        "transaction_id": req.transaction_details.get("transaction_id", ""),
        "amount": req.transaction_details.get("amount", 0.0),
        "currency": req.transaction_details.get("currency", "USD"),
        "merchant_context": req.merchant_context,
    })

    classification_record = {
        "id": uuid4().hex,
        "dispute_id": req.dispute_id,
        "original_paypal_reason": classification.original_paypal_reason,
        "dispute_category": classification.dispute_category.value,
        "explanation": classification.explanation,
        "confidence_level": classification.confidence.level.value,
        "confidence_score": classification.confidence.score,
        "confidence_explanation": classification.confidence.explanation,
        "key_facts": classification.key_facts,
        "relevant_evidence": [item.model_dump() for item in classification.relevant_evidence],
        "missing_information": classification.missing_information,
        "potential_contradictions": classification.potential_contradictions,
        "recommended_next_actions": classification.recommended_next_actions,
        "raw_response": classification.model_dump(),
    }
    db.save_classification(classification_record)

    # Record AI analysis in audit history
    db.log_audit(
        dispute_id=req.dispute_id,
        action="AI_ANALYSIS_GENERATED",
        actor="gemini_classifier" if settings.gemini_api_key else "rule_classifier",
        details={
            "dispute_category": classification.dispute_category.value,
            "confidence_level": classification.confidence.level.value,
            "confidence_score": classification.confidence.score,
            "key_facts_count": len(classification.key_facts),
            "relevant_evidence_count": len(classification.relevant_evidence),
        },
    )

    return classification


@router.get("/{dispute_id}/documents", response_model=list[DocumentMetadata])
def get_dispute_documents(
    dispute_id: str,
    db: Database = Depends(get_db),
):
    """Retrieve all evidence documents attached to a dispute."""
    docs = db.list_documents(dispute_id=dispute_id)
    return [
        DocumentMetadata(
            id=d["id"],
            dispute_id=d.get("dispute_id"),
            filename=d["filename"],
            file_size=d["file_size"],
            content_type=d["content_type"],
            doc_type=DocumentType(d.get("doc_type", "other")),
            status=ProcessingStatus(d.get("status", "PENDING")),
            error_message=d.get("error_message"),
            raw_text=d.get("raw_text"),
            extracted_fields=ExtractedDocumentFields.model_validate(d["extracted_fields"])
            if d.get("extracted_fields") else None,
            created_at=d["created_at"],
            updated_at=d["updated_at"],
        )
        for d in docs
    ]


@router.get("/{dispute_id}")
def get_dispute_details(
    dispute_id: str,
    db: Database = Depends(get_db),
):
    """Get complete dispute investigation details including latest AI classification."""
    dispute = db.get_dispute(dispute_id)
    classification = db.get_latest_classification(dispute_id)
    documents = db.list_documents(dispute_id=dispute_id)

    return {
        "dispute_id": dispute_id,
        "dispute": dispute,
        "latest_classification": classification,
        "document_count": len(documents),
        "documents": [
            {
                "id": d["id"],
                "filename": d["filename"],
                "file_size": d["file_size"],
                "doc_type": d["doc_type"],
                "status": d["status"],
                "extracted_fields": d.get("extracted_fields"),
            }
            for d in documents
        ],
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_dispute(
    req: DisputeCreateRequest,
    db: Database = Depends(get_db),
    merchant_id: str = Depends(get_current_merchant_id),
):
    """Create or update a dispute record in ResolveIQ with audit history."""
    existing = db.get_dispute(req.dispute_id)
    saved = db.save_dispute(req.model_dump())
    db.log_audit(
        dispute_id=req.dispute_id,
        action="DISPUTE_UPDATED" if existing else "DISPUTE_CREATED",
        actor=merchant_id,
        details={
            "reason": req.reason,
            "amount": req.amount,
            "currency": req.currency,
        },
    )
    return saved


@router.get("")
def list_disputes(
    db: Database = Depends(get_db),
):
    """List all registered disputes."""
    with db._conn() as conn:
        rows = conn.execute("SELECT * FROM disputes ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


# =====================================================================
# Evidence Intelligence Engine & Evidence Matrix Endpoints
# =====================================================================

from backend.ai.evidence_engine import EvidenceIntelligenceEngine
from backend.ai.schemas import EvidenceMatrixReport


class EvidenceMatrixRequest(BaseModel):
    dispute_reason: str | None = None
    customer_complaint: str | None = None
    transaction_details: dict[str, Any] = Field(default_factory=dict)
    merchant_context: str | None = None
    document_ids: list[str] = Field(default_factory=list)


@router.post("/{dispute_id}/evidence-matrix", response_model=EvidenceMatrixReport)
def generate_evidence_matrix(
    dispute_id: str,
    req: EvidenceMatrixRequest | None = None,
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_db),
):
    """Generate the complete Evidence Intelligence Matrix for a dispute.

    Converts documents into structured evidence records, decomposes claims,
    matches evidence to each claim with relevance explanations, flags conflicting
    dates/amounts/IDs, and calculates an explainable completeness score.
    """
    dispute_record = db.get_dispute(dispute_id) or {}
    req = req or EvidenceMatrixRequest()

    reason = req.dispute_reason or dispute_record.get("reason", "UNKNOWN_REASON")
    complaint = req.customer_complaint or dispute_record.get("customer_complaint", "")
    merchant_ctx = req.merchant_context or dispute_record.get("merchant_context", "")
    tx_details = req.transaction_details or {
        "transaction_id": dispute_record.get("transaction_id", ""),
        "amount": dispute_record.get("amount", 0.0),
        "currency": dispute_record.get("currency", "USD"),
    }

    # Fetch associated documents
    documents: list[dict[str, Any]] = []
    if req.document_ids:
        for doc_id in req.document_ids:
            doc = db.get_document(doc_id)
            if doc:
                documents.append(doc)

    # Also automatically include documents in DB associated with dispute_id
    existing_docs = db.list_documents(dispute_id=dispute_id)
    known_ids = {d["id"] for d in documents}
    for d in existing_docs:
        if d["id"] not in known_ids:
            documents.append(d)

    engine = EvidenceIntelligenceEngine()
    dispute_payload = {
        "dispute_id": dispute_id,
        "dispute_reason": reason,
        "customer_complaint": complaint,
        "transaction_details": tx_details,
        "merchant_context": merchant_ctx,
    }

    report = engine.generate_matrix(dispute_payload, documents)

    # Save to database and log audit event
    db.save_evidence_matrix(report.model_dump())
    db.log_audit(
        dispute_id=dispute_id,
        action="EVIDENCE_MATRIX_GENERATED",
        actor="evidence_engine",
        details={
            "completeness_score": report.completeness_score.overall_score,
            "items_count": len(report.matrix_items),
            "conflict_warnings_count": len(report.conflict_warnings),
        },
    )
    return report


@router.get("/{dispute_id}/evidence-matrix", response_model=EvidenceMatrixReport)
def get_evidence_matrix(
    dispute_id: str,
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_db),
):
    """Retrieve the latest Evidence Intelligence Matrix for a dispute."""
    stored = db.get_latest_evidence_matrix(dispute_id)
    if stored and stored.get("matrix_report"):
        return EvidenceMatrixReport.model_validate(stored["matrix_report"])

    # If no report generated yet, generate one on the fly
    return generate_evidence_matrix(dispute_id, None, settings, db)


@router.post("/{dispute_id}/seed-sample-evidence")
def seed_sample_evidence_for_dispute(
    dispute_id: str,
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_db),
    merchant_id: str = Depends(get_current_merchant_id),
):
    """Seed verified sample evidence records tailored to the specific dispute scenario
    (INR, SNAD, Unauthorized, Duplicate, Refund) for judges to test with 1 click.
    """
    now = datetime.now(timezone.utc).isoformat()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    created_docs = []

    if dispute_id == "PP-D-910482":
        # SNAD Scenario
        doc1_id = f"demo-spec-{dispute_id[:8]}"
        doc1_filename = "Product_Specification_SKU-990-PRO.txt"
        doc1_content = (
            "====================================================\n"
            "TECHCRAFT AUDIO — OFFICIAL PRODUCT SPECIFICATION SHEET\n"
            "====================================================\n"
            "Model Name      : Studio Master Reference Audio Monitor Pair\n"
            "SKU Code        : SKU-990-PRO (Pro Edition)\n"
            "Components      : 2x Active Nearfield Monitors, 1x Wireless RF Dongle\n"
            "Packaging Note  : Wireless RF Dongle is securely housed under base styrofoam tray.\n"
            "Serial Number   : SN-TC-990-4821\n"
            "Quality QC Sign : Passed (Factory Sealed, Tamper-Evident Seal)\n"
            "====================================================\n"
        )
        doc1_path = upload_dir / f"{doc1_id}_{doc1_filename}"
        doc1_path.write_text(doc1_content, encoding="utf-8")
        fields1 = {
            "sku": "SKU-990-PRO",
            "model": "Studio Master Reference Audio Monitor Pair",
            "included_components": "2x Monitors, 1x Wireless Dongle",
            "dongle_location": "Under base styrofoam tray",
            "qc_status": "Passed Factory Inspection",
        }
        d1 = db.save_document({
            "id": doc1_id,
            "dispute_id": dispute_id,
            "filename": doc1_filename,
            "stored_path": str(doc1_path),
            "file_size": len(doc1_content.encode("utf-8")),
            "content_type": "text/plain",
            "doc_type": "specification",
            "status": "COMPLETED",
            "raw_text": doc1_content,
            "extracted_fields": fields1,
        })
        created_docs.append(d1)

        doc2_id = f"demo-invoice-{dispute_id[:8]}"
        doc2_filename = "Invoice_SKU990_MarcusVance.txt"
        doc2_content = (
            "====================================================\n"
            "TECHCRAFT AUDIO INC. — COMMERCIAL INVOICE\n"
            "====================================================\n"
            "Invoice Number  : INV-99042\n"
            "Purchase Date   : October 18, 2026\n"
            "Buyer Name      : Marcus Aurelius Vance\n"
            "Transaction ID  : 8UU1029384756102\n"
            "Product Ordered : Studio Master Reference Audio Monitor Pair (SKU-990-PRO)\n"
            "Amount Charged  : $450.00 USD\n"
            "Fulfillment     : Dispatched factory sealed with complete accessories.\n"
            "====================================================\n"
        )
        doc2_path = upload_dir / f"{doc2_id}_{doc2_filename}"
        doc2_path.write_text(doc2_content, encoding="utf-8")
        fields2 = {
            "invoice_number": "INV-99042",
            "transaction_id": "8UU1029384756102",
            "customer_name": "Marcus Aurelius Vance",
            "amount": 450.00,
            "currency": "USD",
            "product_or_service": "Studio Master Reference Audio Monitor Pair",
        }
        d2 = db.save_document({
            "id": doc2_id,
            "dispute_id": dispute_id,
            "filename": doc2_filename,
            "stored_path": str(doc2_path),
            "file_size": len(doc2_content.encode("utf-8")),
            "content_type": "text/plain",
            "doc_type": "invoice",
            "status": "COMPLETED",
            "raw_text": doc2_content,
            "extracted_fields": fields2,
        })
        created_docs.append(d2)

    elif dispute_id == "PP-D-739104":
        # Unauthorized / Fraud Scenario
        doc1_id = f"demo-auth-{dispute_id[:8]}"
        doc1_filename = "3DSecure_Authentication_Audit_Log.txt"
        doc1_content = (
            "====================================================\n"
            "PAYPAL 3D SECURE & RISK AUTHENTICATION RECORD\n"
            "====================================================\n"
            "Cardholder Name : Sarah Connor\n"
            "Cardholder Email: sarah.c@skytech.net\n"
            "Transaction ID  : 9JJ2837461928374\n"
            "Authentication  : 3D Secure v2.2 (SCA Strong Customer Authentication)\n"
            "ECI Status      : 05 (Fully Authenticated by Cardholder Issuer)\n"
            "Device Fingerprt: Confirmed matching regular browser session\n"
            "IP Address      : 198.51.100.82 (Austin, TX, US)\n"
            "Seller Protect  : ELIGIBLE\n"
            "====================================================\n"
        )
        doc1_path = upload_dir / f"{doc1_id}_{doc1_filename}"
        doc1_path.write_text(doc1_content, encoding="utf-8")
        fields1 = {
            "customer_name": "Sarah Connor",
            "transaction_id": "9JJ2837461928374",
            "auth_status": "3D Secure 2.2 Passed (ECI 05)",
            "seller_protection": "ELIGIBLE",
            "amount": 75.25,
            "currency": "USD",
        }
        d1 = db.save_document({
            "id": doc1_id,
            "dispute_id": dispute_id,
            "filename": doc1_filename,
            "stored_path": str(doc1_path),
            "file_size": len(doc1_content.encode("utf-8")),
            "content_type": "text/plain",
            "doc_type": "authentication_log",
            "status": "COMPLETED",
            "raw_text": doc1_content,
            "extracted_fields": fields1,
        })
        created_docs.append(d1)

        doc2_id = f"demo-sub-{dispute_id[:8]}"
        doc2_filename = "CloudServices_Subscription_Agreement.txt"
        doc2_content = (
            "====================================================\n"
            "CLOUDSERVICES CORP — RECURRING BILLING TERMS\n"
            "====================================================\n"
            "Subscriber      : Sarah Connor (sarah.c@skytech.net)\n"
            "Plan Tier       : Pro Developer Annual Subscription Renewal\n"
            "Renewal Amount  : $75.25 USD\n"
            "Billing Date    : October 26, 2026\n"
            "Notice Stated   : Pre-billing notice dispatched on October 12, 2026\n"
            "Terms Agreed    : Explicit recurring consent authorized at signup.\n"
            "====================================================\n"
        )
        doc2_path = upload_dir / f"{doc2_id}_{doc2_filename}"
        doc2_path.write_text(doc2_content, encoding="utf-8")
        fields2 = {
            "subscriber": "Sarah Connor",
            "service": "Pro Developer Annual Subscription Renewal",
            "amount": 75.25,
            "currency": "USD",
            "pre_billing_notice_sent": "2026-10-12",
        }
        d2 = db.save_document({
            "id": doc2_id,
            "dispute_id": dispute_id,
            "filename": doc2_filename,
            "stored_path": str(doc2_path),
            "file_size": len(doc2_content.encode("utf-8")),
            "content_type": "text/plain",
            "doc_type": "contract",
            "status": "COMPLETED",
            "raw_text": doc2_content,
            "extracted_fields": fields2,
        })
        created_docs.append(d2)

    elif dispute_id == "PP-D-628405":
        # Duplicate Transaction Scenario
        doc1_id = f"demo-order1-{dispute_id[:8]}"
        doc1_filename = "Order_Receipt_License_Seat_1.txt"
        doc1_content = (
            "====================================================\n"
            "SAAS TOOLKIT — ORDER CONFIRMATION #1\n"
            "====================================================\n"
            "Order ID        : ORD-SAAS-101\n"
            "Purchaser       : Jordan Bell (jordan.bell@cyberlog.io)\n"
            "Transaction ID  : 4KK7765123498123\n"
            "Item Purchased  : Enterprise Seat License #1 (Primary User)\n"
            "License Key     : KEY-ENT-8842-A\n"
            "Gross Amount    : $120.00 USD\n"
            "Timestamp       : 2026-11-01 09:38:12 UTC\n"
            "====================================================\n"
        )
        doc1_path = upload_dir / f"{doc1_id}_{doc1_filename}"
        doc1_path.write_text(doc1_content, encoding="utf-8")
        fields1 = {
            "order_id": "ORD-SAAS-101",
            "transaction_id": "4KK7765123498123",
            "customer_name": "Jordan Bell",
            "product_or_service": "Enterprise Seat License #1",
            "amount": 120.00,
            "currency": "USD",
        }
        d1 = db.save_document({
            "id": doc1_id,
            "dispute_id": dispute_id,
            "filename": doc1_filename,
            "stored_path": str(doc1_path),
            "file_size": len(doc1_content.encode("utf-8")),
            "content_type": "text/plain",
            "doc_type": "order_confirmation",
            "status": "COMPLETED",
            "raw_text": doc1_content,
            "extracted_fields": fields1,
        })
        created_docs.append(d1)

        doc2_id = f"demo-order2-{dispute_id[:8]}"
        doc2_filename = "Order_Receipt_License_Seat_2.txt"
        doc2_content = (
            "====================================================\n"
            "SAAS TOOLKIT — ORDER CONFIRMATION #2 (ADDITIONAL SEAT)\n"
            "====================================================\n"
            "Order ID        : ORD-SAAS-102\n"
            "Purchaser       : Jordan Bell (jordan.bell@cyberlog.io)\n"
            "Transaction ID  : 8ZZ5541234567890\n"
            "Item Purchased  : Enterprise Seat License #2 (Additional Team Seat)\n"
            "License Key     : KEY-ENT-9915-B\n"
            "Gross Amount    : $120.00 USD\n"
            "Timestamp       : 2026-11-01 09:40:45 UTC\n"
            "====================================================\n"
        )
        doc2_path = upload_dir / f"{doc2_id}_{doc2_filename}"
        doc2_path.write_text(doc2_content, encoding="utf-8")
        fields2 = {
            "order_id": "ORD-SAAS-102",
            "transaction_id": "8ZZ5541234567890",
            "customer_name": "Jordan Bell",
            "product_or_service": "Enterprise Seat License #2",
            "amount": 120.00,
            "currency": "USD",
        }
        d2 = db.save_document({
            "id": doc2_id,
            "dispute_id": dispute_id,
            "filename": doc2_filename,
            "stored_path": str(doc2_path),
            "file_size": len(doc2_content.encode("utf-8")),
            "content_type": "text/plain",
            "doc_type": "order_confirmation",
            "status": "COMPLETED",
            "raw_text": doc2_content,
            "extracted_fields": fields2,
        })
        created_docs.append(d2)

    elif dispute_id == "PP-D-517392":
        # Refund / Credit Not Processed Scenario
        doc1_id = f"demo-voucher-{dispute_id[:8]}"
        doc1_filename = "Store_Credit_Voucher_SC-9500.txt"
        doc1_content = (
            "====================================================\n"
            "VINTAGE STORE APPAREL — STORE CREDIT ISSUANCE RECORD\n"
            "====================================================\n"
            "Voucher Code    : SC-9500\n"
            "Beneficiary     : Clara Oswald (clara.o@timetravel.org)\n"
            "Return Order ID : ORD-VINT-3391\n"
            "Credit Value    : $95.00 USD\n"
            "Issuance Date   : October 22, 2026\n"
            "Status          : ACTIVE / AVAILABLE ON ACCOUNT\n"
            "Terms           : Issued per Customer Service Return Agreement #RMA-8812\n"
            "====================================================\n"
        )
        doc1_path = upload_dir / f"{doc1_id}_{doc1_filename}"
        doc1_path.write_text(doc1_content, encoding="utf-8")
        fields1 = {
            "voucher_code": "SC-9500",
            "customer_name": "Clara Oswald",
            "refund_or_credit_amount": 95.00,
            "currency": "USD",
            "issuance_date": "2026-10-22",
            "status": "ACTIVE_CREDIT",
        }
        d1 = db.save_document({
            "id": doc1_id,
            "dispute_id": dispute_id,
            "filename": doc1_filename,
            "stored_path": str(doc1_path),
            "file_size": len(doc1_content.encode("utf-8")),
            "content_type": "text/plain",
            "doc_type": "credit_memo",
            "status": "COMPLETED",
            "raw_text": doc1_content,
            "extracted_fields": fields1,
        })
        created_docs.append(d1)

        doc2_id = f"demo-policy-{dispute_id[:8]}"
        doc2_filename = "Merchant_Return_Policy_Acknowledgment.txt"
        doc2_content = (
            "====================================================\n"
            "VINTAGE APPAREL — PUBLISHED RETURN & CREDIT POLICY\n"
            "====================================================\n"
            "Section 4.1     : Returns after 14 days are issued as store credit.\n"
            "Customer Agree  : Clara Oswald accepted terms at checkout on 2026-10-20.\n"
            "RMA Number      : RMA-8812\n"
            "Action Completed: Credit voucher dispatched to buyer email within 24 hours.\n"
            "====================================================\n"
        )
        doc2_path = upload_dir / f"{doc2_id}_{doc2_filename}"
        doc2_path.write_text(doc2_content, encoding="utf-8")
        fields2 = {
            "customer_name": "Clara Oswald",
            "rma_number": "RMA-8812",
            "policy": "Store credit for returns after 14 days",
            "status": "Credit voucher dispatched",
        }
        d2 = db.save_document({
            "id": doc2_id,
            "dispute_id": dispute_id,
            "filename": doc2_filename,
            "stored_path": str(doc2_path),
            "file_size": len(doc2_content.encode("utf-8")),
            "content_type": "text/plain",
            "doc_type": "terms_of_service",
            "status": "COMPLETED",
            "raw_text": doc2_content,
            "extracted_fields": fields2,
        })
        created_docs.append(d2)

    else:
        # Default: INR Scenario (PP-D-849201 or any standard dispute)
        doc1_id = f"demo-fedex-{dispute_id[:8]}"
        doc1_filename = "FedEx_Proof_of_Delivery_789456123012.txt"
        doc1_content = (
            "====================================================\n"
            "FEDEX EXPRESS DELIVERY CONFIRMATION RECEIPT\n"
            "====================================================\n"
            "Tracking Number : 789456123012\n"
            "Service Level   : FedEx Home Delivery (Standard Ground)\n"
            "Delivery Status : DELIVERED (Front Door / Porch Scan)\n"
            "Delivery Date   : October 14, 2026 at 14:32:00 PST\n"
            "Ship Date       : October 11, 2026\n"
            "Order Number    : ORD-77410\n"
            "Recipient Name  : Eleanor Vance\n"
            "Delivery Address: 742 Evergreen Terrace, Springfield, OR 97477\n"
            "Weight / Units  : 2.4 lbs (1 Package)\n"
            "Signature Status: Direct Signature on File (Geo-stamped scan)\n"
            "Carrier Notes   : Left at front door per delivery instructions.\n"
            "====================================================\n"
        )
        doc1_path = upload_dir / f"{doc1_id}_{doc1_filename}"
        doc1_path.write_text(doc1_content, encoding="utf-8")

        fields1 = {
            "tracking_number": "789456123012",
            "carrier": "FedEx",
            "delivery_date": "2026-10-14",
            "shipment_date": "2026-10-11",
            "order_id": "ORD-77410",
            "customer_name": "Eleanor Vance",
            "amount": 189.50,
            "currency": "USD",
        }
        d1 = db.save_document({
            "id": doc1_id,
            "dispute_id": dispute_id,
            "filename": doc1_filename,
            "stored_path": str(doc1_path),
            "file_size": len(doc1_content.encode("utf-8")),
            "content_type": "text/plain",
            "doc_type": "delivery_confirmation",
            "status": "COMPLETED",
            "raw_text": doc1_content,
            "extracted_fields": fields1,
        })
        created_docs.append(d1)

        doc2_id = f"demo-invoice-{dispute_id[:8]}"
        doc2_filename = "Commercial_Invoice_INV-77410.txt"
        doc2_content = (
            "====================================================\n"
            "APEX HARDWARE & PERIPHERALS INC. — TAX INVOICE\n"
            "====================================================\n"
            "Invoice Number  : INV-77410\n"
            "Order ID        : ORD-77410\n"
            "Purchase Date   : October 10, 2026\n"
            "Transaction ID  : 7TY9843219084321\n"
            "Customer Name   : Eleanor Vance\n"
            "Billing Address : 742 Evergreen Terrace, Springfield, OR\n"
            "Payment Method  : PayPal Checkout (Verified Seller Protection)\n"
            "Item Purchased  : Apex Pro Split Ergonomic Keyboard (Titanium Grey)\n"
            "Quantity        : 1\n"
            "Item Price      : $189.50 USD\n"
            "Sales Tax       : $0.00 USD\n"
            "Total Amount    : $189.50 USD\n"
            "Fulfillment Ref : Shipped Oct 11 via FedEx (789456123012)\n"
            "====================================================\n"
        )
        doc2_path = upload_dir / f"{doc2_id}_{doc2_filename}"
        doc2_path.write_text(doc2_content, encoding="utf-8")

        fields2 = {
            "order_id": "ORD-77410",
            "transaction_id": "7TY9843219084321",
            "customer_name": "Eleanor Vance",
            "purchase_date": "2026-10-10",
            "amount": 189.50,
            "currency": "USD",
            "product_or_service": "Apex Pro Split Ergonomic Keyboard",
            "tracking_number": "789456123012",
        }
        d2 = db.save_document({
            "id": doc2_id,
            "dispute_id": dispute_id,
            "filename": doc2_filename,
            "stored_path": str(doc2_path),
            "file_size": len(doc2_content.encode("utf-8")),
            "content_type": "text/plain",
            "doc_type": "invoice",
            "status": "COMPLETED",
            "raw_text": doc2_content,
            "extracted_fields": fields2,
        })
        created_docs.append(d2)

    doc_names = [d["filename"] for d in created_docs]
    db.log_audit(
        dispute_id=dispute_id,
        action="EVIDENCE_UPLOADED",
        actor=merchant_id,
        details={"type": "demo_seed", "count": len(created_docs), "documents": doc_names},
    )

    return {
        "status": "SEEDED",
        "message": f"Seeded {len(created_docs)} verified sample evidence documents for dispute '{dispute_id}'.",
        "documents": created_docs,
    }
