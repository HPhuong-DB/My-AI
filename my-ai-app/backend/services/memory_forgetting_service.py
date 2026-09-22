"""Targeted forgetting policies for persistent memory stores."""

from __future__ import annotations

from typing import Any

from core.database import DatabaseUnavailable, get_db_connection
from core.migrations import ensure_schema


def forget_expired_memories(user_id: str | None = None, *, strict: bool = False) -> dict[str, Any]:
    """Soft-forget only expired rows and preserve an auditable reason."""
    conn = get_db_connection()
    if not conn:
        if strict:
            raise DatabaseUnavailable("Không thể chạy chính sách quên")
        return {"ok": False, "reason": "database_unavailable", "forgotten": {}}

    cursor = None
    try:
        ensure_schema(conn)

        cursor = conn.cursor()
        forgotten: dict[str, int] = {}
        stores = {
            "personal": ("core_memories", "is_active = 0, "),
            "knowledge": ("personal_knowledge", ""),
            "experiences": ("agent_experiences", ""),
            "sessions": ("conversation_sessions", ""),
            "episodes": ("episodic_memories", ""),
        }
        for name, (table, extra_set) in stores.items():
            where = "forgotten_at IS NULL AND expires_at IS NOT NULL AND expires_at <= CURRENT_TIMESTAMP"
            params: tuple[Any, ...] = ()
            if user_id is not None:
                where += " AND user_id = %s"
                params = (user_id,)
            cursor.execute(
                f"UPDATE {table} SET {extra_set}forgotten_at = CURRENT_TIMESTAMP, "
                f"forget_reason = 'expired' WHERE {where}",
                params,
            )
            forgotten[name] = max(0, int(cursor.rowcount or 0))
        conn.commit()
        return {"ok": True, "user_id": user_id, "forgotten": forgotten, "total": sum(forgotten.values())}
    except Exception as exc:
        conn.rollback()
        if strict:
            raise DatabaseUnavailable("Không thể chạy chính sách quên") from exc
        return {"ok": False, "reason": type(exc).__name__, "forgotten": {}}
    finally:
        if cursor is not None:
            cursor.close()
        conn.close()
