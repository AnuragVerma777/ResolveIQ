"""FastAPI routes for PayPal REST API operations, sandbox synchronization,

dispute evidence adjudication, transaction search, and audit trail.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.config import Settings, get_settings
from backend.db import Database
from backend.paypal.client import (
    PayPalAPIError,
    PayPalAuthError,
    PayPalClient,
    PayPalNotFoundError,
    PayPalRateLimitError,
    PayPalTimeoutError,
    parse_dispute_requirements,
)
from backend.paypal.demo_data import DEMO_DISPUTES, DEMO_TRANSACTIONS
from backend.paypal.preflight import check_submission_readiness, validate_dispute_submission
from backend.security import (
    RateLimit,
    dispute_submission_lock,
    get_current_merchant_id,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/paypal", tags=["paypal"])


def get_db(settings: Settings = Depends(get_settings)) -> Database:
    return Database(settings.db_path)


# ---------------------------------------------------------------------
# Request & Response Schemas
# ---------------------------------------------------------------------

class PayPalConnectionStatus(BaseModel):
    connected: bool
    configured: bool
    mode: str = Field(description="'sandbox', 'demo', or 'demo_fallback'")
    base_url: str
    message: str
    token_valid: bool
    token_expires_in_seconds: int | None = None
    timestamp: str


class EvidenceSubmissionRequest(BaseModel):
    evidence_type: str = Field(
        default="PROOF_OF_FULFILLMENT",
        description="Official PayPal evidence category: PROOF_OF_FULFILLMENT, PROOF_OF_DELIVERY, PROOF_OF_REFUND, etc.",
    )
    carrier_name: str | None = Field(default=None, description="Carrier identifier: FEDEX, UPS, USPS, DHL, OTHER")
    tracking_number: str | None = Field(default=None, description="Carrier tracking / consignment number")
    carrier_name_other: str | None = Field(default=None, description="Carrier name if OTHER")
    refund_ids: list[str] = Field(default_factory=list, description="Associated refund transaction IDs")
    notes: str = Field(default="", description="Merchant evidence statement and factual notes")


class EvidenceSubmissionResult(BaseModel):
    status: str
    dispute_id: str
    submission_debug_id: str
    is_sandbox: bool
    source: str
    message: str
    submitted_at: str
    evidence_type: str
    details: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------

@router.get("/status", response_model=PayPalConnectionStatus)
def get_paypal_status(settings: Settings = Depends(get_settings)):
    """Check connectivity to PayPal REST APIs and return OAuth status.

    Never exposes client secret or bearer tokens.
    """
    client = PayPalClient(settings)
    try:
        status_info = client.check_connection()
        return PayPalConnectionStatus(
            connected=status_info["connected"],
            configured=status_info["configured"],
            mode=status_info["mode"],
            base_url=status_info["base_url"],
            message=status_info["message"],
            token_valid=status_info.get("token_valid", False),
            token_expires_in_seconds=status_info.get("token_expires_in_seconds"),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    finally:
        client.close()


@router.get("/disputes")
def list_paypal_disputes(
    dispute_state: str | None = Query(default=None, description="Filter by dispute_state: REQUIRED_ACTION, UNDER_REVIEW, etc."),
    page_size: int = Query(default=10, ge=1, le=50),
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_db),
):
    """Retrieve merchant disputes from PayPal Sandbox.

    When sandbox credentials are not configured, returns clearly labelled demo records.
    When sandbox API errors occur, explains the blocker and provides fallback records.
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    # Case 1: Sandbox credentials configured
    if settings.paypal_client_id and settings.paypal_client_secret:
        client = PayPalClient(settings)
        try:
            filters = {"page_size": page_size}
            if dispute_state:
                filters["dispute_state"] = dispute_state
            data = client.list_disputes(**filters)
            items = data.get("items", [])

            # Tag each record as live sandbox data
            for item in items:
                item["is_sandbox"] = True
                item["source"] = "sandbox"

            db.log_audit(
                dispute_id="SYSTEM",
                action="PAYPAL_SANDBOX_DISPUTES_FETCHED",
                actor="paypal_client",
                details={"count": len(items), "timestamp": now_iso},
            )

            return {
                "source": "sandbox",
                "is_sandbox": True,
                "items": items,
                "total_items": len(items),
                "timestamp": now_iso,
            }
        except PayPalAPIError as exc:
            logger.warning("PayPal sandbox disputes call failed: %s (debug_id=%s)", exc, exc.request_id)
            db.log_audit(
                dispute_id="SYSTEM",
                action="PAYPAL_API_ERROR",
                actor="paypal_client",
                details={
                    "status_code": exc.status_code,
                    "debug_id": exc.request_id,
                    "error": str(exc),
                },
            )
            # Graceful fallback with clear explanation
            filtered_demo = [
                d for d in DEMO_DISPUTES
                if not dispute_state or d.get("dispute_state") == dispute_state
            ][:page_size]

            return {
                "source": "demo_fallback",
                "is_sandbox": False,
                "error": str(exc),
                "status_code": exc.status_code,
                "paypal_debug_id": exc.request_id,
                "notice": (
                    f"PayPal Sandbox API returned HTTP {exc.status_code}. "
                    "Serving demo fallback records so adjudication workflow can continue."
                ),
                "items": filtered_demo,
                "total_items": len(filtered_demo),
                "timestamp": now_iso,
            }
        finally:
            client.close()

    # Case 2: Sandbox credentials not configured -> Demo records
    filtered_demo = [
        d for d in DEMO_DISPUTES
        if not dispute_state or d.get("dispute_state") == dispute_state
    ][:page_size]

    db.log_audit(
        dispute_id="SYSTEM",
        action="PAYPAL_DEMO_DISPUTES_FETCHED",
        actor="system",
        details={"count": len(filtered_demo), "reason": "No credentials configured"},
    )

    return {
        "source": "demo",
        "is_sandbox": False,
        "notice": "Demo PayPal dispute data displayed (PAYPAL_CLIENT_ID not configured in .env).",
        "items": filtered_demo,
        "total_items": len(filtered_demo),
        "timestamp": now_iso,
    }


