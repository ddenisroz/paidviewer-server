"""Token helpers for worker control-plane auth."""

from __future__ import annotations

import hashlib
import secrets


def hash_secret(raw_value: str) -> str:
    """Return a stable hash for one-time pairing codes and worker auth tokens."""
    return hashlib.sha256(str(raw_value or "").encode("utf-8")).hexdigest()


def generate_secret_urlsafe(length: int = 32) -> str:
    """Generate a URL-safe random secret."""
    return secrets.token_urlsafe(length)


def generate_pairing_code() -> str:
    """Generate a readable one-time pairing code."""
    chunks = [secrets.token_hex(2).upper() for _ in range(3)]
    return f"PVW-{'-'.join(chunks)}"


def generate_worker_key() -> str:
    """Generate a stable public worker key."""
    return f"wrk_{secrets.token_hex(8)}"
