"""In-memory sliding-window rate limiter for sensitive API endpoints.

Prevents brute-force, denial-of-service, and resource-exhaustion attacks against
AI inference, file upload, webhook dispatch, and PayPal submission operations.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from typing import Callable

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)


class SlidingWindowRateLimiter:
    """Thread-safe sliding-window rate limiter."""

    def __init__(self):
        self._lock = threading.Lock()
        # key -> list of float timestamps
        self._history: dict[str, list[float]] = defaultdict(list)

    def is_allowed(
        self,
        key: str,
        max_requests: int,
        window_seconds: float,
    ) -> tuple[bool, int, float]:
        """Check if request is permitted within the sliding time window.

        Returns: (allowed: bool, remaining_requests: int, retry_after_seconds: float)
        """
        now = time.monotonic()
        cutoff = now - window_seconds

        with self._lock:
            timestamps = self._history[key]
            # Prune older entries outside the window
            timestamps = [t for t in timestamps if t > cutoff]

            if len(timestamps) >= max_requests:
                # Calculate when the oldest request in the window expires
                oldest = timestamps[0]
                retry_after = max(1.0, round(oldest + window_seconds - now, 1))
                self._history[key] = timestamps
                return False, 0, retry_after

            # Record this request
            timestamps.append(now)
            self._history[key] = timestamps
            remaining = max(0, max_requests - len(timestamps))
            return True, remaining, 0.0

    def reset(self) -> None:
        """Reset all rate limiter state (useful for test isolation)."""
        with self._lock:
            self._history.clear()


# Global rate limiter instance
_global_limiter = SlidingWindowRateLimiter()


def get_client_identifier(request: Request) -> str:
    """Extract a consistent client identifier from the request."""
    # Check X-Forwarded-For if behind a reverse proxy
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "127.0.0.1"

    # Incorporate merchant header if provided
    merchant_id = request.headers.get("X-Merchant-Id", "")
    if merchant_id:
        return f"{client_ip}:{merchant_id}"
    return client_ip


class RateLimit:
    """FastAPI route dependency for rate limiting."""

    def __init__(
        self,
        max_requests: int,
        window_seconds: float = 60.0,
        scope: str = "default",
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.scope = scope

    async def __call__(self, request: Request) -> None:
        # Check if rate limiting is globally disabled in configuration
        from backend.config import get_settings
        settings = get_settings()
        if not getattr(settings, "rate_limit_enabled", True):
            return

        client_id = get_client_identifier(request)
        rate_key = f"{self.scope}:{client_id}"

        allowed, remaining, retry_after = _global_limiter.is_allowed(
            rate_key,
            max_requests=self.max_requests,
            window_seconds=self.window_seconds,
        )

        if not allowed:
            logger.warning(
                "Rate limit exceeded for %s on scope '%s'. Limit: %s/%ss. Retry after %ss.",
                client_id, self.scope, self.max_requests, self.window_seconds, retry_after,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded on {self.scope}. Too many requests.",
                headers={
                    "Retry-After": str(int(retry_after)),
                    "X-RateLimit-Limit": str(self.max_requests),
                    "X-RateLimit-Remaining": "0",
                },
            )


def reset_rate_limits() -> None:
    """Public helper to reset all rate limits during testing."""
    _global_limiter.reset()
