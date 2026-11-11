"""FastAPI routes for Zapier Catch Hook automation settings, test pings,

and delivery history logging.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.config import Settings, get_settings
from backend.db import Database
from backend.integrations.zapier import (
    AutomationEvent,
    DeliveryResult,
    ZapierWebhookService,
    mask_webhook_url,
)
from backend.security import RateLimit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/automation", tags=["automation"])


def get_db(settings: Settings = Depends(get_settings)) -> Database:
    return Database(settings.db_path)


ALL_SUPPORTED_EVENTS = [
    {
        "id": AutomationEvent.DISPUTE_CREATED.value,
        "name": "Dispute Ingested",
        "description": "Triggered when a new dispute is opened or imported into ResolveIQ.",
    },
    {
        "id": AutomationEvent.HIGH_PRIORITY.value,
        "name": "High Priority Claim",
        "description": "Triggered when dispute amount exceeds high-value threshold or is flagged urgent.",
    },
    {
        "id": AutomationEvent.EVIDENCE_MISSING.value,
        "name": "Evidence Missing",
        "description": "Triggered when critical documents (tracking, invoice, proof) are missing.",
    },
    {
        "id": AutomationEvent.EVIDENCE_READY_FOR_REVIEW.value,
        "name": "Ready for Merchant Review",
        "description": "Triggered when evidence matrix completeness score meets submission threshold.",
    },
    {
        "id": AutomationEvent.DEADLINE_APPROACHING.value,
        "name": "Deadline Approaching",
        "description": "Triggered when PayPal response due date is within 48 hours.",
    },
    {
        "id": AutomationEvent.SUBMITTED.value,
        "name": "Dispute Submitted",
        "description": "Triggered only after an explicit merchant approval and successful submission to PayPal.",
    },
]


# ---------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------

class AutomationSettingsResponse(BaseModel):
    webhook_url: str
    webhook_url_masked: str
    is_configured: bool
    is_verified: bool
    last_verified_at: str | None = None
    enabled_events: list[str]
    all_supported_events: list[dict[str, str]]
    timeout_seconds: float
    max_retries: int


class AutomationSettingsUpdateRequest(BaseModel):
    webhook_url: str = Field(default="", description="Zapier Catch Hook HTTPS URL")
    enabled_events: list[str] = Field(default_factory=list)
    timeout_seconds: float = Field(default=8.0, ge=1.0, le=30.0)
    max_retries: int = Field(default=2, ge=0, le=5)


class TestWebhookRequest(BaseModel):
    webhook_url: str | None = Field(default=None, description="Optional override URL to test")


class TestWebhookResponse(BaseModel):
    success: bool
    status_code: int | None = None
    response_time_ms: float
    error: str | None = None
    message: str
    event_id: str


class EmitEventRequest(BaseModel):
    event: str
    dispute_id: str
    extra_data: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------

@router.get("/settings", response_model=AutomationSettingsResponse)
def get_automation_settings(
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_db),
):
    """Retrieve current Zapier automation configuration, verification status, and supported events."""
    data = db.get_automation_settings()
    url = data.get("webhook_url") or settings.zapier_webhook_url
    is_configured = bool(url.strip())
    is_verified = bool(data.get("is_verified", False))

    return AutomationSettingsResponse(
        webhook_url=url,
        webhook_url_masked=mask_webhook_url(url),
        is_configured=is_configured,
        is_verified=is_verified and is_configured,
        last_verified_at=data.get("last_verified_at"),
        enabled_events=data.get("enabled_events", []),
        all_supported_events=ALL_SUPPORTED_EVENTS,
        timeout_seconds=float(data.get("timeout_seconds", 8.0)),
        max_retries=int(data.get("max_retries", 2)),
    )


@router.put("/settings", response_model=AutomationSettingsResponse)
def update_automation_settings(
    req: AutomationSettingsUpdateRequest,
    db: Database = Depends(get_db),
):
    """Update Zapier Catch Hook configuration.

    Validates HTTPS scheme. If the URL is changed, verification status is reset to False.
    """
    clean_url = req.webhook_url.strip()
    if clean_url:
        parsed = urlparse(clean_url)
        if parsed.scheme != "https":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Webhook URL: Zapier Webhook URLs must use secure HTTPS.",
            )
        if not parsed.netloc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Webhook URL format.",
            )

    current = db.get_automation_settings()
    # Reset verification if URL changed
    url_changed = clean_url != current.get("webhook_url", "")
    is_verified = False if url_changed else current.get("is_verified", False)
    last_verified = None if url_changed else current.get("last_verified_at")

    # Validate event IDs
    valid_event_ids = {e.value for e in AutomationEvent}
    filtered_events = [ev for ev in req.enabled_events if ev in valid_event_ids]
    if not req.enabled_events:
        filtered_events = list(valid_event_ids)

    saved = db.save_automation_settings({
        "webhook_url": clean_url,
        "enabled_events": filtered_events,
        "is_verified": is_verified,
        "last_verified_at": last_verified,
        "timeout_seconds": req.timeout_seconds,
        "max_retries": req.max_retries,
    })

    return AutomationSettingsResponse(
        webhook_url=saved.get("webhook_url", ""),
        webhook_url_masked=mask_webhook_url(saved.get("webhook_url", "")),
        is_configured=bool(saved.get("webhook_url", "")),
        is_verified=bool(saved.get("is_verified", False)),
        last_verified_at=saved.get("last_verified_at"),
        enabled_events=saved.get("enabled_events", []),
        all_supported_events=ALL_SUPPORTED_EVENTS,
        timeout_seconds=float(saved.get("timeout_seconds", 8.0)),
        max_retries=int(saved.get("max_retries", 2)),
    )


@router.post("/test", response_model=TestWebhookResponse)
def test_zapier_webhook(
    req: TestWebhookRequest | None = None,
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_db),
    _rate_limit: None = Depends(RateLimit(max_requests=10, window_seconds=60.0, scope="automation_test")),
):
    """Dispatch a test webhook event to verify connection with Zapier Catch Hook.

    Only marks connection as verified when a 2xx HTTP response is actually received.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    current_settings = db.get_automation_settings()
    target_url = (req.webhook_url if req and req.webhook_url else None) or current_settings.get("webhook_url") or settings.zapier_webhook_url
    target_url = target_url.strip() if target_url else ""

    if not target_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot test webhook: No Zapier Webhook URL configured.",
        )

    parsed = urlparse(target_url)
    if parsed.scheme != "https":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zapier Webhook URL must use HTTPS.",
        )

    test_payload = {
        "message": "ResolveIQ Zapier Webhook verification ping",
        "dispute_id": "PP-D-VERIFY-TEST",
        "amount": 189.50,
        "currency": "USD",
        "reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        "status": "WAITING_FOR_SELLER_RESPONSE",
        "portal_url": "https://resolveiq.app/disputes/PP-D-VERIFY-TEST",
        "verified_at": now_iso,
    }

    service = ZapierWebhookService(
        webhook_url=target_url,
        timeout_seconds=float(current_settings.get("timeout_seconds", 8.0)),
        max_retries=1,
        db=db,
    )

    try:
        result = service.emit(AutomationEvent.DISPUTE_CREATED, test_payload, test_mode=True)
    finally:
        service.close()

    # Update verified status in DB if delivery was successful
    if result.delivered:
        db.save_automation_settings({
            "is_verified": True,
            "last_verified_at": now_iso,
        })
        message = "Test webhook successfully received by Zapier! Integration verified."
    else:
        db.save_automation_settings({
            "is_verified": False,
        })
        message = f"Delivery failed ({result.error or 'HTTP ' + str(result.status_code)}). Check your Zapier Hook URL."

    return TestWebhookResponse(
        success=result.delivered,
        status_code=result.status_code,
        response_time_ms=result.response_time_ms,
        error=result.error,
        message=message,
        event_id=result.event_id,
    )


