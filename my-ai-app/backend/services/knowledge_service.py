"""Long-term memory views: personal facts, researched knowledge and experiences."""

from __future__ import annotations

import json
import os
from typing import Any

from core.database import get_db_connection
from services.memory_metadata import clamp_score, expiry_from_env, normalize_expiry
from services.memory_service import get_recent_memories
from services.research_service import list_knowledge

DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "default")


def _ensure_experience_table(conn) -> None:
    if not conn:
        return
    from core.migrations import ensure_schema

    ensure_schema(conn)


def save_experience(
    user_id: str = DEFAULT_USER_ID,
    title: str = "",
    lesson: str = "",
    context: str = "",
    source_type: str = "goal",
    source_id: int | None = None,
    *,
    source_ref: str | None = None,
    confidence: float = 0.80,
    importance: float = 0.75,
    expires_at: Any = None,
) -> dict[str, Any] | None:
    title = str(title or "").strip()
    lesson = str(lesson or "").strip()
    if not title or not lesson:
        raise ValueError("Experience cần title và lesson")
    source_type = str(source_type or "goal")[:50]
    confidence = clamp_score(confidence, 0.80)
    importance = clamp_score(importance, 0.75)
    source_ref = str(source_ref)[:255] if source_ref not in (None, "") else (str(source_id) if source_id is not None else None)
    expires_at = normalize_expiry(expires_at) if expires_at is not None else expiry_from_env("EXPERIENCE_TTL_DAYS", 0)
    conn = get_db_connection()
    if not conn:
        return None
    cursor = None
    try:
        _ensure_experience_table(conn)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "INSERT INTO agent_experiences "
            "(user_id, title, lesson, context, source_type, source_id, source_ref, confidence, importance, expires_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (user_id, title[:255], lesson, str(context or ""), source_type, source_id, source_ref, confidence, importance, expires_at),
        )
        experience_id = cursor.lastrowid
        conn.commit()
        return {
            "id": experience_id,
            "user_id": user_id,
            "title": title,
            "lesson": lesson,
            "context": context,
            "source_type": source_type,
            "source_id": source_id,
            "source_ref": source_ref,
            "confidence": confidence,
            "importance": importance,
            "expires_at": expires_at,
        }
    except Exception as exc:
        print(f"Lỗi lưu experience: {exc}")
        return None
    finally:
        if conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def list_experiences(user_id: str = DEFAULT_USER_ID, limit: int = 20) -> list[dict[str, Any]]:
    conn = get_db_connection()
    if not conn:
        return []
    cursor = None
    try:
        _ensure_experience_table(conn)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, user_id, title, lesson, context, source_type, source_id, source_ref, "
            "confidence, importance, expires_at, created_at FROM agent_experiences "
            "WHERE user_id = %s AND forgotten_at IS NULL "
            "AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP) "
            "ORDER BY id DESC LIMIT %s",
            (user_id, max(1, min(int(limit), 50))),
        )
        return [dict(item) for item in (cursor.fetchall() or [])]
    finally:
        if conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def get_long_term_memory(user_id: str = DEFAULT_USER_ID, query: str = "", limit: int = 10) -> dict[str, Any]:
    """Return intentionally separated memory categories for prompt consumers."""
    normalized = str(query or "").strip().lower()
    personal = get_recent_memories(limit=limit, user_id=user_id)
    knowledge = list_knowledge(user_id, limit)
    experiences = list_experiences(user_id, limit)
    if normalized:
        personal = [item for item in personal if normalized in str(item.get("fact", "")).lower()]
        knowledge = [item for item in knowledge if normalized in json.dumps(item, ensure_ascii=False).lower()]
        experiences = [item for item in experiences if normalized in json.dumps(item, ensure_ascii=False).lower()]
    return {"user_id": user_id, "personal": personal[:limit], "knowledge": knowledge[:limit], "experiences": experiences[:limit]}