@router.get("/disputes/{dispute_id}")
def get_paypal_dispute(
    dispute_id: str,
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_db),
):
    """Retrieve detailed dispute information and evidence requirements.

    Returns the full dispute payload, allowed response options, and domain-specific
    evidence guidance for the dispute type.
    """
    # 1. Check live PayPal sandbox if configured
    if settings.paypal_client_id and settings.paypal_client_secret:
        client = PayPalClient(settings)
        try:
            dispute = client.get_dispute(dispute_id)
            dispute["is_sandbox"] = True
            dispute["source"] = "sandbox"
            requirements = parse_dispute_requirements(dispute)

            db.log_audit(
                dispute_id=dispute_id,
                action="PAYPAL_DISPUTE_DETAILS_FETCHED",
                actor="paypal_client",
                details={"source": "sandbox"},
            )

            return {
                "source": "sandbox",
                "is_sandbox": True,
                "dispute": dispute,
                "requirements": requirements,
            }
        except PayPalNotFoundError:
            logger.info("Dispute %s not found in live sandbox; checking demo records", dispute_id)
        except PayPalAPIError as exc:
            logger.warning("Sandbox fetch failed for %s: %s", dispute_id, exc)
        finally:
            client.close()

    # 2. Check demo records
    for d in DEMO_DISPUTES:
        if d["dispute_id"] == dispute_id:
            requirements = parse_dispute_requirements(d)
            return {
                "source": "demo",
                "is_sandbox": False,
                "notice": "Demo dispute record displayed.",
                "dispute": d,
                "requirements": requirements,
            }

    # 3. Check local database
    local_dispute = db.get_dispute(dispute_id)
    if local_dispute:
        transformed = {
            "dispute_id": local_dispute["dispute_id"],
            "reason": local_dispute.get("reason", "MERCHANDISE_OR_SERVICE_NOT_RECEIVED"),
            "customer_complaint": local_dispute.get("customer_complaint", ""),
            "status": "WAITING_FOR_SELLER_RESPONSE",
            "dispute_state": "REQUIRED_ACTION",
            "dispute_life_cycle_stage": "CHARGEBACK",
            "dispute_amount": {
                "currency_code": local_dispute.get("currency", "USD"),
                "value": str(local_dispute.get("amount", "0.00")),
            },
            "allowed_response_options": ["PROVIDE_EVIDENCE", "ACCEPT_CLAIM"],
            "is_sandbox": False,
            "source": "local_db",
        }
        requirements = parse_dispute_requirements(transformed)
        return {
            "source": "local_db",
            "is_sandbox": False,
            "dispute": transformed,
            "requirements": requirements,
        }

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Dispute '{dispute_id}' not found in PayPal sandbox or local workspace.",
    )


@router.get("/disputes/{dispute_id}/requirements")
def get_dispute_requirements(
    dispute_id: str,
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_db),
):
    """Retrieve parsed evidence requirements and supported actions for a specific dispute."""
    details = get_paypal_dispute(dispute_id=dispute_id, settings=settings, db=db)
    return details.get("requirements")


