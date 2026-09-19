"""Consent and privacy audit controls for perception features."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


class Permission:
    MICROPHONE = "microphone"
    SCREEN = "screen"
    DOCUMENT = "document"
    IMAGE = "image"


CAPTURE_PERMISSIONS = frozenset({Permission.MICROPHONE, Permission.SCREEN})
ALL_PERMISSIONS = frozenset({Permission.MICROPHONE, Permission.SCREEN, Permission.DOCUMENT, Permission.IMAGE})


@dataclass(frozen=True, slots=True)
class PrivacyAuditEntry:
    user_id: str
    action: str
    permission: str
    created_at: datetime
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "action": self.action,
            "permission": self.permission,
            "created_at": self.created_at.isoformat(),
            "metadata": dict(self.metadata),
        }


class PrivacyManager:
    """Keep consent in memory and audit only metadata, never captured content."""

    def __init__(self, *, max_audit_entries: int = 500) -> None:
        self._consents: dict[str, dict[str, bool]] = defaultdict(dict)
        self._audit: deque[PrivacyAuditEntry] = deque(maxlen=max_audit_entries)

    @staticmethod
    def _validate(user_id: str, permission: str) -> None:
        if not user_id or not user_id.strip() or len(user_id) > 100:
            raise ValueError("user_id không hợp lệ")
        if permission not in ALL_PERMISSIONS:
            raise ValueError(f"Permission không hợp lệ: {permission}")

    def _record(self, user_id: str, action: str, permission: str, **metadata: Any) -> None:
        self._audit.append(
            PrivacyAuditEntry(
                user_id=user_id,
                action=action,
                permission=permission,
                created_at=datetime.now(timezone.utc),
                metadata=metadata,
            )
        )

    def set_consent(self, user_id: str, permission: str, granted: bool) -> None:
        self._validate(user_id, permission)
        self._consents[user_id][permission] = bool(granted)
        self._record(user_id, "consent_granted" if granted else "consent_revoked", permission)

    def is_allowed(self, user_id: str, permission: str) -> bool:
        self._validate(user_id, permission)
        return bool(self._consents[user_id].get(permission, False))

    def require(self, user_id: str, permission: str) -> bool:
        allowed = self.is_allowed(user_id, permission)
        if not allowed:
            self._record(user_id, "capture_denied", permission)
        return allowed

    def record_capture(self, user_id: str, permission: str, **metadata: Any) -> None:
        self._validate(user_id, permission)
        safe_metadata = {
            key: value
            for key, value in metadata.items()
            if key in {"content_type", "document_type", "char_count", "width", "height"}
        }
        self._record(user_id, "capture_used", permission, **safe_metadata)

    def get_consents(self, user_id: str) -> dict[str, bool]:
        if not user_id or not user_id.strip() or len(user_id) > 100:
            raise ValueError("user_id không hợp lệ")
        return {permission: bool(self._consents[user_id].get(permission, False)) for permission in ALL_PERMISSIONS}

    def get_audit(self, user_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        if not user_id or not user_id.strip() or len(user_id) > 100:
            raise ValueError("user_id không hợp lệ")
        return [entry.to_dict() for entry in list(self._audit)[-max(1, min(limit, 100)):] if entry.user_id == user_id]

    def revoke_capture_permissions(self) -> None:
        for user_id, permissions in self._consents.items():
            for permission in CAPTURE_PERMISSIONS:
                if permissions.get(permission):
                    permissions[permission] = False
                    self._record(user_id, "emergency_revoke", permission)
