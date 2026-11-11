"""Pre-flight verification for PayPal dispute evidence submissions.

Enforces Safety and Reliability rules:
1. Prevent duplicate submissions.
2. Check dispute status (must be open/actionable).
3. Check submission deadline (must not be expired).
4. Verify merchant permissions (dispute must allow PROVIDE_EVIDENCE).
5. Verify required evidence (tracking/fulfillment documentation for NOT_RECEIVED).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status

from backend.config import Settings
from backend.db import Database
from backend.paypal.client import PayPalClient
from backend.paypal.demo_data import DEMO_DISPUTES

logger = logging.getLogger(__name__)


def get_dispute_context(
    dispute_id: str, db: Database, settings: Settings
) -> dict[str, Any] | None:
    """Retrieve dispute details from live PayPal Sandbox, demo datasets, or local DB."""
    # 1. Check live PayPal sandbox if configured
    if settings.paypal_client_id and settings.paypal_client_secret:
        client = PayPalClient(settings)
        try:
            live = client.get_dispute(dispute_id)
            if live and "dispute_id" in live:
                return live
        except Exception:
            pass
        finally:
            client.close()

    # 2. Check demo catalog
    for d in DEMO_DISPUTES:
        if d.get("dispute_id") == dispute_id:
            return d

    # 3. Check local database
    local = db.get_dispute(dispute_id)
    if local:
        return {
            "dispute_id": local["dispute_id"],
            "reason": local.get("reason", "MERCHANDISE_OR_SERVICE_NOT_RECEIVED"),
            "status": "WAITING_FOR_SELLER_RESPONSE",
            "dispute_state": "REQUIRED_ACTION",
            "allowed_response_options": ["PROVIDE_EVIDENCE", "ACCEPT_CLAIM"],
            "seller_response_due_date": None,
        }

    return None


def check_submission_readiness(
    dispute_id: str,
    db: Database,
    settings: Settings,
    response_id: str | None = None,
) -> dict[str, Any]:
    """Inspect readiness for evidence submission without raising exceptions.

    Returns diagnostic report with blockers and warnings.
    """
    dispute = get_dispute_context(dispute_id, db, settings)
    blockers: list[str] = []
    warnings: list[str] = []

    if not dispute:
        return {
            "eligible": False,
            "dispute_id": dispute_id,
            "status": "UNKNOWN",
            "is_open": False,
            "deadline": None,
            "is_deadline_passed": False,
            "can_submit_evidence": False,
            "blockers": [f"Dispute '{dispute_id}' not found in PayPal Sandbox or local registry."],
            "warnings": [],
        }

    dispute_status = (dispute.get("status") or "WAITING_FOR_SELLER_RESPONSE").upper()
    allowed_options = dispute.get("allowed_response_options") or []
    due_date = dispute.get("seller_response_due_date")

    # 1. Status check
    is_open = dispute_status not in ("RESOLVED", "CLOSED", "CANCELED")
    if not is_open:
        blockers.append(f"Dispute is in terminal state '{dispute_status}' and cannot receive evidence.")

    # 2. Deadline check
    is_deadline_passed = False
    if due_date:
        try:
            norm_date = due_date.replace("Z", "+00:00")
            parsed_date = datetime.fromisoformat(norm_date)
            if parsed_date.tzinfo is None:
                parsed_date = parsed_date.replace(tzinfo=timezone.utc)
            now_utc = datetime.now(timezone.utc)
            if parsed_date < now_utc:
                is_deadline_passed = True
                blockers.append(f"Submission deadline has passed ({due_date}). Submission rejected.")
        except Exception as exc:
            warnings.append(f"Could not parse response due date '{due_date}': {exc}")

    # 3. Permissions check
    can_submit_evidence = True
    if allowed_options and "PROVIDE_EVIDENCE" not in allowed_options:
        can_submit_evidence = False
        blockers.append(
            f"Merchant permission not granted: PayPal allowed actions are {allowed_options}, "
            "which does not include 'PROVIDE_EVIDENCE'."
        )

    # 4. Check attached documents and tracking
    docs = db.list_documents(dispute_id=dispute_id)
    has_tracking = any(
        isinstance(d.get("extracted_fields"), dict) and d["extracted_fields"].get("tracking_number")
        for d in docs
    )
    if not docs:
        warnings.append("No supporting documents are attached to this dispute in ResolveIQ.")

    # 5. Check if response is already submitted
    latest_resp = db.get_response(response_id) if response_id else db.get_latest_response(dispute_id)
    if latest_resp and latest_resp.get("submission_status") == "SUBMITTED":
        blockers.append(
            f"Response version v{latest_resp.get('version')} has already been submitted to PayPal "
            f"(Debug ID: {latest_resp.get('submission_debug_id')}). Duplicate submission blocked."
        )

    return {
        "eligible": len(blockers) == 0,
        "dispute_id": dispute_id,
        "status": dispute_status,
        "is_open": is_open,
        "deadline": due_date,
        "is_deadline_passed": is_deadline_passed,
        "allowed_response_options": allowed_options,
        "can_submit_evidence": can_submit_evidence,
        "attached_documents_count": len(docs),
        "has_tracking_number": has_tracking,
        "blockers": blockers,
        "warnings": warnings,
    }


def validate_dispute_submission(
    dispute_id: str,
    db: Database,
    settings: Settings,
    tracking_info: list[dict[str, Any]] | None = None,
    notes: str = "",
    response_id: str | None = None,
) -> dict[str, Any]:
    """Execute strict pre-flight checks and raise HTTPException if blocked."""
    readiness = check_submission_readiness(dispute_id, db, settings, response_id)

    if not readiness["eligible"]:
        blocker_msg = "; ".join(readiness["blockers"])
        if not readiness["is_open"] or readiness["is_deadline_passed"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Dispute submission blocked: {blocker_msg}",
            )
        if not readiness["can_submit_evidence"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Dispute action forbidden: {blocker_msg}",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Submission pre-flight failure: {blocker_msg}",
        )

    # Check substantive content for item not received claims
    dispute = get_dispute_context(dispute_id, db, settings) or {}
    reason = str(dispute.get("reason", "")).upper()
    has_tracking = bool(tracking_info and len(tracking_info) > 0)
    has_notes = bool(notes and len(notes.strip()) > 10)

    if "NOT_RECEIVED" in reason and not has_tracking and not has_notes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Required evidence missing: 'Merchandise or service not received' disputes "
                "require either carrier tracking information or a substantive merchant rebuttal letter."
            ),
        )

    return readiness