@router.get("/transactions")
def list_paypal_transactions(
    start_date: str | None = Query(default=None, description="RFC3339 start timestamp (e.g. 2026-10-01T00:00:00Z)"),
    end_date: str | None = Query(default=None, description="RFC3339 end timestamp"),
    page_size: int = Query(default=10, ge=1, le=50),
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_db),
):
    """Search transactions via PayPal Transaction Search API with demo fallback."""
    now = datetime.now(timezone.utc)
    if not end_date:
        end_date = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    if not start_date:
        start_date = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    if settings.paypal_client_id and settings.paypal_client_secret:
        client = PayPalClient(settings)
        try:
            res = client.list_transactions(start_date=start_date, end_date=end_date, page_size=page_size)
            details = res.get("transaction_details", [])
            for item in details:
                item["is_sandbox"] = True
                item["source"] = "sandbox"

            db.log_audit(
                dispute_id="SYSTEM",
                action="PAYPAL_TRANSACTIONS_SEARCHED",
                actor="paypal_client",
                details={"count": len(details), "start_date": start_date, "end_date": end_date},
            )

            return {
                "source": "sandbox",
                "is_sandbox": True,
                "start_date": start_date,
                "end_date": end_date,
                "transaction_details": details,
                "total_items": len(details),
            }
        except PayPalAPIError as exc:
            logger.warning("Transaction search failed on sandbox: %s", exc)
            return {
                "source": "demo_fallback",
                "is_sandbox": False,
                "error": str(exc),
                "notice": "Serving demo transactions because PayPal sandbox query returned error.",
                "transaction_details": DEMO_TRANSACTIONS[:page_size],
                "total_items": len(DEMO_TRANSACTIONS),
            }
        finally:
            client.close()

    return {
        "source": "demo",
        "is_sandbox": False,
        "notice": "Demo transaction data (PAYPAL_CLIENT_ID not configured).",
        "transaction_details": DEMO_TRANSACTIONS[:page_size],
        "total_items": len(DEMO_TRANSACTIONS),
    }


@router.get("/disputes/{dispute_id}/preflight-check")
def check_dispute_preflight(
    dispute_id: str,
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_db),
):
    """Check readiness for dispute evidence submission: status, deadline, evidence, permissions."""
    return check_submission_readiness(dispute_id, db, settings)


@router.post("/disputes/{dispute_id}/provide-evidence", response_model=EvidenceSubmissionResult)
def submit_paypal_evidence(
    dispute_id: str,
    req: EvidenceSubmissionRequest,
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_db),
    merchant_id: str = Depends(get_current_merchant_id),
    _rate_limit: None = Depends(RateLimit(max_requests=10, window_seconds=60.0, scope="paypal_provide_evidence")),
):
    """Submit structured evidence directly to PayPal Resolution Center.

    Conforms to official PayPal provide-evidence API schema.
    Runs pre-flight validation for deadline, open status, permissions, and required evidence.
    Locks against concurrent in-flight submissions and logs operations in audit history.
    """
    with dispute_submission_lock(dispute_id):
        now_iso = datetime.now(timezone.utc).isoformat()

        # Build official PayPal evidence payload
        tracking_info: list[dict[str, Any]] = []
        if req.tracking_number:
            item: dict[str, Any] = {"tracking_number": req.tracking_number.strip()}
            if req.carrier_name:
                item["carrier_name"] = req.carrier_name.strip()
            if req.carrier_name_other:
                item["carrier_name_other"] = req.carrier_name_other.strip()
            tracking_info.append(item)

        # Enforce safety preflight check
        validate_dispute_submission(
            dispute_id=dispute_id,
            db=db,
            settings=settings,
            tracking_info=tracking_info,
            notes=req.notes,
        )

        # Record submission attempt in audit history
        db.log_audit(
            dispute_id=dispute_id,
            action="PAYPAL_SUBMISSION_ATTEMPTED",
            actor=merchant_id,
            details={
                "evidence_type": req.evidence_type,
                "tracking_number": req.tracking_number,
            },
        )

        evidence_payload: dict[str, Any] = {
            "evidence_type": req.evidence_type,
            "evidence_info": {
                "tracking_info": tracking_info,
                "refund_ids": req.refund_ids,
                "notes": req.notes[:2000] if req.notes else "Evidence submitted via ResolveIQ Adjudication Studio.",
            },
        }

        # Execute submission
        is_sandbox = False
        source = "demo"
        debug_id = f"demo-debug-{uuid4().hex[:8]}"
        extra_details: dict[str, Any] = {}

        if settings.paypal_client_id and settings.paypal_client_secret:
            client = PayPalClient(settings)
            try:
                res = client.submit_evidence(dispute_id, evidence_payload)
                is_sandbox = True
                source = "sandbox"
                debug_id = res.get("debug_id") or f"pp-dbg-{uuid4().hex[:8]}"
                extra_details = res
            except PayPalAPIError as exc:
                db.log_audit(
                    dispute_id=dispute_id,
                    action="PAYPAL_SUBMISSION_FAILED",
                    actor="paypal_client",
                    details={
                        "status_code": exc.status_code,
                        "debug_id": exc.request_id,
                        "error": str(exc),
                    },
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"PayPal API evidence submission failed ({exc.status_code}): {str(exc)}",
                )
            finally:
                client.close()

        # Update any existing resolution response for this dispute
        latest_resp = db.get_latest_response(dispute_id)
        if latest_resp:
            db.update_response(
                latest_resp["id"],
                submission_status="SUBMITTED",
                submission_debug_id=debug_id,
            )

        # Log audit events for submission result
        db.log_audit(
            dispute_id=dispute_id,
            action="PAYPAL_SUBMISSION_SUCCEEDED",
            actor="paypal_client",
            details={
                "evidence_type": req.evidence_type,
                "carrier_name": req.carrier_name,
                "tracking_number": req.tracking_number,
                "submission_debug_id": debug_id,
                "is_sandbox": is_sandbox,
                "source": source,
                "timestamp": now_iso,
            },
        )
        db.log_audit(
            dispute_id=dispute_id,
            action="PAYPAL_EVIDENCE_SUBMITTED",
            actor=merchant_id,
            details={
                "evidence_type": req.evidence_type,
                "carrier_name": req.carrier_name,
                "tracking_number": req.tracking_number,
                "submission_debug_id": debug_id,
                "is_sandbox": is_sandbox,
                "source": source,
                "timestamp": now_iso,
            },
        )

        return EvidenceSubmissionResult(
            status="SUBMITTED",
            dispute_id=dispute_id,
            submission_debug_id=debug_id,
            is_sandbox=is_sandbox,
            source=source,
            message="Dispute evidence successfully submitted to PayPal Resolution Center.",
            submitted_at=now_iso,
            evidence_type=req.evidence_type,
            details=extra_details,
        )


