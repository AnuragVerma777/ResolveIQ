"""ResolveIQ AI Resolution Studio Engine.

Generates professional, evidence-backed PayPal dispute responses using only verified
documentary facts. Strictly segregates verified facts, merchant context, and uncertain info.
Mandatory merchant review and approval before PayPal submission.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from backend.ai.engine import StructuredGenerator
from backend.ai.schemas import (
    CategorizedClaim,
    DisputeResponseDraft,
    EvidenceMatrixReport,
    EvidenceStatus,
    FactSectionType,
    StructuredEvidenceRecord,
)

logger = logging.getLogger(__name__)

RESOLUTION_SYSTEM_RULES = """You are ResolveIQ's Senior Dispute Resolution Legal Officer.
Your objective is to draft a rigorous, professional PayPal dispute response on behalf of the merchant.

CRITICAL FACTUAL AND ADJUDICATIVE DIRECTIVES:
1. GROUNDED IN VERIFIED EVIDENCE ONLY:
   - Every single factual claim asserting shipping, tracking, delivery, billing, or items MUST cite a verified evidence document.
   - NEVER invent, infer, or assume delivery confirmation, customer communications, tracking numbers, or invoice amounts.
   - If an assertion cannot be proven by an uploaded document, classify it as 'merchant_statement' or 'unknown_information', NEVER as 'verified_fact'.

2. MANDATORY SEGREGATION OF PROVENANCE:
   - "verified_fact": Proved by documented carrier scan, invoice, or receipt.
   - "merchant_statement": Merchant-supplied context (e.g. internal notes, dispatch policies).
   - "ai_recommendation": Procedural guidance (e.g. invoking PayPal Seller Protection terms).
   - "unknown_information": Data requested by buyer or PayPal that is absent or unverified.

3. ETHICAL CONSTRAINTS:
   - NEVER promise, guarantee, or predict dispute resolution outcome.
   - NEVER state that missing evidence proves the customer lied.
   - Explicit merchant review and approval is mandatory before any submission to PayPal.
