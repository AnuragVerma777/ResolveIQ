"""ResolveIQ Core Evidence Intelligence Engine.

Converts documents into structured evidence records, identifies dispute claims,
matches evidence to claims, detects conflicting dates/amounts/IDs, and calculates
an explainable completeness score based on documented evidence coverage.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Mapping

from backend.ai.engine import StructuredGenerator
from backend.ai.schemas import (
    CompletenessScoreBreakdown,
    ConflictWarning,
    EvidenceMatrixItem,
    EvidenceMatrixReport,
    EvidenceStatus,
    StructuredEvidenceRecord,
)

logger = logging.getLogger(__name__)

EVIDENCE_INTELLIGENCE_SYSTEM_RULES = """You are ResolveIQ's Chief Evidence Adjudication Intelligence Engine.
Your mandate is to critically evaluate merchant evidence against each specific claim in a PayPal dispute.

CRITICAL OPERATIONAL RULES:
1. EVIDENCE STATUSES:
   - "Supported": Merchant possesses verified documentary evidence directly substantiating or resolving the claim.
   - "Partially supported": Evidence exists but lacks crucial elements (e.g. tracking exists but lacks delivery scan).
   - "Unsupported": No documentary evidence addresses this claim whatsoever.
   - "Contradictory": Evidence directly conflicts with the claim or contradicts other merchant records.

2. OBJECTIVITY AND ETHICS:
   - DO NOT fabricate evidence, carrier scans, or tracking numbers under any circumstances.
   - DO NOT treat missing evidence as proof that an event did not happen (absence of evidence is not evidence of absence).
   - Base all reasoning on verified source documents and verbatim text excerpts.
   - Clearly explain WHY each evidence item is relevant to its assigned claim.
   - Flag any date, amount, order ID, or tracking inconsistencies.
