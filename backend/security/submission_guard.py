"""Protection against concurrent and duplicate PayPal dispute submissions."""
from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Generator

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

# In-flight submission registry protected by a reentrant lock
_lock = threading.Lock()
_active_submissions: set[str] = set()


@contextmanager
def dispute_submission_lock(dispute_id: str) -> Generator[None, None, None]:
    """Prevent concurrent in-flight submissions for the exact same dispute ID.

    Raises HTTP 409 Conflict if another worker or thread is currently submitting
    evidence for the same dispute.
    """
    clean_id = str(dispute_id).strip()
    with _lock:
        if clean_id in _active_submissions:
            logger.warning("Concurrent submission attempt blocked for dispute '%s'", clean_id)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Dispute submission is already in progress for '{clean_id}'. Concurrent submission prevented.",
            )
        _active_submissions.add(clean_id)

    try:
        yield
    finally:
        with _lock:
            _active_submissions.discard(clean_id)


def reset_submission_locks() -> None:
    """Reset active in-flight locks (used for test isolation)."""
    with _lock:
        _active_submissions.clear()
