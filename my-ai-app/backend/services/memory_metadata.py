"""Shared validation and expiry helpers for persistent memory metadata."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any


def clamp_score(value: Any, default: float) -> float:
    """Return a stable 0..1 score even when old rows contain invalid values."""
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = float(default)
    return round(max(0.0, min(score, 1.0)), 2)


def normalize_expiry(value: Any) -> datetime | None:
    """Normalize an API/DB timestamp to the naive UTC form used by MySQL."""
    if value in (None, ""):
        return None
    parsed = value
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if not isinstance(parsed, datetime):
        raise ValueError("expires_at phải là thời gian ISO 8601 hợp lệ")
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def expiry_from_env(name: str, default_days: int) -> datetime | None:
    """Create an expiry from a day-based setting; zero means no expiry."""
    try:
        days = int(os.getenv(name, str(default_days)))
    except ValueError:
        days = default_days
    if days <= 0:
        return None
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=days)


def is_expired(value: Any, *, now: datetime | None = None) -> bool:
    try:
        expiry = normalize_expiry(value)
    except (TypeError, ValueError):
        return False
    if expiry is None:
        return False
    current = now or datetime.now(timezone.utc).replace(tzinfo=None)
    if current.tzinfo is not None:
        current = current.astimezone(timezone.utc).replace(tzinfo=None)
    return expiry <= current
