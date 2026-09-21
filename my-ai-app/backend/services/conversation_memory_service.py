"""Persistent session summaries and user-grounded episodic memories."""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

from core.database import DatabaseUnavailable, get_db_connection
from services.dialogue_context_service import normalize, tokens
from services.memory_metadata import expiry_from_env


DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "default")
_TOPIC_STOP_WORDS = {
    "ban", "cau", "huohuo", "minh", "toi", "to", "nguoi", "dung",
    "cho", "biet", "noi", "hoi", "lam", "sao", "the", "nao", "nhe",
    "nha", "di", "voi", "ve", "co", "can", "muon", "giup", "them",
    "dang", "da", "se", "vua",
}


def _ensure_tables(conn) -> None:
    from core.migrations import ensure_schema

    ensure_schema(conn)


def _clean_turn_text(value: str, limit: int) -> str:
    text = str(value or "").split("\n\n[TRA CỨU", 1)[0]
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _decode_summary(value: Any) -> dict[str, list[Any]]:
    try:
        data = json.loads(value or "{}") if not isinstance(value, dict) else value
    except (TypeError, json.JSONDecodeError):
        data = {}
    return {
        "topics": list(data.get("topics") or []),
        "user_points": list(data.get("user_points") or []),
        "assistant_points": list(data.get("assistant_points") or []),
    }


def update_session_summary(
    previous: Any,
    user_message: str,
    assistant_reply: str,
    source_chat_id: int,
) -> dict[str, list[Any]]:
    """Create a bounded, role-labelled extractive summary for one session."""
    summary = _decode_summary(previous)
    user_text = _clean_turn_text(user_message, 320)
    assistant_text = _clean_turn_text(assistant_reply, 320)
    if user_text:
        point = {"chat_id": int(source_chat_id), "text": user_text}
        if not summary["user_points"] or summary["user_points"][-1] != point:
            summary["user_points"].append(point)
        summary["user_points"] = summary["user_points"][-8:]
        for topic in sorted(tokens(user_text) - _TOPIC_STOP_WORDS):
            if len(topic) >= 3 and topic not in summary["topics"]:
                summary["topics"].append(topic)
        summary["topics"] = summary["topics"][-16:]
    if assistant_text:
        point = {"chat_id": int(source_chat_id), "text": assistant_text}
        if not summary["assistant_points"] or summary["assistant_points"][-1] != point:
            summary["assistant_points"].append(point)
        summary["assistant_points"] = summary["assistant_points"][-6:]
    return summary


def extract_episode(user_message: str) -> dict[str, Any] | None:
    """Extract only explicit first-person events; questions and quotes stay out."""
    original = _clean_turn_text(user_message, 1200)
    if not original or "?" in original:
        return None
    direct = re.sub(
        r'''```[\s\S]*?```|`[^`]*`|“[^”]*”|「[^」]*」|"[^"]*"|'[^']*' ''',
        " ",
        original,
        flags=re.X,
    )
    normalized = normalize(direct)
    first_person_subject = re.match(
        r"^(?:(?:hom nay|hom qua|tuan nay|vua roi|cuoi cung(?: thi)?|may qua)[, ]+)?(?:minh|toi|to)\b",
        normalized,
    )
    if not first_person_subject:
        return None

    subject = r"^(?:(?:hom nay|hom qua|tuan nay|vua roi|cuoi cung(?: thi)?|may qua)[, ]+)?(?:minh|toi|to)\s+"
    patterns = (
        ("achievement", subject + r"(?:(?:vua|da|moi|cuoi cung)\s+){0,3}(?:hoan thanh|lam xong|dat duoc|thi dau|do|tot nghiep|thang)\b", 0.90),
        ("decision", subject + r"(?:(?:vua|da)\s+)?(?:quyet dinh|se bat dau|se dung|se nghi|chon)\b", 0.80),
        ("emotion", subject + r"(?:(?:dang|rat|hoi|cam thay)\s+){0,2}(?:vui|hanh phuc|buon|met|lo lang|so|cang thang|that vong|hao huc)\b", 0.75),
        ("life_event", subject + r"(?:vua|da)\b|^(?:hom nay|hom qua|tuan nay|vua roi)[, ]+(?:minh|toi|to)\s+\S+", 0.70),
    )
    for event_type, pattern, salience in patterns:
        if re.search(pattern, normalized):
            labels = {
                "achievement": "Thành tựu",
                "decision": "Quyết định",
                "emotion": "Cảm xúc",
                "life_event": "Sự kiện",
            }
            short = original[:180].rstrip(" .!?\n")
            return {
                "event_type": event_type,
                "title": f"{labels[event_type]}: {short}"[:255],
                "description": original[:1000],
                "salience": salience,
            }
    return None


