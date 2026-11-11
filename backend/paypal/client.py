"""Authenticated PayPal REST client with OAuth token caching, auto-refresh on 401,

robust error handling, dispute actions parser, and audit logging support.
"""
from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import quote

import httpx

from backend.config import Settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Exception Hierarchy
# ---------------------------------------------------------------------

class PayPalAPIError(RuntimeError):
    """Base exception for all PayPal REST API errors."""

    def __init__(
        self,
        status_code: int,
        message: str,
        request_id: str | None = None,
        details: Any = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.request_id = request_id
        self.details = details


class PayPalAuthError(PayPalAPIError):
    """Raised on OAuth token acquisition, refresh, or authorization failure."""

    def __init__(
        self,
        message: str = "PayPal authentication failed",
        status_code: int = 401,
        request_id: str | None = None,
    ):
        super().__init__(status_code=status_code, message=message, request_id=request_id)


class PayPalRateLimitError(PayPalAPIError):
    """Raised when PayPal responds with HTTP 429 Too Many Requests."""

    def __init__(
        self,
        message: str = "PayPal API rate limit exceeded",
        request_id: str | None = None,
        retry_after: int | None = None,
    ):
        super().__init__(status_code=429, message=message, request_id=request_id)
        self.retry_after = retry_after


class PayPalTimeoutError(PayPalAPIError):
    """Raised when a PayPal API request or gateway times out (HTTP 504)."""

    def __init__(
        self,
        message: str = "PayPal API request timed out",
        request_id: str | None = None,
    ):
        super().__init__(status_code=504, message=message, request_id=request_id)


class PayPalNotFoundError(PayPalAPIError):
    """Raised when a PayPal resource is not found (HTTP 404)."""

    def __init__(
        self,
        message: str = "PayPal resource not found",
        request_id: str | None = None,
    ):
        super().__init__(status_code=404, message=message, request_id=request_id)


# ---------------------------------------------------------------------
# Dispute Requirements & Supported Actions Parser
# ---------------------------------------------------------------------

def parse_dispute_requirements(dispute_data: dict[str, Any]) -> dict[str, Any]:
    """Parse dispute details to determine required evidence types and supported actions.

    Extracts allowed response options from the PayPal dispute schema, provides
    domain-specific evidence guidance, and determines actionable merchant steps.
    """
    reason = (
        dispute_data.get("reason")
        or dispute_data.get("dispute_reason")
        or "UNKNOWN"
    )
    allowed_options = dispute_data.get("allowed_response_options") or []
    due_date = dispute_data.get("seller_response_due_date")
    status = dispute_data.get("status", "UNKNOWN")
    stage = dispute_data.get("dispute_life_cycle_stage", "UNKNOWN")
    state = dispute_data.get("dispute_state", "UNKNOWN")

    # Domain specific guidance and recommended evidence categories
    if "NOT_RECEIVED" in reason:
        recommended = [
            "PROOF_OF_FULFILLMENT",
            "PROOF_OF_DELIVERY",
            "PROOF_OF_REFUND",
            "ADDITIONAL_INFORMATION_OF_ITEM",
        ]
        guidance = (
            "For Item Not Received claims, submit online verifiable carrier tracking showing "
            "delivery to the buyer's address. Signature confirmation is required for orders over $750."
        )
        actions = [
            "Submit Carrier Tracking",
            "Provide Delivery Confirmation",
            "Provide Proof of Refund",
            "Accept Claim",
        ]
    elif "NOT_AS_DESCRIBED" in reason:
        recommended = [
            "PROOF_OF_REFUND",
            "PROOF_OF_RESHIPMENT",
            "MERCHANT_TERMS_AND_CONDITIONS",
            "ADDITIONAL_INFORMATION_OF_ITEM",
        ]
        guidance = (
            "For Not as Described claims, provide item specifications, proof of correct shipment, "
            "published store return policies, or return merchandise authorization (RMA) information."
        )
        actions = [
            "Submit Item Specifications",
            "Provide Merchant Terms & Return Policy",
            "Offer Settlement / Replacement",
            "Accept Claim",
        ]
    elif "UNAUTHORISED" in reason:
        recommended = [
            "PROOF_OF_FULFILLMENT",
            "PROOF_OF_DELIVERY",
            "BUYER_ID",
            "CONFIRMATION_OR_AUTHENTICATION",
        ]
        guidance = (
            "For Unauthorized activity claims, provide proof of delivery to the verified PayPal "
            "address, buyer authentication logs, IP timestamps, or 3D Secure confirmation."
        )
        actions = [
            "Submit Verified Fulfillment Proof",
            "Provide Authentication Logs",
            "Accept Claim",
        ]
    else:
        recommended = ["PROOF_OF_FULFILLMENT", "ADDITIONAL_INFORMATION_OF_ITEM", "NOTES"]
        guidance = (
            "Review customer complaint details and submit documentation validating transaction "
            "fulfillment, communication logs, or refund processing."
        )
        actions = ["Provide Supporting Evidence", "Accept Claim"]

    can_submit_evidence = "PROVIDE_EVIDENCE" in allowed_options or not allowed_options
    can_accept_claim = "ACCEPT_CLAIM" in allowed_options or not allowed_options
    can_make_offer = "MAKE_OFFER_TO_RESOLVE" in allowed_options

    return {
        "dispute_id": dispute_data.get("dispute_id", ""),
        "reason": reason,
        "status": status,
        "stage": stage,
        "state": state,
        "seller_response_due_date": due_date,
        "allowed_response_options": allowed_options,
        "can_submit_evidence": can_submit_evidence,
        "can_accept_claim": can_accept_claim,
        "can_make_offer": can_make_offer,
        "recommended_evidence_types": recommended,
        "supported_actions": actions,
        "guidance": guidance,
    }


# ---------------------------------------------------------------------
# PayPal REST Client
# ---------------------------------------------------------------------

class PayPalClient:
    """Authenticated PayPal REST API Client for Sandbox and Live endpoints."""

    def __init__(self, settings: Settings, http: httpx.Client | None = None):
        self.settings = settings
        self._http = http or httpx.Client(timeout=settings.paypal_timeout_seconds)
        self._owns_http = http is None
        self._token: str | None = None
        self._token_expires_at = 0.0

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def _access_token(self, force_refresh: bool = False) -> str:
        """Acquire or return cached OAuth 2.0 Bearer token via Client Credentials grant."""
        if not self.settings.paypal_client_id or not self.settings.paypal_client_secret:
            raise PayPalAuthError(
                "PayPal credentials not configured on the backend. "
                "Please configure PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET.",
                status_code=401,
            )

        if not force_refresh and self._token and time.monotonic() < self._token_expires_at - 30:
            return self._token

        token_url = f"{self.settings.paypal_base_url.rstrip('/')}/v1/oauth2/token"
        try:
            response = self._http.post(
                token_url,
                auth=(self.settings.paypal_client_id, self.settings.paypal_client_secret),
                data={"grant_type": "client_credentials"},
                headers={"Accept": "application/json", "Accept-Language": "en_US"},
            )
            request_id = response.headers.get("PayPal-Debug-Id")

            if response.status_code in (401, 403):
                logger.warning("PayPal OAuth credentials rejected (HTTP %s, debug_id=%s)", response.status_code, request_id)
                raise PayPalAuthError(
                    f"PayPal OAuth credentials rejected (HTTP {response.status_code})",
                    status_code=response.status_code,
                    request_id=request_id,
                )

            response.raise_for_status()
            payload = response.json()
            self._token = payload["access_token"]
            expires_in = int(payload.get("expires_in", 32400))
            self._token_expires_at = time.monotonic() + expires_in
            logger.info("PayPal OAuth token acquired; expires_in=%s seconds", expires_in)
            return self._token
        except PayPalAuthError:
            raise
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            logger.warning("PayPal OAuth request failed (%s)", type(exc).__name__)
            raise PayPalAPIError(502, "PayPal authentication failed") from exc

    def check_connection(self) -> dict[str, Any]:
        """Verify PayPal connectivity, credentials, and token validity."""
        if not self.settings.paypal_client_id or not self.settings.paypal_client_secret:
            return {
                "connected": False,
                "configured": False,
                "mode": "demo",
                "base_url": self.settings.paypal_base_url,
                "message": "PayPal credentials not configured in environment. Operating in demo mode.",
                "token_valid": False,
                "token_expires_in_seconds": None,
            }

        try:
            self._access_token()
            remaining_seconds = max(0, int(self._token_expires_at - time.monotonic()))
            return {
                "connected": True,
                "configured": True,
                "mode": "sandbox",
                "base_url": self.settings.paypal_base_url,
                "message": "Successfully authenticated with PayPal Sandbox API.",
                "token_valid": True,
                "token_expires_in_seconds": remaining_seconds,
            }
        except PayPalAPIError as exc:
            return {
                "connected": False,
                "configured": True,
                "mode": "demo_fallback",
                "base_url": self.settings.paypal_base_url,
                "message": f"PayPal authentication error: {exc}",
                "token_valid": False,
                "token_expires_in_seconds": None,
                "request_id": exc.request_id,
            }
        except Exception as exc:
            return {
                "connected": False,
                "configured": True,
                "mode": "demo_fallback",
                "base_url": self.settings.paypal_base_url,
                "message": f"PayPal connection failed: {exc}",
                "token_valid": False,
                "token_expires_in_seconds": None,
            }

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        retry_on_401: bool = True,
    ) -> dict[str, Any]:
        """Perform an authenticated request to PayPal REST API with 401 re-authentication retry."""
        url = f"{self.settings.paypal_base_url.rstrip('/')}/{path.lstrip('/')}"
        token = self._access_token()

        try:
            response = self._http.request(
                method,
                url,
                params=params,
                json=json,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
            )

            # Auto-refresh token and retry once if 401 Unauthorized is returned
            if response.status_code == 401 and retry_on_401:
                logger.info("PayPal API returned 401 Unauthorized. Refreshing token and retrying...")
                self._token = None
                self._token_expires_at = 0.0
                return self.request(method, path, params=params, json=json, retry_on_401=False)

            if response.is_error:
                request_id = response.headers.get("PayPal-Debug-Id")
                logger.warning(
                    "PayPal API returned status=%s debug_id=%s path=%s",
                    response.status_code,
                    request_id,
                    path,
                )

                if response.status_code == 401:
                    raise PayPalAuthError(
                        message="PayPal authentication failed: Invalid or expired token",
                        status_code=401,
                        request_id=request_id,
                    )
                elif response.status_code == 429:
                    retry_after_str = response.headers.get("Retry-After")
                    retry_after = int(retry_after_str) if retry_after_str and retry_after_str.isdigit() else None
                    raise PayPalRateLimitError(
                        message=f"PayPal API rate limit exceeded. Retry after {retry_after or 'a few'} seconds.",
                        request_id=request_id,
                        retry_after=retry_after,
                    )
                elif response.status_code == 404:
                    raise PayPalNotFoundError(
                        message=f"PayPal resource not found at {path}",
                        request_id=request_id,
                    )
                elif response.status_code == 504:
                    raise PayPalTimeoutError(
                        message="PayPal gateway timed out",
                        request_id=request_id,
                    )
                else:
                    # Sanitize message to never leak raw response body secrets
                    raise PayPalAPIError(
                        status_code=response.status_code,
                        message=f"PayPal API request failed ({response.status_code})",
                        request_id=request_id,
                    )

            if response.status_code == 204 or not response.content:
                return {}
            return response.json()
        except httpx.TimeoutException as exc:
            logger.warning("PayPal API request timed out")
            raise PayPalTimeoutError("PayPal API request timed out") from exc
        except (
            PayPalAPIError,
            PayPalAuthError,
            PayPalRateLimitError,
            PayPalTimeoutError,
            PayPalNotFoundError,
        ):
            raise
        except httpx.HTTPError as exc:
            logger.warning("PayPal API transport error (%s)", type(exc).__name__)
            raise PayPalAPIError(502, "PayPal API transport error") from exc

    def list_transactions(
        self, start_date: str, end_date: str, **filters: Any
    ) -> dict[str, Any]:
        """Search transactions via PayPal Transaction Search API.

        Requires RFC3339 start_date and end_date (max span 31 days).
        """
        params = {"start_date": start_date, "end_date": end_date, **filters}
        return self.request("GET", "/v1/reporting/transactions", params=params)

    def get_transaction(self, transaction_id: str) -> dict[str, Any]:
        """Fetch details of a single transaction if supported."""
        return self.request("GET", f"/v1/reporting/transactions/{quote(transaction_id, safe='')}")

    def list_disputes(self, **filters: Any) -> dict[str, Any]:
        """List customer disputes from PayPal."""
        return self.request("GET", "/v1/customer/disputes", params=filters)

    def get_dispute(self, dispute_id: str) -> dict[str, Any]:
        """Fetch full details of a specific dispute."""
        return self.request("GET", f"/v1/customer/disputes/{quote(dispute_id, safe='')}")

    def submit_evidence(self, dispute_id: str, evidence: dict[str, Any]) -> dict[str, Any]:
        """Submit evidence for a dispute to PayPal Resolution Center.

        Uses the official `/v1/customer/disputes/{dispute_id}/provide-evidence` endpoint.
        Returns the response dictionary or confirmation.
        """
        path = f"/v1/customer/disputes/{quote(dispute_id, safe='')}/provide-evidence"
        return self.request("POST", path, json=evidence)
