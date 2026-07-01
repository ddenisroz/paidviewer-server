"""Helpers for safe logging of sensitive identifiers."""

from typing import Optional


def mask_session_id(session_id: Optional[str], visible_prefix: int = 8) -> str:
    """
    Return masked session identifier for logs.

    Keeps only a short prefix to preserve traceability while avoiding full token leaks.
    """
    if not session_id:
        return "NONE"

    value = str(session_id).strip()
    if not value:
        return "NONE"

    if len(value) <= visible_prefix:
        return "***"

    return f"{value[:visible_prefix]}..."