def record_completed_turn(
    user_id: str,
    user_message: str,
    assistant_reply: str,
    assistant_chat_id: int,
    *,
    strict: bool = False,
) -> dict[str, Any] | None:
    """Attach a completed exchange to an inactivity-bounded session."""
    conn = get_db_connection()
    if not conn:
        if strict:
            raise DatabaseUnavailable("Không thể lưu session memory")
        return None
    cursor = None
    try:
        _ensure_tables(conn)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id FROM chat_history WHERE user_id = %s AND role = 'user' "
            "AND id < %s ORDER BY id DESC LIMIT 1",
            (user_id, int(assistant_chat_id)),
        )
        source = cursor.fetchone()
        if not source:
            return None
        source_chat_id = int(source["id"])
        idle_seconds = max(60, int(os.getenv("SESSION_IDLE_SECONDS", "1800")))
        session_expiry = expiry_from_env("SESSION_SUMMARY_TTL_DAYS", 90)
        episode_expiry = expiry_from_env("EPISODIC_MEMORY_TTL_DAYS", 365)
        cursor.execute(
            "SELECT id, summary, turn_count, "
            "TIMESTAMPDIFF(SECOND, last_activity_at, CURRENT_TIMESTAMP) AS idle_seconds "
            "FROM conversation_sessions WHERE user_id = %s AND forgotten_at IS NULL "
            "ORDER BY last_activity_at DESC, id DESC LIMIT 1 FOR UPDATE",
            (user_id,),
        )
        session = cursor.fetchone()
        if not session or int(session.get("idle_seconds") or 0) > idle_seconds:
            if session:
                cursor.execute(
                    "UPDATE conversation_sessions SET ended_at = last_activity_at WHERE id = %s AND user_id = %s",
                    (session["id"], user_id),
                )
            cursor.execute(
                "INSERT INTO conversation_sessions "
                "(user_id, start_chat_id, summary, turn_count, confidence, importance, source_type, source_ref, expires_at) "
                "VALUES (%s, %s, %s, 0, 1.00, 0.50, 'chat_session', %s, %s)",
                (user_id, source_chat_id, json.dumps(_decode_summary(None), ensure_ascii=False), str(source_chat_id), session_expiry),
            )
            session_id = int(cursor.lastrowid)
            previous_summary: Any = None
        else:
            session_id = int(session["id"])
            previous_summary = session.get("summary")

        summary = update_session_summary(previous_summary, user_message, assistant_reply, source_chat_id)
        cursor.execute(
            "UPDATE conversation_sessions SET summary = %s, turn_count = turn_count + 1, "
            "last_activity_at = CURRENT_TIMESTAMP, ended_at = NULL, expires_at = %s "
            "WHERE id = %s AND user_id = %s",
            (json.dumps(summary, ensure_ascii=False), session_expiry, session_id, user_id),
        )

        episode = extract_episode(user_message)
        if episode:
            fingerprint = hashlib.sha256(normalize(episode["description"]).encode("utf-8")).hexdigest()
            cursor.execute(
                "INSERT IGNORE INTO episodic_memories "
                "(user_id, session_id, source_chat_id, event_type, title, description, salience, source_role, "
                "source_fingerprint, confidence, importance, source_type, source_ref, expires_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, 'user', %s, 0.90, %s, 'chat_episode', %s, %s)",
                (
                    user_id,
                    session_id,
                    source_chat_id,
                    episode["event_type"],
                    episode["title"],
                    episode["description"],
                    episode["salience"],
                    fingerprint,
                    episode["salience"],
                    str(source_chat_id),
                    episode_expiry,
                ),
            )
        conn.commit()
        return {"session_id": session_id, "source_chat_id": source_chat_id, "episode": episode}
    except Exception as exc:
        conn.rollback()
        if strict:
            raise DatabaseUnavailable("Không thể lưu session memory") from exc
        print(f"Lỗi lưu session/episodic memory: {exc}")
        return None
    finally:
        if cursor is not None:
            cursor.close()
        if conn.is_connected():
            conn.close()


