"""Persistent personal notes tool, scoped to one user at a time."""

from __future__ import annotations

import json
import os
from typing import Any

from core.database import get_db_connection

DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "default")
MAX_NOTE_TITLE_LENGTH = 255
MAX_NOTE_CONTENT_LENGTH = 100_000
MAX_NOTE_TAGS = 20


def _ensure_notes_table(conn) -> None:
    if not conn:
        return
    from core.migrations import ensure_schema

    ensure_schema(conn)


def _normalize_title(title: str) -> str:
    value = str(title or "").strip()
    if not value:
        raise ValueError("Tiêu đề note không được để trống")
    if len(value) > MAX_NOTE_TITLE_LENGTH:
        raise ValueError(f"Tiêu đề note tối đa {MAX_NOTE_TITLE_LENGTH} ký tự")
    return value


def _normalize_content(content: str) -> str:
    value = str(content or "").strip()
    if not value:
        raise ValueError("Nội dung note không được để trống")
    if len(value) > MAX_NOTE_CONTENT_LENGTH:
        raise ValueError(f"Nội dung note tối đa {MAX_NOTE_CONTENT_LENGTH} ký tự")
    return value


def _normalize_tags(tags: list[str] | tuple[str, ...] | str | None) -> list[str]:
    if tags is None:
        return []
    values = tags.split(",") if isinstance(tags, str) else list(tags)
    normalized: list[str] = []
    for tag in values:
        value = str(tag or "").strip().lower()
        if value and value not in normalized:
            normalized.append(value[:50])
    return normalized[:MAX_NOTE_TAGS]


def _serialize_tags(tags: list[str] | tuple[str, ...] | str | None) -> str:
    return json.dumps(_normalize_tags(tags), ensure_ascii=False)


def _deserialize_tags(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return _normalize_tags(value)
    try:
        decoded = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        decoded = str(value).split(",")
    return _normalize_tags(decoded)


def _note_from_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    note = dict(row)
    note["tags"] = _deserialize_tags(note.get("tags"))
    note["is_archived"] = bool(note.get("is_archived"))
    return note


def create_note(
    user_id: str = DEFAULT_USER_ID,
    title: str = "",
    content: str = "",
    tags: list[str] | tuple[str, ...] | str | None = None,
) -> dict[str, Any] | None:
    title = _normalize_title(title)
    content = _normalize_content(content)
    serialized_tags = _serialize_tags(tags)
    conn = get_db_connection()
    if not conn:
        return None

    cursor = None
    try:
        _ensure_notes_table(conn)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "INSERT INTO personal_notes (user_id, title, content, tags, is_archived) VALUES (%s, %s, %s, %s, %s)",
            (user_id, title, content, serialized_tags, False),
        )
        note_id = cursor.lastrowid
        conn.commit()
        cursor.execute(
            "SELECT id, user_id, title, content, tags, is_archived, created_at, updated_at FROM personal_notes WHERE id = %s AND user_id = %s",
            (note_id, user_id),
        )
        return _note_from_row(cursor.fetchone())
    except Exception as exc:
        print(f"Lỗi tạo note: {exc}")
        return None
    finally:
        if conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def list_notes(
    user_id: str = DEFAULT_USER_ID,
    search: str = "",
    include_archived: bool = False,
    limit: int = 50,
) -> list[dict[str, Any]]:
    conn = get_db_connection()
    if not conn:
        return []

    safe_limit = max(1, min(int(limit), 100))
    cursor = None
    try:
        _ensure_notes_table(conn)
        cursor = conn.cursor(dictionary=True)
        clauses = ["user_id = %s"]
        params: list[Any] = [user_id]
        if not include_archived:
            clauses.append("is_archived = 0")
        normalized_search = str(search or "").strip()
        if normalized_search:
            wildcard = f"%{normalized_search}%"
            clauses.append("(title LIKE %s OR content LIKE %s OR tags LIKE %s)")
            params.extend([wildcard, wildcard, wildcard])
        params.append(safe_limit)
        cursor.execute(
            "SELECT id, user_id, title, content, tags, is_archived, created_at, updated_at "
            f"FROM personal_notes WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC, id DESC LIMIT %s",
            tuple(params),
        )
        return [_note_from_row(row) for row in (cursor.fetchall() or [])]
    except Exception as exc:
        print(f"Lỗi liệt kê note: {exc}")
        return []
    finally:
        if conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def get_note(note_id: int, user_id: str = DEFAULT_USER_ID) -> dict[str, Any] | None:
    conn = get_db_connection()
    if not conn:
        return None

    cursor = None
    try:
        _ensure_notes_table(conn)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, user_id, title, content, tags, is_archived, created_at, updated_at FROM personal_notes WHERE id = %s AND user_id = %s LIMIT 1",
            (note_id, user_id),
        )
        return _note_from_row(cursor.fetchone())
    except Exception as exc:
        print(f"Lỗi đọc note: {exc}")
        return None
    finally:
        if conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def update_note(
    note_id: int,
    user_id: str = DEFAULT_USER_ID,
    title: str | None = None,
    content: str | None = None,
    tags: list[str] | tuple[str, ...] | str | None = None,
) -> dict[str, Any] | None:
    fields: list[str] = []
    values: list[Any] = []
    if title is not None:
        fields.append("title = %s")
        values.append(_normalize_title(title))
    if content is not None:
        fields.append("content = %s")
        values.append(_normalize_content(content))
    if tags is not None:
        fields.append("tags = %s")
        values.append(_serialize_tags(tags))
    if not fields:
        raise ValueError("Cần có title, content hoặc tags để cập nhật note")

    conn = get_db_connection()
    if not conn:
        return None

    cursor = None
    try:
        _ensure_notes_table(conn)
        cursor = conn.cursor(dictionary=True)
        values.extend([note_id, user_id])
        cursor.execute(
            f"UPDATE personal_notes SET {', '.join(fields)} WHERE id = %s AND user_id = %s",
            tuple(values),
        )
        if cursor.rowcount == 0:
            return None
        conn.commit()
        cursor.execute(
            "SELECT id, user_id, title, content, tags, is_archived, created_at, updated_at FROM personal_notes WHERE id = %s AND user_id = %s LIMIT 1",
            (note_id, user_id),
        )
        return _note_from_row(cursor.fetchone())
    except Exception as exc:
        print(f"Lỗi cập nhật note: {exc}")
        return None
    finally:
        if conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def archive_note(note_id: int, user_id: str = DEFAULT_USER_ID) -> bool:
    conn = get_db_connection()
    if not conn:
        return False

    cursor = None
    try:
        _ensure_notes_table(conn)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE personal_notes SET is_archived = 1 WHERE id = %s AND user_id = %s",
            (note_id, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as exc:
        print(f"Lỗi archive note: {exc}")
        return False
    finally:
        if conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()
