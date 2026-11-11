"""Merchant-controlled Zapier Catch Hook delivery over HTTPS webhooks.

Supported events:
1. dispute.created
2. dispute.high_priority
3. evidence.missing
4. evidence.ready_for_review
5. dispute.deadline_approaching
6. dispute.submitted

Features:
- Structured JSON payloads with UUID event IDs and UTC ISO-8601 timestamps
- Sensitive customer data sanitation
- Configurable timeout and transient error retries (5xx / timeouts)
- Duplicate event deduplication window
- Persistent SQLite delivery history logging
- Real test webhook execution with verification status
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from pydantic import BaseModel, Field

from backend.db import Database

logger = logging.getLogger(__name__)


class AutomationEvent(str, Enum):
    DISPUTE_CREATED = "dispute.created"
    HIGH_PRIORITY = "dispute.high_priority"
    EVIDENCE_MISSING = "evidence.missing"
    EVIDENCE_READY_FOR_REVIEW = "evidence.ready_for_review"
    DEADLINE_APPROACHING = "dispute.deadline_approaching"
    SUBMITTED = "dispute.submitted"


def mask_webhook_url(url: str | None) -> str:
    """Mask sensitive tokens in Zapier Catch Hook URL for display and safe logging."""
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split("/") if p]
        if len(path_parts) >= 2:
            last_part = path_parts[-1]
            masked_last = last_part[:3] + "..." + last_part[-3:] if len(last_part) > 6 else "..."
            return f"{parsed.scheme}://{parsed.netloc}/.../{masked_last}"
        return f"{parsed.scheme}://{parsed.netloc}/..."
    except Exception:
        return "https://hooks.zapier.com/..."


def sanitize_payload(data: Mapping[str, Any]) -> dict[str, Any]:
    """Strip full document binaries, customer credentials, and sensitive private fields.

    Only operational dispute metadata is transmitted to third-party automation tools.
    """
    blocked_keys = {
        "raw_text", "stored_path", "client_secret", "access_token",
        "credit_card", "card_number", "cvv", "ssn", "password",
        "file_content", "binary_data", "pdf_bytes",
    }
    safe: dict[str, Any] = {}
    for k, v in data.items():
        if k.lower() in blocked_keys:
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            # Mask potential customer email address
            if k == "customer_email" and isinstance(v, str) and "@" in v:
                parts = v.split("@")
                safe[k] = parts[0][:2] + "***@" + parts[1]
            else:
                safe[k] = v
        elif isinstance(v, (list, tuple)):
            # Allow list of strings (e.g. key_facts, missing_fields)
            safe[k] = [str(item) for item in v[:20] if not isinstance(item, (dict, list))]
        elif isinstance(v, dict):
            # Recursively sanitize nested structures
            safe[k] = sanitize_payload(v)
    return safe


class WebhookPayload(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event: AutomationEvent
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: str = "1"
    data: dict[str, Any]
    test_mode: bool = False


class DeliveryResult(BaseModel):
    event_id: str
    event: AutomationEvent
    delivered: bool
    status_code: int | None = None
    error: str | None = None
    attempts: int = 1
    response_time_ms: float = 0.0


class ZapierWebhookService:
    """POST event payloads to the merchant's Zapier Catch Hook URL with retries & logging."""

    # In-memory deduplication window: (event, dispute_id) -> timestamp
    _recent_events: dict[str, float] = {}

    def __init__(
        self,
        webhook_url: str | None,
        *,
        timeout_seconds: float = 8.0,
        max_retries: int = 2,
        enabled_events: set[AutomationEvent] | None = None,
        http: httpx.Client | None = None,
        db: Database | None = None,
        dedup_window_seconds: float = 30.0,
    ):
        self.webhook_url = webhook_url.strip() if webhook_url else ""
        if self.webhook_url and urlparse(self.webhook_url).scheme != "https":
            raise ValueError("Zapier webhook URL must use HTTPS")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, max_retries)
        self.enabled_events = enabled_events if enabled_events is not None else set(AutomationEvent)
        self._http = http or httpx.Client(timeout=timeout_seconds)
        self._owns_http = http is None
        self.db = db
        self.dedup_window_seconds = dedup_window_seconds

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def _is_duplicate(self, event: AutomationEvent, dispute_id: str | None) -> bool:
        if not dispute_id:
            return False
        key = f"{event.value}:{dispute_id}"
        now = time.monotonic()
        last_time = self._recent_events.get(key)
        if last_time and (now - last_time) < self.dedup_window_seconds:
            return True
        self._recent_events[key] = now
        # Prune old cache entries
        if len(self._recent_events) > 500:
            cutoff = now - self.dedup_window_seconds
            self._recent_events = {k: v for k, v in self._recent_events.items() if v >= cutoff}
        return False

    def emit(
        self,
        event: AutomationEvent,
        data: Mapping[str, Any],
        *,
        test_mode: bool = False,
    ) -> DeliveryResult:
        dispute_id = str(data.get("dispute_id") or "")
        payload = WebhookPayload(
            event=event,
            data=sanitize_payload(data),
            test_mode=test_mode,
        )

        # 1. Check if event is enabled
        if event not in self.enabled_events:
            logger.info("Automation event disabled: event=%s event_id=%s", event.value, payload.event_id)
            return DeliveryResult(
                event_id=payload.event_id,
                event=event,
                delivered=False,
                error="disabled",
            )

        # 2. Check if webhook URL is configured
        if not self.webhook_url:
            logger.info("Automation event not delivered: webhook not configured event=%s event_id=%s",
                        event.value, payload.event_id)
            return DeliveryResult(
                event_id=payload.event_id,
                event=event,
                delivered=False,
                error="webhook_not_configured",
            )

        # 3. Deduplication check (skip for test pings)
        if not test_mode and dispute_id and self._is_duplicate(event, dispute_id):
            logger.info("Automation event duplicate suppressed: event=%s dispute_id=%s", event.value, dispute_id)
            return DeliveryResult(
                event_id=payload.event_id,
                event=event,
                delivered=False,
                error="duplicate_event_suppressed",
            )

        # 4. Transmission with Retry Logic (exponential backoff for 5xx and timeouts)
        attempts = 0
        max_attempts = 1 + self.max_retries
        delivered = False
        status_code: int | None = None
        last_error: str | None = None
        total_time_ms = 0.0

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "ResolveIQ-Automation/3.0",
        }
        body_json = payload.model_dump(mode="json")

        for attempt in range(1, max_attempts + 1):
            attempts = attempt
            t0 = time.monotonic()
            try:
                response = self._http.post(
                    self.webhook_url,
                    json=body_json,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
                elapsed_ms = (time.monotonic() - t0) * 1000.0
                total_time_ms += elapsed_ms
                status_code = response.status_code

                if 200 <= status_code < 300:
                    delivered = True
                    last_error = None
                    logger.info("Automation delivered event=%s event_id=%s status=%s attempt=%s",
                                event.value, payload.event_id, status_code, attempt)
                    break
                elif 400 <= status_code < 500:
                    # Client errors (e.g. 400 bad payload or 404 webhook deleted) - Do not retry
                    delivered = False
                    last_error = f"webhook_client_error_{status_code}"
                    logger.warning("Zapier Catch Hook rejected request with HTTP %s; aborting retries", status_code)
                    break
                else:
                    # 5xx server error from Zapier
                    delivered = False
                    last_error = f"webhook_http_error_{status_code}"
                    logger.warning("Zapier Catch Hook returned HTTP %s on attempt %s", status_code, attempt)

            except httpx.TimeoutException:
                elapsed_ms = (time.monotonic() - t0) * 1000.0
                total_time_ms += elapsed_ms
                last_error = "timeout"
                logger.warning("Zapier Catch Hook timed out on attempt %s", attempt)
            except httpx.HTTPError as exc:
                elapsed_ms = (time.monotonic() - t0) * 1000.0
                total_time_ms += elapsed_ms
                last_error = "transport_error"
                logger.warning("Zapier transport error on attempt %s: %s", attempt, type(exc).__name__)

            # Backoff before next attempt if retrying
            if attempt < max_attempts and not delivered:
                backoff_seconds = min(2.0, 0.25 * (2 ** (attempt - 1)))
                time.sleep(backoff_seconds)

        result = DeliveryResult(
            event_id=payload.event_id,
            event=event,
            delivered=delivered,
            status_code=status_code,
            error=last_error,
            attempts=attempts,
            response_time_ms=round(total_time_ms, 1),
        )

        # 5. Persist delivery in SQLite history if database is available
        if self.db:
            try:
                self.db.save_webhook_delivery({
                    "event_id": payload.event_id,
                    "event_name": event.value,
                    "dispute_id": dispute_id or None,
                    "payload": body_json,
                    "target_url_masked": mask_webhook_url(self.webhook_url),
                    "delivered": delivered,
                    "status_code": status_code,
                    "error": last_error,
                    "attempts": attempts,
                    "response_time_ms": result.response_time_ms,
                })
                # Record in unified audit history
                self.db.log_audit(
                    dispute_id=dispute_id or "SYSTEM",
                    action="ZAPIER_WEBHOOK_DELIVERED" if delivered else "ZAPIER_WEBHOOK_FAILED",
                    actor="zapier_service",
                    details={
                        "event": event.value,
                        "event_id": payload.event_id,
                        "delivered": delivered,
                        "status_code": status_code,
                        "attempts": attempts,
                        "error": last_error,
                        "target_url": mask_webhook_url(self.webhook_url),
                    },
                )
            except Exception as exc:
                logger.warning("Could not record webhook delivery history in DB: %s", exc)

        return result


def service_from_environment(
    enabled_events: set[AutomationEvent] | None = None,
    db: Database | None = None,
) -> ZapierWebhookService:
    """Instantiate service favoring settings stored in DB, falling back to environment."""
    import os
    webhook_url = ""
    timeout = 8.0
    retries = 2

    if db:
        try:
            settings_data = db.get_automation_settings()
            webhook_url = settings_data.get("webhook_url", "")
            timeout = float(settings_data.get("timeout_seconds", 8.0))
            retries = int(settings_data.get("max_retries", 2))
            if enabled_events is None and settings_data.get("enabled_events"):
                enabled_events = {
                    AutomationEvent(ev)
                    for ev in settings_data["enabled_events"]
                    if ev in [e.value for e in AutomationEvent]
                }
        except Exception as exc:
            logger.info("Using env variables for Zapier service (DB settings lookup: %s)", exc)

    if not webhook_url:
        try:
            from backend.config import get_settings
            st = get_settings()
            webhook_url = st.zapier_webhook_url
            timeout = st.zapier_webhook_timeout_seconds
        except Exception:
            webhook_url = os.getenv("ZAPIER_WEBHOOK_URL", "")
            timeout = float(os.getenv("ZAPIER_WEBHOOK_TIMEOUT_SECONDS", "8"))
    if not webhook_url:
        webhook_url = os.getenv("ZAPIER_WEBHOOK_URL", "")

    return ZapierWebhookService(
        webhook_url=webhook_url,
        timeout_seconds=timeout,
        max_retries=retries,
        enabled_events=enabled_events,
        db=db,
    )


def emit_submission_completed(
    dispute_id: str,
    *,
    enabled_events: set[AutomationEvent] | None = None,
    db: Database | None = None,
) -> DeliveryResult:
    """Call only after an explicit merchant approved submission succeeds."""
    service = service_from_environment(enabled_events, db=db)
    try:
        return service.emit(AutomationEvent.SUBMITTED, {"dispute_id": dispute_id})
    finally:
        service.close()