def _context_boundary(cursor, user_id: str) -> tuple[int, set[int]]:
    cursor.execute(
        "SELECT cutoff_chat_id FROM memory_context_state WHERE user_id = %s",
        (user_id,),
    )
    row = cursor.fetchone()
    cutoff = int((row or {}).get("cutoff_chat_id") or 0)
    cursor.execute(
        "SELECT chat_id FROM memory_context_exclusions WHERE user_id = %s",
        (user_id,),
    )
    excluded = {int(item["chat_id"]) for item in (cursor.fetchall() or [])}
    return cutoff, excluded


def list_session_summaries(
    user_id: str = DEFAULT_USER_ID,
    limit: int = 10,
    *,
    strict: bool = False,
) -> list[dict[str, Any]]:
    conn = get_db_connection()
    if not conn:
        if strict:
            raise DatabaseUnavailable("Không thể đọc session summary")
        return []
    cursor = None
    try:
        _ensure_tables(conn)
        cursor = conn.cursor(dictionary=True)
        cutoff, excluded = _context_boundary(cursor, user_id)
        cursor.execute(
            "SELECT id, user_id, start_chat_id, summary, turn_count, confidence, importance, source_type, source_ref, "
            "expires_at, started_at, last_activity_at, ended_at FROM conversation_sessions "
            "WHERE user_id = %s AND forgotten_at IS NULL "
            "AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP) "
            "ORDER BY last_activity_at DESC, id DESC LIMIT %s",
            (user_id, max(1, min(int(limit), 50))),
        )
        result = []
        for row in cursor.fetchall() or []:
            summary = _decode_summary(row.get("summary"))
            summary["user_points"] = [
                item for item in summary["user_points"]
                if int(item.get("chat_id") or 0) > cutoff and int(item.get("chat_id") or 0) not in excluded
            ]
            summary["assistant_points"] = [
                item for item in summary["assistant_points"]
                if int(item.get("chat_id") or 0) > cutoff and int(item.get("chat_id") or 0) not in excluded
            ]
            if not summary["user_points"]:
                continue
            summary["topics"] = sorted({
                topic
                for item in summary["user_points"]
                for topic in tokens(str(item.get("text") or "")) - _TOPIC_STOP_WORDS
                if len(topic) >= 3
            })[-16:]
            result.append({
                "id": row["id"],
                "user_id": row["user_id"],
                "topics": summary["topics"],
                "user_points": summary["user_points"],
                "assistant_points": summary["assistant_points"],
                "turn_count": int(row.get("turn_count") or 0),
                "started_at": row.get("started_at"),
                "last_activity_at": row.get("last_activity_at"),
                "ended_at": row.get("ended_at"),
                "confidence": float(row.get("confidence") or 1.0),
                "importance": float(row.get("importance") or 0.5),
                "source_type": row.get("source_type") or "chat_session",
                "source_ref": row.get("source_ref") or str(row.get("start_chat_id") or ""),
                "expires_at": row.get("expires_at"),
            })
        return result
    except Exception as exc:
        if strict:
            raise DatabaseUnavailable("Không thể đọc session summary") from exc
        print(f"Lỗi đọc session summary: {exc}")
        return []
    finally:
        if cursor is not None:
            cursor.close()
        if conn.is_connected():
            conn.close()


def list_episodes(
    user_id: str = DEFAULT_USER_ID,
    limit: int = 40,
    *,
    strict: bool = False,
) -> list[dict[str, Any]]:
    conn = get_db_connection()
    if not conn:
        if strict:
            raise DatabaseUnavailable("Không thể đọc episodic memory")
        return []
    cursor = None
    try:
        _ensure_tables(conn)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, user_id, session_id, source_chat_id, event_type, title, description, "
            "salience, source_role, confidence, importance, source_type, source_ref, expires_at, occurred_at FROM episodic_memories "
            "WHERE user_id = %s AND source_chat_id > COALESCE((SELECT cutoff_chat_id "
            "FROM memory_context_state WHERE user_id = %s), 0) "
            "AND forgotten_at IS NULL AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP) "
            "AND NOT EXISTS (SELECT 1 FROM memory_context_exclusions excluded "
            "WHERE excluded.user_id = episodic_memories.user_id "
            "AND excluded.chat_id = episodic_memories.source_chat_id) "
            "ORDER BY salience DESC, occurred_at DESC, id DESC LIMIT %s",
            (user_id, user_id, max(1, min(int(limit), 100))),
        )
        return [dict(row) for row in (cursor.fetchall() or [])]
    except Exception as exc:
        if strict:
            raise DatabaseUnavailable("Không thể đọc episodic memory") from exc
        print(f"Lỗi đọc episodic memory: {exc}")
        return []
    finally:
        if cursor is not None:
            cursor.close()
        if conn.is_connected():
            conn.close()