"""


class ResolutionEngine:
    """Engine for generating professional dispute responses grounded in verified evidence."""

    def __init__(self, generator: StructuredGenerator | None = None):
        self.generator = generator

    def validate_claims_against_evidence(
        self,
        claims: list[CategorizedClaim],
        evidence_records: list[StructuredEvidenceRecord],
    ) -> None:
        """Verify that every evidence_id cited in claims exists in the supplied evidence records."""
        evidence_map = {rec.evidence_id: rec for rec in evidence_records}
        for claim in claims:
            for eid in claim.evidence_ids:
                if eid not in evidence_map:
                    raise ValueError(f"Claim references unsupported evidence reference '{eid}'")

    def generate_response(
        self,
        dispute_data: Mapping[str, Any],
        evidence_records: list[StructuredEvidenceRecord],
        matrix_report: EvidenceMatrixReport | None = None,
        merchant_instructions: str = "",
        existing_version: int = 0,
    ) -> DisputeResponseDraft:
        """Synthesize dispute details, evidence records, and matrix findings into an official response draft."""
        dispute_id = str(dispute_data.get("dispute_id", "UNKNOWN_DISPUTE"))
        reason = str(dispute_data.get("dispute_reason") or dispute_data.get("reason") or "UNKNOWN_REASON")
        complaint = str(dispute_data.get("customer_complaint") or dispute_data.get("claim") or "")
        merchant_ctx = str(dispute_data.get("merchant_context") or "")
        tx_details = dispute_data.get("transaction_details") or {}
        now_str = datetime.now(timezone.utc).isoformat()
        response_id = f"resp_{uuid4().hex[:12]}"
        version = existing_version + 1

        # Map known evidence IDs to documents
        evidence_map = {rec.evidence_id: rec for rec in evidence_records}
        known_sources = {rec.source_document for rec in evidence_records}

        # Step 1: Synthesize verified facts strictly from evidence records
        verified_facts: list[str] = []
        categorized_claims: list[CategorizedClaim] = []

        for rec in evidence_records:
            if rec.tracking_number and rec.delivery_date:
                fact_str = (
                    f"Carrier shipment (tracking #{rec.tracking_number}) was successfully delivered "
                    f"to the destination on {rec.delivery_date}."
                )
                verified_facts.append(fact_str)
                categorized_claims.append(
                    CategorizedClaim(
                        text=fact_str,
                        section=FactSectionType.VERIFIED_FACT,
                        evidence_ids=[rec.evidence_id],
                        source_documents=[rec.source_document],
                    )
                )
            elif rec.tracking_number and rec.shipment_date:
                fact_str = f"Package was dispatched under tracking #{rec.tracking_number} on {rec.shipment_date}."
                verified_facts.append(fact_str)
                categorized_claims.append(
                    CategorizedClaim(
                        text=fact_str,
                        section=FactSectionType.VERIFIED_FACT,
                        evidence_ids=[rec.evidence_id],
                        source_documents=[rec.source_document],
                    )
                )

            if rec.order_id and rec.amount is not None:
                fact_str = f"Order #{rec.order_id} total billed amount was documented as ${rec.amount:.2f} {rec.currency or 'USD'}."
                verified_facts.append(fact_str)
                categorized_claims.append(
                    CategorizedClaim(
                        text=fact_str,
                        section=FactSectionType.VERIFIED_FACT,
                        evidence_ids=[rec.evidence_id],
                        source_documents=[rec.source_document],
                    )
                )

            if rec.refund_status:
                fact_str = f"Refund record in '{rec.source_document}' documents status as {rec.refund_status}."
                verified_facts.append(fact_str)
                categorized_claims.append(
                    CategorizedClaim(
                        text=fact_str,
                        section=FactSectionType.VERIFIED_FACT,
                        evidence_ids=[rec.evidence_id],
                        source_documents=[rec.source_document],
                    )
                )

            # If no tracking and no amount was extracted, extract factual key lines from key_facts
            if not rec.tracking_number and rec.amount is None and not rec.refund_status:
                for kf in rec.key_facts[:2]:
                    fact_str = f"Document '{rec.source_document}' verifies: {kf}"
                    verified_facts.append(fact_str)
                    categorized_claims.append(
                        CategorizedClaim(
                            text=fact_str,
                            section=FactSectionType.VERIFIED_FACT,
                            evidence_ids=[rec.evidence_id],
                            source_documents=[rec.source_document],
                        )
                    )

        # Step 2: Merchant statements
        merchant_statements: list[str] = []
        if merchant_ctx:
            merchant_statements.append(f"Merchant internal record: {merchant_ctx}")
            categorized_claims.append(
                CategorizedClaim(
                    text=f"Merchant notes: {merchant_ctx}",
                    section=FactSectionType.MERCHANT_STATEMENT,
                    evidence_ids=[],
                    source_documents=[],
                )
            )

        # Step 3: AI procedural recommendations
        ai_recommendations: list[str] = []
        reason_lower = reason.lower()
        if "not_received" in reason_lower or "not received" in reason_lower:
            if any(rec.delivery_date for rec in evidence_records):
                ai_recommendations.append(
                    "Request PayPal dispute resolution officer review carrier delivery confirmation "
                    "showing successful delivery prior to dispute initiation."
                )
                ai_recommendations.append("Apply PayPal Seller Protection for eligible merchandise fulfillment.")
            else:
                ai_recommendations.append(
                    "Obtain official carrier delivery scan confirmation before finalizing case review."
                )
        elif "unauthori" in reason_lower:
            ai_recommendations.append(
                "Submit proof of fulfillment to confirmed PayPal buyer address to establish Seller Protection eligibility."
            )
            ai_recommendations.append(
                "Provide user authentication, IP geolocations, and 2FA audit logs substantiating authorized account access."
            )
        elif "duplicate" in reason_lower:
            ai_recommendations.append(
                "Provide transaction identifiers and fulfillment records for each distinct order, or confirm credit issuance if an erroneous duplicate charge occurred."
            )
        elif "credit" in reason_lower or "refund" in reason_lower:
            ai_recommendations.append(
                "Submit proof of issued credit transaction or document that returned merchandise was not delivered per return policy terms."
            )
        elif "described" in reason_lower or "damaged" in reason_lower:
            ai_recommendations.append(
                "Submit pre-shipment quality assurance records, product serial numbers, and request buyer return merchandise before refund consideration."
            )
        else:
            ai_recommendations.append(
                "Submit merchant quality assurance records and verified transaction invoice."
            )

        for rec_text in ai_recommendations:
            categorized_claims.append(
                CategorizedClaim(
                    text=rec_text,
                    section=FactSectionType.AI_RECOMMENDATION,
                    evidence_ids=[],
                    source_documents=[],
                )
            )

        # Step 4: Unknown / Missing Information
        unknown_info: list[str] = []
        missing_warnings: list[str] = []
        contradiction_warnings: list[str] = []

        if matrix_report:
            for item in matrix_report.matrix_items:
                if item.missing_information:
                    for m in item.missing_information:
                        if m not in unknown_info:
                            unknown_info.append(m)
                            missing_warnings.append(m)
                if item.contradiction_warnings:
                    for cw in item.contradiction_warnings:
                        if cw not in contradiction_warnings:
                            contradiction_warnings.append(cw)
        else:
            if not any(rec.delivery_date for rec in evidence_records):
                unknown_info.append("Final carrier delivery confirmation timestamp at recipient door")
                missing_warnings.append("Carrier proof of delivery scan is absent from uploaded records")

        for u in unknown_info:
            categorized_claims.append(
                CategorizedClaim(
                    text=f"Pending documentation: {u}",
                    section=FactSectionType.UNKNOWN_INFORMATION,
                    evidence_ids=[],
                    source_documents=[],
                    uncertain=True,
                )
            )

        # Step 5: Questions for merchant
        questions_for_merchant = [
            f"Can you provide {m.lower()}?" for m in missing_warnings[:3]
        ]

        # Step 6: Construct Official Response Letter
        subject_line = f"Rebuttal & Documentary Evidence Dossier for Dispute {dispute_id} ({reason})"
        letter_parts = [
            f"Dear PayPal Dispute Adjudication Team,",
            f"\nRe: Dispute Reference {dispute_id}",
            f"Claim Category: {reason.replace('_', ' ').title()}",
            f"Transaction ID: {tx_details.get('transaction_id', 'Referenced on file')}",
            f"\nWe are formally submitting this evidence-backed response on behalf of the merchant regarding the dispute opened by the buyer.",
            f"\n--- 1. VERIFIED FACTUAL FINDINGS ---",
        ]

        if verified_facts:
            for fact in verified_facts:
                letter_parts.append(f"• {fact}")
        else:
            letter_parts.append("• Transaction initiated on merchant platform; documentary records attached.")

        letter_parts.append(f"\n--- 2. MERCHANT FULFILLMENT CONTEXT ---")
        if merchant_statements:
            for ms in merchant_statements:
                letter_parts.append(f"• {ms}")
        else:
            letter_parts.append("• Order processed in accordance with standard merchant fulfillment policies.")

        letter_parts.append(f"\n--- 3. ADJUDICATIVE POSITION & SELLER PROTECTION ---")
        for rec_step in ai_recommendations:
            letter_parts.append(f"• {rec_step}")

        if unknown_info:
            letter_parts.append(f"\n--- 4. CLARIFICATIONS & PENDING DATA ---")
            for u in unknown_info:
                letter_parts.append(f"• Pending verification: {u}")

        letter_parts.append(
            "\nBased on the documented evidence referenced above, we respectfully request the dispute officer "
            "review the attached official records and conclude the inquiry accordingly.\n\n"
            "Respectfully submitted,\nMerchant Resolution Operations"
        )

        official_response_letter = "\n".join(letter_parts)

        # Enforce server-side verification: all evidence_ids must be valid
        for claim in categorized_claims:
            for eid in claim.evidence_ids:
                if eid not in evidence_map:
                    raise ValueError(f"Claim references unsupported evidence ID '{eid}'")

        return DisputeResponseDraft(
            response_id=response_id,
            dispute_id=dispute_id,
            version=version,
            subject_line=subject_line,
            official_response_letter=official_response_letter,
            categorized_claims=categorized_claims,
            verified_facts=verified_facts,
            merchant_statements=merchant_statements,
            ai_recommendations=ai_recommendations,
            unknown_or_missing_info=unknown_info,
            questions_for_merchant=questions_for_merchant,
            missing_evidence_warnings=missing_warnings,
            contradiction_warnings=contradiction_warnings,
            merchant_approval_required=True,
            approved_by_merchant=False,
            submission_status="DRAFT",
        )