"""


class EvidenceIntelligenceEngine:
    """Core engine for dispute claim decomposition, evidence mapping, and conflict analysis."""

    def __init__(self, generator: StructuredGenerator | None = None):
        self.generator = generator

    def build_evidence_records(
        self,
        documents: list[dict[str, Any]],
    ) -> list[StructuredEvidenceRecord]:
        """Convert extracted documents into verified, structured evidence records."""
        records: list[StructuredEvidenceRecord] = []

        for doc in documents:
            doc_id = doc.get("id") or doc.get("evidence_id") or "UNKNOWN_DOC"
            filename = doc.get("name") or doc.get("filename") or "document"
            text = doc.get("text") or doc.get("raw_text") or ""
            doc_type = str(doc.get("doc_type") or "other")
            fields = doc.get("extracted_fields") or {}

            # Gather facts from extracted text and fields
            key_facts = []
            if fields.get("order_id"):
                key_facts.append(f"Order ID documented as {fields['order_id']}.")
            if fields.get("tracking_number"):
                key_facts.append(f"Carrier tracking number documented as {fields['tracking_number']}.")
            if fields.get("amount"):
                key_facts.append(f"Documented total amount is {fields['amount']} {fields.get('currency', 'USD')}.")
            if fields.get("delivery_date"):
                key_facts.append(f"Delivery date documented as {fields['delivery_date']}.")
            if fields.get("shipment_date"):
                key_facts.append(f"Shipment date documented as {fields['shipment_date']}.")
            if fields.get("refund_status"):
                key_facts.append(f"Refund status documented as {fields['refund_status']}.")

            # If no structured fields, extract short factual lines from text
            if not key_facts and text:
                lines = [ln.strip() for ln in text.split("\n") if len(ln.strip()) > 8 and not ln.startswith("[")]
                key_facts = lines[:3]

            excerpt = text[:250].strip() if text else ""

            records.append(
                StructuredEvidenceRecord(
                    evidence_id=doc_id,
                    document_id=doc.get("id"),
                    source_document=filename,
                    doc_type=doc_type,
                    key_facts=key_facts,
                    verbatim_excerpt=excerpt,
                    order_id=fields.get("order_id"),
                    transaction_id=fields.get("transaction_id"),
                    tracking_number=fields.get("tracking_number"),
                    amount=fields.get("amount"),
                    currency=fields.get("currency"),
                    purchase_date=fields.get("purchase_date"),
                    delivery_date=fields.get("delivery_date"),
                    shipment_date=fields.get("shipment_date"),
                    refund_status=fields.get("refund_status"),
                    verified=True,
                )
            )

        return records

    def identify_claims(self, dispute_data: Mapping[str, Any]) -> list[dict[str, str]]:
        """Decompose dispute into discrete, adjudicable claims."""
        claims: list[dict[str, str]] = []
        reason = str(dispute_data.get("dispute_reason") or dispute_data.get("reason") or "").strip()
        complaint = str(dispute_data.get("customer_complaint") or dispute_data.get("claim") or "").strip()
        merchant_ctx = str(dispute_data.get("merchant_context") or "").strip()

        # Primary reason claim
        if reason:
            claims.append({
                "claim": f"Dispute reason asserted: {reason}",
                "claim_type": "paypal_reason",
            })

        # Customer complaint decomposition
        if complaint:
            complaint_lower = complaint.lower()
            # Non-receipt claim
            if any(k in complaint_lower for k in ["never received", "not received", "didn't receive", "didn't get", "where is my", "lost in transit"]):
                claims.append({
                    "claim": "Buyer claims the purchased merchandise or service was never delivered to their address.",
                    "claim_type": "customer_assertion",
                })
            # Unauthorized claim
            if any(k in complaint_lower for k in ["unauthorized", "didn't authorize", "hacked", "stolen card", "fraud", "unrecognized"]):
                claims.append({
                    "claim": "Buyer claims the payment transaction was unauthorized or fraudulent.",
                    "claim_type": "customer_assertion",
                })
            # Condition / Description claim
            if any(k in complaint_lower for k in ["damaged", "broken", "cracked", "defective", "wrong item", "counterfeit", "not as described"]):
                claims.append({
                    "claim": "Buyer claims the received item was damaged, defective, or significantly different from the description.",
                    "claim_type": "customer_assertion",
                })
            # Refund claim
            if any(k in complaint_lower for k in ["refund", "credit", "return", "promised refund", "returned item"]):
                claims.append({
                    "claim": "Buyer claims a promised refund or credit was not processed after returning merchandise.",
                    "claim_type": "customer_assertion",
                })
            # Duplicate / Amount claim
            if any(k in complaint_lower for k in ["charged twice", "duplicate", "double charge", "wrong amount", "overcharged"]):
                claims.append({
                    "claim": "Buyer claims an incorrect billing amount or duplicate charge.",
                    "claim_type": "customer_assertion",
                })
            # If no specialized category triggered, retain verbatim complaint statement
            if len(claims) <= 1:
                claims.append({
                    "claim": f"Buyer states: \"{complaint}\"",
                    "claim_type": "customer_assertion",
                })

        # Merchant position
        if merchant_ctx:
            claims.append({
                "claim": f"Merchant position: {merchant_ctx}",
                "claim_type": "merchant_position",
            })

        return claims

    def detect_conflicts(
        self,
        dispute_data: Mapping[str, Any],
        evidence_records: list[StructuredEvidenceRecord],
    ) -> list[ConflictWarning]:
        """Detect conflicting dates, amounts, order IDs, or tracking information across records."""
        conflicts: list[ConflictWarning] = []

        tx_details = dispute_data.get("transaction_details") or {}
        dispute_amount = None
        if "amount" in tx_details:
            try:
                dispute_amount = float(tx_details["amount"])
            except (ValueError, TypeError):
                pass
        elif "amount" in dispute_data:
            try:
                dispute_amount = float(dispute_data["amount"])
            except (ValueError, TypeError):
                pass

        dispute_tx_id = str(tx_details.get("transaction_id") or dispute_data.get("transaction_id") or "").strip()
        dispute_order_id = str(dispute_data.get("order_id") or "").strip()

        # 1. Amount Conflict Check
        if dispute_amount is not None:
            for rec in evidence_records:
                if rec.amount is not None and abs(rec.amount - dispute_amount) > 0.05:
                    conflicts.append(
                        ConflictWarning(
                            conflict_type="amount_mismatch",
                            field_name="amount",
                            disputed_value=f"{dispute_amount:.2f}",
                            evidence_value=f"{rec.amount:.2f}",
                            source_reference=rec.source_document,
                            explanation=(
                                f"Dispute transaction amount is {dispute_amount:.2f}, but evidence document "
                                f"'{rec.source_document}' records total amount as {rec.amount:.2f}."
                            ),
                        )
                    )

        # 2. Order ID Conflict Check
        if dispute_order_id:
            for rec in evidence_records:
                if rec.order_id and rec.order_id.lower() != dispute_order_id.lower():
                    conflicts.append(
                        ConflictWarning(
                            conflict_type="order_id_mismatch",
                            field_name="order_id",
                            disputed_value=dispute_order_id,
                            evidence_value=rec.order_id,
                            source_reference=rec.source_document,
                            explanation=(
                                f"Dispute references order ID '{dispute_order_id}', but document "
                                f"'{rec.source_document}' references order ID '{rec.order_id}'."
                            ),
                        )
                    )

        # 3. Date Sequence Conflict Check
        for rec in evidence_records:
            if rec.shipment_date and rec.delivery_date:
                # Basic ISO YYYY-MM-DD comparison
                if re.match(r"^\d{4}-\d{2}-\d{2}$", rec.shipment_date) and re.match(r"^\d{4}-\d{2}-\d{2}$", rec.delivery_date):
                    if rec.delivery_date < rec.shipment_date:
                        conflicts.append(
                            ConflictWarning(
                                conflict_type="date_mismatch",
                                field_name="delivery_date",
                                disputed_value=f"Shipped {rec.shipment_date}",
                                evidence_value=f"Delivered {rec.delivery_date}",
                                source_reference=rec.source_document,
                                explanation=(
                                    f"Documented delivery date ({rec.delivery_date}) in '{rec.source_document}' "
                                    f"precedes shipment date ({rec.shipment_date})."
                                ),
                            )
                        )

        # 4. Tracking Inconsistency Check
        tracking_numbers = {rec.tracking_number for rec in evidence_records if rec.tracking_number}
        if len(tracking_numbers) > 1:
            tracking_list = ", ".join(sorted(tracking_numbers))
            conflicts.append(
                ConflictWarning(
                    conflict_type="tracking_mismatch",
                    field_name="tracking_number",
                    disputed_value="Single shipment expected",
                    evidence_value=tracking_list,
                    source_reference="Multiple evidence documents",
                    explanation=f"Multiple conflicting carrier tracking numbers found in evidence: {tracking_list}.",
                )
            )

        return conflicts

    def calculate_completeness_score(
        self,
        matrix_items: list[EvidenceMatrixItem],
        evidence_records: list[StructuredEvidenceRecord],
        conflicts: list[ConflictWarning],
    ) -> CompletenessScoreBreakdown:
        """Calculate an explainable, rubric-based evidence completeness score.

        Strict Directive: The score is based on documented evidence coverage,
        NOT an invented probability of winning. Missing evidence is not proof
        that an event did not happen.
        """
        if not matrix_items:
            return CompletenessScoreBreakdown(
                overall_score=0,
                claim_coverage_points=0,
                core_evidence_points=0,
                data_consistency_points=0,
                conflict_deductions=0,
                explanation="No claims or evidence available to evaluate.",
                scoring_rubric={"total": 0},
            )

        # 1. Claim Coverage Points (up to 50 pts)
        total_claims = len(matrix_items)
        supported_weight = 0.0
        for item in matrix_items:
            if item.evidence_status == EvidenceStatus.SUPPORTED:
                supported_weight += 1.0
            elif item.evidence_status == EvidenceStatus.PARTIALLY_SUPPORTED:
                supported_weight += 0.5
            elif item.evidence_status == EvidenceStatus.CONTRADICTORY:
                supported_weight -= 0.25

        claim_coverage_ratio = max(0.0, min(1.0, supported_weight / total_claims))
        claim_coverage_points = int(round(claim_coverage_ratio * 50))

        # 2. Core Documentation Points (up to 30 pts)
        has_delivery_proof = any(
            rec.delivery_date or rec.tracking_number or "delivery" in rec.doc_type or "shipping" in rec.doc_type
            for rec in evidence_records
        )
        has_order_receipt = any(
            rec.order_id or rec.amount or "invoice" in rec.doc_type or "order" in rec.doc_type
            for rec in evidence_records
        )
        has_communication_record = any(
            "email" in rec.doc_type or "notes" in rec.doc_type or "receipt" in rec.doc_type
            for rec in evidence_records
        )

        core_evidence_points = 0
        if has_delivery_proof:
            core_evidence_points += 15
        if has_order_receipt:
            core_evidence_points += 10
        if has_communication_record:
            core_evidence_points += 5

        # 3. Data Consistency Points (up to 20 pts)
        # 20 points base, deducting 5 points per conflict down to 0
        conflict_deductions = min(20, len(conflicts) * 5)
        data_consistency_points = 20 - conflict_deductions

        # Overall Score
        overall_score = max(0, min(100, claim_coverage_points + core_evidence_points + data_consistency_points))

        # Human-readable explanation of the score calculation
        explanation = (
            f"Evidence Completeness Score: {overall_score}/100. "
            f"Breakdown: Claim Coverage: {claim_coverage_points}/50 ({int(supported_weight)}/{total_claims} claims supported), "
            f"Core Records: {core_evidence_points}/30 "
            f"({'Delivery Proof present' if has_delivery_proof else 'Delivery proof missing'}, "
            f"{'Order/Invoice present' if has_order_receipt else 'Invoice missing'}), "
            f"Data Consistency: {data_consistency_points}/20 ({len(conflicts)} conflict(s) detected)."
        )

        rubric = {
            "claim_coverage_max": 50,
            "claim_coverage_awarded": claim_coverage_points,
            "core_evidence_max": 30,
            "core_evidence_awarded": core_evidence_points,
            "data_consistency_max": 20,
            "data_consistency_awarded": data_consistency_points,
            "conflict_deductions": conflict_deductions,
            "total_score": overall_score,
        }

        return CompletenessScoreBreakdown(
            overall_score=overall_score,
            claim_coverage_points=claim_coverage_points,
            core_evidence_points=core_evidence_points,
            data_consistency_points=data_consistency_points,
            conflict_deductions=conflict_deductions,
            explanation=explanation,
            scoring_rubric=rubric,
        )

    def generate_matrix(
        self,
        dispute_data: Mapping[str, Any],
        documents: list[dict[str, Any]],
    ) -> EvidenceMatrixReport:
        """Execute full Evidence Intelligence Pipeline: decompose claims, map evidence,

        identify missing/unsupported aspects, detect conflicts, and score completeness.
        """
        dispute_id = str(dispute_data.get("dispute_id", "UNKNOWN_DISPUTE"))
        now_str = datetime.now(timezone.utc).isoformat()

        # Step 1: Convert extracted documents into structured evidence records
        evidence_records = self.build_evidence_records(documents)

        # Step 2: Identify claims made in the dispute
        raw_claims = self.identify_claims(dispute_data)

        # Step 3: Detect conflicts across documents and dispute
        conflicts = self.detect_conflicts(dispute_data, evidence_records)

        # Step 4: Build matrix items for each claim
        matrix_items: list[EvidenceMatrixItem] = []
        unsupported_claims: list[str] = []
        recommended_actions: list[str] = []

        for c in raw_claims:
            claim_text = c["claim"]
            claim_type = c["claim_type"]
            claim_lower = claim_text.lower().replace("_", " ").replace("-", " ")

            matched_evidence_summaries: list[str] = []
            matched_sources: list[str] = []
            missing_info: list[str] = []
            contradiction_warns: list[str] = []
            unsupported_aspects: list[str] = []
            relevance_expl = ""
            action = None
            status = EvidenceStatus.UNSUPPORTED

            # Case 0: Merchant position / notes
            if claim_type == "merchant_position":
                if evidence_records:
                    rec = evidence_records[0]
                    matched_sources.append(rec.source_document)
                    matched_evidence_summaries.append(f"Referenced merchant documentation: '{rec.source_document}'")
                    status = EvidenceStatus.PARTIALLY_SUPPORTED
                    relevance_expl = f"Provides contextual merchant record in '{rec.source_document}'."
                    action = "Review documentation to ensure alignment with PayPal dispute requirements."
                else:
                    status = EvidenceStatus.UNSUPPORTED
                    relevance_expl = "No supporting merchant documentation provided."
                    missing_info.append("Merchant transaction documentation")
                    action = "Upload supporting evidence relevant to this claim."

            # Case A: Non-receipt claim
            elif "never delivered" in claim_lower or "not received" in claim_lower or "merchandise_or_service_not_received" in claim_lower:
                delivery_records = [
                    r for r in evidence_records
                    if r.delivery_date or r.tracking_number or "delivery" in r.doc_type or "shipping" in r.doc_type
                ]
                if delivery_records:
                    rec = delivery_records[0]
                    matched_sources.append(rec.source_document)
                    if rec.delivery_date and rec.tracking_number:
                        status = EvidenceStatus.SUPPORTED
                        matched_evidence_summaries.append(
                            f"Carrier tracking #{rec.tracking_number} documents delivery on {rec.delivery_date}."
                        )
                        relevance_expl = (
                            f"Verified carrier tracking in '{rec.source_document}' establishes physical delivery "
                            f"to the recipient on {rec.delivery_date}, directly disproving the non-receipt claim."
                        )
                        action = "Submit carrier tracking number and proof of delivery scan to PayPal Resolution Center."
                    else:
                        status = EvidenceStatus.PARTIALLY_SUPPORTED
                        matched_evidence_summaries.append(
                            f"Fulfillment record found in '{rec.source_document}' ({rec.tracking_number or 'no tracking'})."
                        )
                        relevance_expl = (
                            f"'{rec.source_document}' confirms dispatch, but lacks an official carrier delivery timestamp."
                        )
                        missing_info.append("Carrier proof of delivery scan confirming final delivery date and address")
                        unsupported_aspects.append("Definitive proof of delivery at buyer's postal address")
                        action = "Request an official delivery confirmation scan from the shipping carrier."
                else:
                    status = EvidenceStatus.UNSUPPORTED
                    relevance_expl = "No shipping receipts, carrier tracking scans, or delivery confirmations were provided."
                    missing_info.append("Shipping carrier tracking number and proof of fulfillment")
                    unsupported_claims.append(f"Non-receipt defense: {claim_text}")
                    action = "Locate and upload carrier tracking document or proof of dispatch."

            # Case B: Unauthorized transaction claim
            elif "unauthorized" in claim_lower or "fraud" in claim_lower:
                auth_records = [
                    r for r in evidence_records
                    if "order" in r.doc_type or "invoice" in r.doc_type or r.order_id or "email" in r.doc_type
                ]
                if auth_records:
                    rec = auth_records[0]
                    matched_sources.append(rec.source_document)
                    matched_evidence_summaries.append(
                        f"Order record #{rec.order_id or 'verified'} confirms buyer credentials and order details."
                    )
                    status = EvidenceStatus.PARTIALLY_SUPPORTED
                    relevance_expl = (
                        f"'{rec.source_document}' links purchase to buyer account, but additional proof of seller "
                        "protection address confirmation is needed."
                    )
                    missing_info.append("Proof that shipment was dispatched to PayPal seller protection eligible address")
                    action = "Provide PayPal transaction log showing confirmed seller protection shipping address."
                else:
                    status = EvidenceStatus.UNSUPPORTED
                    relevance_expl = "No account verification, order confirmation, or login audit records present."
                    missing_info.append("Order confirmation receipt and buyer authorization log")
                    unsupported_claims.append(f"Authorization defense: {claim_text}")
                    action = "Upload order receipt showing verified buyer account details."

            # Case C: Damaged / Not as described claim
            elif "damaged" in claim_lower or "not as described" in claim_lower:
                inspect_records = [
                    r for r in evidence_records
                    if "receipt" in r.doc_type or "invoice" in r.doc_type or "shipping" in r.doc_type
                ]
                if inspect_records:
                    rec = inspect_records[0]
                    matched_sources.append(rec.source_document)
                    status = EvidenceStatus.PARTIALLY_SUPPORTED
                    matched_evidence_summaries.append(f"Item specification documented in '{rec.source_document}'.")
                    relevance_expl = (
                        f"'{rec.source_document}' establishes item specifications prior to shipment, but lacks "
                        "buyer post-delivery damage inspection photos."
                    )
                    missing_info.append("Warehouse pre-shipment condition photo or return inspection report")
                    action = "Request buyer photographs of packaging damage or provide pre-shipment inspection log."
                else:
                    status = EvidenceStatus.UNSUPPORTED
                    relevance_expl = "No merchandise condition, warranty, or packaging inspection records available."
                    missing_info.append("Product description, condition checklist, and merchant return policy")
                    unsupported_claims.append(f"Item condition defense: {claim_text}")
                    action = "Upload product listing specification and quality control dispatch record."

            # Case D: Duplicate charge / billing claim
            elif "duplicate" in claim_lower or "charged twice" in claim_lower or "double charge" in claim_lower or "incorrect amount" in claim_lower or "overcharge" in claim_lower:
                order_records = [
                    r for r in evidence_records
                    if r.order_id or r.transaction_id or "invoice" in r.doc_type or "order" in r.doc_type or "receipt" in r.doc_type
                ]
                distinct_orders = {r.order_id for r in order_records if r.order_id}
                distinct_txns = {r.transaction_id for r in order_records if r.transaction_id}
                if len(distinct_orders) > 1 or len(distinct_txns) > 1:
                    status = EvidenceStatus.SUPPORTED
                    for r in order_records:
                        matched_sources.append(r.source_document)
                    matched_evidence_summaries.append(
                        f"Evidence documents multiple distinct transactions/orders: Orders {', '.join(sorted(distinct_orders))} (Txns {', '.join(sorted(distinct_txns))})."
                    )
                    relevance_expl = (
                        "Documentary evidence confirms separate purchase transactions with distinct order IDs and amounts, "
                        "disproving the assertion of an unfulfilled duplicate charge."
                    )
                    action = "Submit separate invoice and fulfillment records for each distinct order to PayPal."
                elif order_records:
                    status = EvidenceStatus.PARTIALLY_SUPPORTED
                    rec = order_records[0]
                    matched_sources.append(rec.source_document)
                    matched_evidence_summaries.append(f"Single order record documented in '{rec.source_document}'.")
                    relevance_expl = (
                        f"'{rec.source_document}' documents only a single order ({rec.order_id or 'verified'}). "
                        "Need billing processor logs for second alleged charge."
                    )
                    missing_info.append("Payment processor billing statement or bank charge trace showing all transaction IDs")
                    action = "Check transaction ledger for duplicate capture or verify if second charge was voided/reversed."
                else:
                    status = EvidenceStatus.UNSUPPORTED
                    relevance_expl = "No order receipts or payment transaction records provided."
                    missing_info.append("Invoices, order confirmations, and merchant transaction records")
                    unsupported_claims.append(f"Billing defense: {claim_text}")
                    action = "Upload invoice records for all transactions associated with the buyer."

            # Case E: Refund / Credit not processed claim
            elif "credit" in claim_lower or "refund" in claim_lower or "return" in claim_lower:
                refund_records = [
                    r for r in evidence_records
                    if r.refund_status or "refund" in r.doc_type or "credit" in r.doc_type
                ]
                return_records = [
                    r for r in evidence_records
                    if "return" in r.doc_type or "rma" in r.doc_type or "warehouse" in r.doc_type or "depot" in r.doc_type
                ]
                if refund_records:
                    rec = refund_records[0]
                    matched_sources.append(rec.source_document)
                    status = EvidenceStatus.SUPPORTED
                    matched_evidence_summaries.append(
                        f"Refund transaction record documented in '{rec.source_document}' (Status: {rec.refund_status or 'PROCESSED'})."
                    )
                    relevance_expl = (
                        f"'{rec.source_document}' establishes that refund credit was already initiated or executed, "
                        "satisfying the buyer's credit request."
                    )
                    action = "Submit refund transaction ID and credit confirmation receipt to PayPal."
                elif return_records:
                    rec = return_records[0]
                    matched_sources.append(rec.source_document)
                    status = EvidenceStatus.PARTIALLY_SUPPORTED
                    matched_evidence_summaries.append(
                        f"Return/RMA inspection documentation documented in '{rec.source_document}'."
                    )
                    relevance_expl = (
                        f"'{rec.source_document}' outlines return conditions or shows pending receipt of goods, "
                        "confirming that credit processing is contingent upon verified return delivery."
                    )
                    missing_info.append("Buyer carrier return tracking number and proof of delivery to merchant warehouse")
                    action = "Request buyer provide carrier return tracking number showing physical delivery to return depot."
                elif evidence_records:
                    rec = evidence_records[0]
                    matched_sources.append(rec.source_document)
                    status = EvidenceStatus.PARTIALLY_SUPPORTED
                    matched_evidence_summaries.append(f"Referenced merchant documentation: '{rec.source_document}'.")
                    relevance_expl = (
                        f"Merchant provided '{rec.source_document}', but specific return inspection or refund transaction proof is missing."
                    )
                    missing_info.append("Refund transaction receipt or return delivery confirmation")
                    action = "Provide return policy, return authorization log, or proof of issued credit."
                else:
                    status = EvidenceStatus.UNSUPPORTED
                    relevance_expl = "No return policy, RMA log, return tracking, or refund receipts available."
                    missing_info.append("Merchant return policy, RMA documentation, and refund records")
                    unsupported_claims.append(f"Credit defense: {claim_text}")
                    action = "Upload merchant return policy and return tracking verification."

            # Case F: Merchant position / other claims
            else:
                if evidence_records:
                    rec = evidence_records[0]
                    matched_sources.append(rec.source_document)
                    matched_evidence_summaries.append(f"Referenced merchant documentation: {rec.source_document}")
                    status = EvidenceStatus.PARTIALLY_SUPPORTED
                    relevance_expl = f"Provides contextual merchant record in '{rec.source_document}'."
                    action = "Review documentation to ensure alignment with PayPal dispute requirements."
                else:
                    status = EvidenceStatus.UNSUPPORTED
                    relevance_expl = "No supporting merchant documentation provided."
                    missing_info.append("Merchant transaction documentation")
                    action = "Upload supporting evidence relevant to this claim."

            # Attach any matching conflict warnings to this claim
            for conf in conflicts:
                if (
                    ("amount" in conf.field_name and "amount" in claim_lower)
                    or ("tracking" in conf.field_name and "delivered" in claim_lower)
                    or ("date" in conf.field_name and "delivered" in claim_lower)
                ):
                    contradiction_warns.append(conf.explanation)
                    if status == EvidenceStatus.SUPPORTED:
                        status = EvidenceStatus.CONTRADICTORY

            if action and action not in recommended_actions:
                recommended_actions.append(action)

            matrix_items.append(
                EvidenceMatrixItem(
                    claim=claim_text,
                    claim_type=claim_type,
                    supporting_evidence=matched_evidence_summaries,
                    source_documents=matched_sources,
                    evidence_relevance_explanation=relevance_expl,
                    evidence_status=status,
                    missing_information=missing_info,
                    contradiction_warnings=contradiction_warns,
                    unsupported_aspects=unsupported_aspects,
                    recommended_merchant_action=action,
                )
            )

        # Step 5: Compute explainable completeness score
        completeness = self.calculate_completeness_score(matrix_items, evidence_records, conflicts)

        return EvidenceMatrixReport(
            dispute_id=dispute_id,
            matrix_items=matrix_items,
            evidence_records=evidence_records,
            conflict_warnings=conflicts,
            unsupported_factual_claims=unsupported_claims,
            recommended_next_actions=recommended_actions,
            completeness_score=completeness,
            created_at=now_str,
        )