def load_conversation_memory(
    user_id: str = DEFAULT_USER_ID,
    *,
    session_limit: int = 10,
    episode_limit: int = 40,
    strict: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load both conversation stores through one connection for prompt recall."""
    conn = get_db_connection()
    if not conn:
        if strict:
            raise DatabaseUnavailable("Không thể đọc conversation memory")
        return [], []
    cursor = None
    try:
        _ensure_tables(conn)
        cursor = conn.cursor(dictionary=True)
        cutoff, excluded = _context_boundary(cursor, user_id)
        cursor.execute(
            "SELECT id, user_id, start_chat_id, summary, turn_count, confidence, importance, source_type, source_ref, "
            "expires_at, started_at, last_activity_at, ended_at FROM conversation_sessions "
            "WHERE user_id = %s AND forgotten_at IS NULL "
            "AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP) "
            "ORDER BY last_activity_at DESC, id DESC LIMIT %s",
            (user_id, max(1, min(int(session_limit), 50))),
        )
        session_rows = [dict(row) for row in (cursor.fetchall() or [])]
        cursor.execute(
            "SELECT id, user_id, session_id, source_chat_id, event_type, title, description, "
            "salience, source_role, confidence, importance, source_type, source_ref, expires_at, occurred_at FROM episodic_memories "
            "WHERE user_id = %s AND source_chat_id > %s AND forgotten_at IS NULL "
            "AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP) "
            "AND NOT EXISTS (SELECT 1 FROM memory_context_exclusions excluded "
            "WHERE excluded.user_id = episodic_memories.user_id "
            "AND excluded.chat_id = episodic_memories.source_chat_id) "
            "ORDER BY salience DESC, occurred_at DESC, id DESC LIMIT %s",
            (user_id, cutoff, max(1, min(int(episode_limit), 100))),
        )
        episodes = [dict(row) for row in (cursor.fetchall() or [])]

        sessions = []
        for row in session_rows:
            summary = _decode_summary(row.get("summary"))
            summary["user_points"] = [
                item for item in summary["user_points"]
                if int(item.get("chat_id") or 0) > cutoff and int(item.get("chat_id") or 0) not in excluded
            ]
            summary["assistant_points"] = [
                item for item in summary["assistant_points"]
                if int(item.get("chat_id") or 0) > cutoff and int(item.get("chat_id") or 0) not in excluded
            ]
            if not summary["user_points"]:
                continue
            summary["topics"] = sorted({
                topic
                for item in summary["user_points"]
                for topic in tokens(str(item.get("text") or "")) - _TOPIC_STOP_WORDS
                if len(topic) >= 3
            })[-16:]
            sessions.append({
                "id": row["id"],
                "user_id": row["user_id"],
                "topics": summary["topics"],
                "user_points": summary["user_points"],
                "assistant_points": summary["assistant_points"],
                "turn_count": int(row.get("turn_count") or 0),
                "started_at": row.get("started_at"),
                "last_activity_at": row.get("last_activity_at"),
                "ended_at": row.get("ended_at"),
                "confidence": float(row.get("confidence") or 1.0),
                "importance": float(row.get("importance") or 0.5),
                "source_type": row.get("source_type") or "chat_session",
                "source_ref": row.get("source_ref") or str(row.get("start_chat_id") or ""),
                "expires_at": row.get("expires_at"),
            })
        return sessions, episodes
    except Exception as exc:
        if strict:
            raise DatabaseUnavailable("Không thể đọc conversation memory") from exc
        print(f"Lỗi đọc conversation memory: {exc}")
        return [], []
    finally:
        if cursor is not None:
            cursor.close()
        if conn.is_connected():
            conn.close()
