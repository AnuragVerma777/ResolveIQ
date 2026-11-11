"""Security sanitization utilities for path validation, filename sanitization,
PII/secret masking, and prompt-injection containment.
"""
from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4
from fastapi import HTTPException, status


def sanitize_filename(filename: str) -> str:
    """Sanitize uploaded filenames against path traversal and dangerous characters.

    Strips directory separators, null bytes, control characters, and leading dots.
    """
    if not filename or not filename.strip():
        return f"document_{uuid4().hex[:8]}.bin"

    # Remove null bytes and path separators (handles both POSIX / and Windows \)
    clean = filename.replace("\x00", "").replace("/", "_").replace("\\", "_")
    # Take basename only
    clean = Path(clean).name

    # Remove non-whitelisted characters
    clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", clean)
    # Strip leading dots or underscores to prevent hidden files or traversal tricks
    clean = clean.lstrip("._")

    if not clean or clean in {".", ".."}:
        return f"document_{uuid4().hex[:8]}.bin"

    # Truncate overly long filenames
    if len(clean) > 120:
        stem = Path(clean).stem[:100]
        suffix = Path(clean).suffix[:20]
        clean = f"{stem}{suffix}"

    return clean


def validate_safe_path(target: Path | str, base_dir: Path | str) -> Path:
    """Validate that target path strictly resolves inside base_dir without path traversal.

    Raises HTTPException 403 if target attempts to escape base_dir.
    """
    base_resolved = Path(base_dir).resolve()
    target_resolved = Path(target).resolve()

    try:
        if not target_resolved.is_relative_to(base_resolved):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Storage path traversal detected.",
            )
    except (ValueError, AttributeError):
        # Fallback check
        try:
            target_resolved.relative_to(base_resolved)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Storage path traversal detected.",
            )

    return target_resolved


def wrap_untrusted_text(content: str, label: str = "document_content") -> str:
    """Wrap untrusted user/merchant document content in isolated XML-like guardrail tags.

    Neutralizes prompt-injection attempts by escaping embedded closing tags and
    clearly bounding external untrusted text for LLM processors.
    """
    if not content:
        return f'<untrusted_content type="{label}">[EMPTY]</untrusted_content>'

    # Escape any closing guardrail tag within user content to prevent breakout
    safe_content = content.replace("</untrusted_content>", "&lt;/untrusted_content&gt;")
    safe_content = safe_content.replace("<untrusted_content", "&lt;untrusted_content")

    return (
        f'<untrusted_content type="{label}">\n'
        f'{safe_content}\n'
        f'</untrusted_content>'
    )


def mask_secret(val: str | None, show_chars: int = 4) -> str:
    """Mask credentials, tokens, or webhook secrets."""
    if not val:
        return ""
    s = str(val).strip()
    if len(s) <= show_chars + 2:
        return "****"
    half = show_chars // 2
    return f"{s[:half]}****{s[-half:]}"