@router.post("/disputes/{dispute_id}/import")
def import_dispute_to_workspace(
    dispute_id: str,
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_db),
):
    """Import a dispute from PayPal (Sandbox or Demo) into ResolveIQ's local workspace.

    Persists the dispute in the local SQLite database so the merchant can immediately
    upload documents, analyze claims, run Gemini classification, and generate rebuttals.
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    # Check if already imported
    existing = db.get_dispute(dispute_id)
    if existing:
        return {
            "status": "ALREADY_IMPORTED",
            "message": f"Dispute '{dispute_id}' is already loaded in your case workspace.",
            "dispute": existing,
        }

    # Fetch details from PayPal or Demo data
    dispute_payload: dict[str, Any] | None = None

    if settings.paypal_client_id and settings.paypal_client_secret:
        client = PayPalClient(settings)
        try:
            live_data = client.get_dispute(dispute_id)
            dispute_payload = live_data
        except Exception as exc:
            logger.info("Could not fetch %s from live sandbox (%s), checking demo set", dispute_id, exc)
        finally:
            client.close()

    if not dispute_payload:
        for d in DEMO_DISPUTES:
            if d["dispute_id"] == dispute_id:
                dispute_payload = d
                break

    if not dispute_payload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dispute '{dispute_id}' could not be located in PayPal sandbox or demo catalog.",
        )

    # Extract fields for local DB
    reason = dispute_payload.get("reason", "MERCHANDISE_OR_SERVICE_NOT_RECEIVED")
    complaint = dispute_payload.get("customer_complaint", "")
    merchant_ctx = dispute_payload.get("merchant_context", "")

    # Extract transaction details
    tx_list = dispute_payload.get("disputed_transactions", [])
    first_tx = tx_list[0] if tx_list else {}
    tx_id = first_tx.get("seller_transaction_id") or first_tx.get("buyer_transaction_id") or ""

    # Amount & currency
    amount_obj = dispute_payload.get("dispute_amount", {})
    amount = float(amount_obj.get("value", 0.0))
    currency = amount_obj.get("currency_code", "USD")

    # If customer complaint is empty, check messages
    if not complaint and dispute_payload.get("messages"):
        complaint = " ".join(m.get("content", "") for m in dispute_payload["messages"])

    record = {
        "dispute_id": dispute_id,
        "reason": reason,
        "customer_complaint": complaint,
        "transaction_id": tx_id,
        "amount": amount,
        "currency": currency,
        "merchant_context": merchant_ctx,
    }

    saved = db.save_dispute(record)

    db.log_audit(
        dispute_id=dispute_id,
        action="PAYPAL_DISPUTE_IMPORTED",
        actor="merchant",
        details={
            "source": dispute_payload.get("source", "sandbox" if dispute_payload.get("is_sandbox") else "demo"),
            "reason": reason,
            "amount": amount,
            "currency": currency,
            "timestamp": now_iso,
        },
    )

    return {
        "status": "IMPORTED",
        "message": f"Dispute '{dispute_id}' imported into ResolveIQ case workspace.",
        "dispute": saved,
    }
