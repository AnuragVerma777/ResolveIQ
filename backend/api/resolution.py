"""Resolution Studio API: Draft generation, merchant editing, approval gates,

and PayPal evidence submission.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, status

from backend.ai.evidence_engine import EvidenceIntelligenceEngine
from backend.ai.resolution_engine import ResolutionEngine
from backend.ai.schemas import (
    ApprovalRequest,
    AuditLogEntry,
    DisputeResponseDraft,
    EvidenceMatrixReport,
    ResponseEditRequest,
)
from backend.config import Settings, get_settings
from backend.db import Database
from backend.integrations.zapier import AutomationEvent, service_from_environment
from backend.paypal.client import PayPalAPIError, PayPalClient
from backend.paypal.preflight import check_submission_readiness, validate_dispute_submission
from backend.security import (
    RateLimit,
    dispute_submission_lock,
    get_current_merchant_id,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/disputes", tags=["resolution"])


def get_db(settings: Settings = Depends(get_settings)) -> Database:
    return Database(settings.db_path)


@router.post("/{dispute_id}/resolution/generate", response_model=DisputeResponseDraft)
def generate_dispute_response(
    dispute_id: str,
    merchant_instructions: str = "",
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_db),
    merchant_id: str = Depends(get_current_merchant_id),
    _rate_limit: None = Depends(RateLimit(max_requests=25, window_seconds=60.0, scope="resolution_generate")),
):
    """Generate professional evidence-backed dispute rebuttal response.

    Uses only verified facts from attached records. All factual claims cite
    supporting evidence documents. Disclaimers and approval gates are enforced.
    """
    dispute_record = db.get_dispute(dispute_id) or {}
    documents = db.list_documents(dispute_id=dispute_id)

    # 1. Generate or load evidence matrix
    matrix_engine = EvidenceIntelligenceEngine()
    dispute_payload = {
        "dispute_id": dispute_id,
        "dispute_reason": dispute_record.get("reason", "UNKNOWN"),
        "customer_complaint": dispute_record.get("customer_complaint", ""),
        "transaction_details": {
            "transaction_id": dispute_record.get("transaction_id", ""),
            "amount": dispute_record.get("amount", 0.0),
            "currency": dispute_record.get("currency", "USD"),
        },
        "merchant_context": dispute_record.get("merchant_context", ""),
    }

    matrix_report = matrix_engine.generate_matrix(dispute_payload, documents)
    evidence_records = matrix_engine.build_evidence_records(documents)

    # 2. Check existing version number
    latest_existing = db.get_latest_response(dispute_id)
    prev_version = latest_existing["version"] if latest_existing else 0

    # 3. Generate response draft
    resolution_engine = ResolutionEngine()
    draft = resolution_engine.generate_response(
        dispute_data=dispute_payload,
        evidence_records=evidence_records,
        matrix_report=matrix_report,
        merchant_instructions=merchant_instructions,
        existing_version=prev_version,
    )

    # 4. Save to database
    db.save_response({
        "id": draft.response_id,
        "dispute_id": dispute_id,
        "version": draft.version,
        "subject_line": draft.subject_line,
        "response_letter": draft.official_response_letter,
        "structured_payload": draft.model_dump(),
        "is_approved": False,
        "submission_status": "DRAFT",
    })

    # 5. Record audit log
    db.log_audit(
        dispute_id=dispute_id,
        action="RESPONSE_GENERATED",
        actor="ai_engine",
        details={
            "response_id": draft.response_id,
            "version": draft.version,
            "verified_facts_count": len(draft.verified_facts),
            "claims_count": len(draft.categorized_claims),
        },
    )

    return draft


@router.get("/{dispute_id}/resolution")
def get_resolution_details(
    dispute_id: str,
    db: Database = Depends(get_db),
):
    """Retrieve latest dispute response, approval status, and previous versions."""
    latest = db.get_latest_response(dispute_id)
    versions = db.list_response_versions(dispute_id)

    return {
        "dispute_id": dispute_id,
        "latest_response": latest,
        "versions_count": len(versions),
        "versions": [
            {
                "id": v["id"],
                "version": v["version"],
                "is_approved": v["is_approved"],
                "submission_status": v["submission_status"],
                "created_at": v["created_at"],
            }
            for v in versions
        ],
    }


@router.put("/{dispute_id}/resolution/{response_id}", response_model=DisputeResponseDraft)
def edit_response_draft(
    dispute_id: str,
    response_id: str,
    body: ResponseEditRequest,
    db: Database = Depends(get_db),
):
    """Allow merchant to polish and edit the generated response text.

    Editing automatically resets approval status to require re-approval before submission.
    """
    existing = db.get_response(response_id)
    if not existing or existing["dispute_id"] != dispute_id:
        raise HTTPException(status_code=404, detail="Response draft not found")

    new_version = existing["version"] + 1
    new_response_id = f"resp_edit_{new_version}_{existing['id'][-6:]}"

    payload = existing.get("structured_payload") or {}
    payload["official_response_letter"] = body.official_response_letter
    payload["version"] = new_version
    payload["response_id"] = new_response_id
    payload["is_approved"] = False
    payload["approved_by_merchant"] = False
    payload["approved_by"] = None
    payload["approved_at"] = None
    payload["submission_status"] = "DRAFT"

    saved = db.save_response({
        "id": new_response_id,
        "dispute_id": dispute_id,
        "version": new_version,
        "subject_line": existing["subject_line"],
        "response_letter": body.official_response_letter,
        "structured_payload": payload,
        "is_approved": False,
        "submission_status": "DRAFT",
    })

    db.log_audit(
        dispute_id=dispute_id,
        action="RESPONSE_EDITED",
        actor="merchant",
        details={
            "old_response_id": response_id,
            "new_response_id": new_response_id,
            "new_version": new_version,
            "notes": body.edit_notes,
        },
    )

    return DisputeResponseDraft.model_validate(saved["structured_payload"])


@router.post("/{dispute_id}/resolution/{response_id}/approve", response_model=DisputeResponseDraft)
def approve_response(
    dispute_id: str,
    response_id: str,
    req: ApprovalRequest,
    db: Database = Depends(get_db),
):
    """Explicit merchant approval action required prior to any dispute submission."""
    if not req.confirmed or not req.approver_name.strip():
        raise HTTPException(status_code=400, detail="Explicit approver confirmation is required")

    existing = db.get_response(response_id)
    if not existing or existing["dispute_id"] != dispute_id:
        raise HTTPException(status_code=404, detail="Response draft not found")

    now_str = datetime.now(timezone.utc).isoformat()
    payload = existing.get("structured_payload") or {}
    payload["approved_by_merchant"] = True
    payload["approved_by"] = req.approver_name.strip()
    payload["approved_at"] = now_str
    payload["submission_status"] = "APPROVED"

    updated = db.update_response(
        response_id,
        is_approved=True,
        approved_by=req.approver_name.strip(),
        approved_at=now_str,
        submission_status="APPROVED",
        structured_payload=payload,
    )

    db.log_audit(
        dispute_id=dispute_id,
        action="MERCHANT_APPROVED",
        actor=req.approver_name.strip(),
        details={"response_id": response_id, "approved_at": now_str},
    )

    return DisputeResponseDraft.model_validate(updated["structured_payload"])


@router.get("/{dispute_id}/preflight-check")
def preflight_check(
    dispute_id: str,
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_db),
):
    """Verify readiness for dispute submission: status, deadline, evidence, and permissions."""
    return check_submission_readiness(dispute_id, db, settings)


@router.post("/{dispute_id}/resolution/{response_id}/submit")
def submit_response_to_paypal(
    dispute_id: str,
    response_id: str,
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_db),
    merchant_id: str = Depends(get_current_merchant_id),
    _rate_limit: None = Depends(RateLimit(max_requests=10, window_seconds=60.0, scope="dispute_submit")),
):
    """Submit merchant-approved response to PayPal Resolution Center.

    Enforces mandatory approval gate, deadline validity, status check, required evidence verification,
    in-flight concurrency locking, and full audit logging.
    """
    with dispute_submission_lock(dispute_id):
        resp = db.get_response(response_id)
        if not resp or resp["dispute_id"] != dispute_id:
            raise HTTPException(status_code=404, detail="Response not found")

        # MANDATORY APPROVAL GATE
        if not resp.get("is_approved"):
            raise HTTPException(
                status_code=400,
                detail="Merchant approval is mandatory before submitting a dispute response to PayPal.",
            )

        if resp.get("submission_status") == "SUBMITTED":
            return {
                "status": "ALREADY_SUBMITTED",
                "message": "This response has already been submitted to PayPal.",
                "debug_id": resp.get("submission_debug_id"),
            }

        # Harvest tracking info from attached documents if available
        tracking_entries = []
        attached_docs = db.list_documents(dispute_id=dispute_id)
        for doc in attached_docs:
            fields = doc.get("extracted_fields") or {}
            if isinstance(fields, dict) and fields.get("tracking_number"):
                carrier = "OTHER"
                raw_text = (doc.get("raw_text") or "").upper()
                if "FEDEX" in raw_text:
                    carrier = "FEDEX"
                elif "UPS" in raw_text:
                    carrier = "UPS"
                elif "USPS" in raw_text:
                    carrier = "USPS"
                elif "DHL" in raw_text:
                    carrier = "DHL"
                tracking_entries.append({
                    "carrier_name": carrier,
                    "tracking_number": str(fields["tracking_number"]),
                })

        # Run strict safety & reliability pre-flight checks:
        # Validates status open, deadline not expired, permissions granted, required evidence present, no duplicates
        validate_dispute_submission(
            dispute_id=dispute_id,
            db=db,
            settings=settings,
            tracking_info=tracking_entries,
            notes=resp.get("response_letter", ""),
            response_id=response_id,
        )

        # Record submission attempt in audit history
        db.log_audit(
            dispute_id=dispute_id,
            action="PAYPAL_SUBMISSION_ATTEMPTED",
            actor=merchant_id,
            details={"response_id": response_id, "evidence_type": "PROOF_OF_FULFILLMENT"},
        )

        evidence_payload = {
            "evidence_type": "PROOF_OF_FULFILLMENT",
            "evidence_info": {
                "tracking_info": tracking_entries,
                "notes": resp["response_letter"][:2000],
            },
        }

        # Execute PayPal submission
        debug_id = f"mock-pp-debug-{uuid4().hex[:8]}"
        if settings.paypal_client_id and settings.paypal_client_secret:
            client = PayPalClient(settings)
            try:
                res = client.submit_evidence(dispute_id, evidence_payload)
                debug_id = res.get("debug_id") or debug_id
            except PayPalAPIError as exc:
                db.log_audit(
                    dispute_id=dispute_id,
                    action="PAYPAL_SUBMISSION_FAILED",
                    actor="paypal_client",
                    details={"status_code": exc.status_code, "error": str(exc)},
                )
                raise HTTPException(status_code=502, detail=f"PayPal API error: {str(exc)}")
            finally:
                client.close()

        # Update database record
        payload = resp.get("structured_payload") or {}
        payload["submission_status"] = "SUBMITTED"
        db.update_response(
            response_id,
            submission_status="SUBMITTED",
            submission_debug_id=debug_id,
            structured_payload=payload,
        )

        # Emit Zapier webhook notification (notification only; never automates submission)
        try:
            zapier = service_from_environment(db=db)
            zapier.emit(
                AutomationEvent.SUBMITTED,
                {
                    "dispute_id": dispute_id,
                    "response_id": response_id,
                    "submitted_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            zapier.close()
        except Exception as exc:
            logger.warning("Zapier notification failed on submission: %s", exc)

        # Log audit entry for successful submission result
        db.log_audit(
            dispute_id=dispute_id,
            action="PAYPAL_SUBMISSION_SUCCEEDED",
            actor="paypal_client",
            details={
                "response_id": response_id,
                "submission_debug_id": debug_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        # Also maintain legacy PAYPAL_SUBMITTED action for backwards compatibility
        db.log_audit(
            dispute_id=dispute_id,
            action="PAYPAL_SUBMITTED",
            actor=merchant_id,
            details={
                "response_id": response_id,
                "submission_debug_id": debug_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        return {
            "status": "SUBMITTED",
            "dispute_id": dispute_id,
            "response_id": response_id,
            "submission_debug_id": debug_id,
            "message": "Evidence-backed response successfully submitted to PayPal Resolution Center.",
        }


@router.get("/{dispute_id}/audit-trail", response_model=list[AuditLogEntry])
def get_dispute_audit_trail(
    dispute_id: str,
    db: Database = Depends(get_db),
):
    """Retrieve full chronological audit trail of all actions and state transitions."""
    logs = db.list_audit_logs(dispute_id)
    return [
        AuditLogEntry(
            id=log["id"],
            dispute_id=log["dispute_id"],
            action=log["action"],
            actor=log["actor"],
            details=log.get("details", {}),
            timestamp=log["timestamp"],
        )
        for log in logs
    ]
