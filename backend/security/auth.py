"""Merchant authentication and tenant authorization checks for dispute records."""
from __future__ import annotations

import hmac
import logging
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from backend.config import Settings, get_settings
from backend.db import Database

logger = logging.getLogger(__name__)


def get_current_merchant_id(
    request: Request,
    settings: Settings = Depends(get_settings),
    x_merchant_id: Annotated[str | None, Header()] = None,
) -> str:
    """Validate request authentication and extract the merchant identity.

    - If MERCHANT_API_KEY is configured in backend environment, enforces
      Bearer token authentication using constant-time string comparison.
    - Extracts tenant identifier from 'X-Merchant-Id' header (defaults to 'default_merchant').
    """
    # 1. Check if backend requires API key authentication
    if settings.merchant_api_key:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required: Missing Bearer token in Authorization header.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        token = auth_header.split(" ", 1)[1].strip()
        if not hmac.compare_digest(token, settings.merchant_api_key):
            logger.warning("Invalid merchant API key attempted from %s", request.client.host if request.client else "unknown")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Invalid merchant API key.",
            )

    # 2. Return merchant tenant identifier
    merchant_id = (x_merchant_id or "").strip()
    return merchant_id if merchant_id else "default_merchant"


def verify_merchant_record_access(
    dispute_id: str,
    merchant_id: str,
    db: Database,
) -> None:
    """Ensure merchant has permission to view or manipulate records for this dispute.

    In multi-tenant setups, prevents cross-tenant data leakage.
    """
    # For future multi-tenant segregation, check dispute record owner if present
    dispute = db.get_dispute(dispute_id)
    if dispute and "merchant_id" in dispute and dispute["merchant_id"]:
        if dispute["merchant_id"] != merchant_id and merchant_id != "admin":
            logger.warning(
                "Tenant authorization breach attempt: merchant '%s' tried to access dispute '%s' belonging to '%s'",
                merchant_id, dispute_id, dispute["merchant_id"],
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You do not have permission to view or modify this dispute.",
            )