@router.get("/deliveries")
def list_webhook_deliveries(
    limit: int = Query(default=50, ge=1, le=100),
    db: Database = Depends(get_db),
):
    """Retrieve chronological history of dispatched webhook events and results."""
    return db.list_webhook_deliveries(limit=limit)


@router.post("/emit")
def emit_automation_event(
    req: EmitEventRequest,
    db: Database = Depends(get_db),
):
    """Manually dispatch an operational automation event for a dispute."""
    valid_events = {e.value: e for e in AutomationEvent}
    if req.event not in valid_events:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown automation event: '{req.event}'. Supported: {list(valid_events.keys())}",
        )

    ev_enum = valid_events[req.event]
    event_data = {
        "dispute_id": req.dispute_id,
        "dispatched_at": datetime.now(timezone.utc).isoformat(),
        **req.extra_data,
    }

    settings_data = db.get_automation_settings()
    service = ZapierWebhookService(
        webhook_url=settings_data.get("webhook_url", ""),
        timeout_seconds=float(settings_data.get("timeout_seconds", 8.0)),
        max_retries=int(settings_data.get("max_retries", 2)),
        enabled_events={
            AutomationEvent(e) for e in settings_data.get("enabled_events", []) if e in valid_events
        },
        db=db,
    )

    try:
        res = service.emit(ev_enum, event_data)
        return {
            "delivered": res.delivered,
            "status_code": res.status_code,
            "error": res.error,
            "event_id": res.event_id,
            "attempts": res.attempts,
            "response_time_ms": res.response_time_ms,
        }
    finally:
        service.close()
