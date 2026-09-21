"""Long-term goal management, scoped by user."""

from __future__ import annotations

import os
from typing import Any

from core.database import get_db_connection

DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "default")
GOAL_STATUSES = frozenset({"active", "paused", "completed", "archived"})


def _ensure_goal_table(conn) -> None:
    if not conn:
        return
    from core.migrations import ensure_schema

    ensure_schema(conn)


def _validate_title(title: str) -> str:
    value = str(title or "").strip()
    if not value:
        raise ValueError("Goal title không được để trống")
    if len(value) > 255:
        raise ValueError("Goal title tối đa 255 ký tự")
    return value


def _validate_progress(progress: int) -> int:
    value = int(progress)
    if value < 0 or value > 100:
        raise ValueError("Progress phải nằm trong khoảng 0 đến 100")
    return value


def _row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    result = dict(row)
    result["progress"] = int(result.get("progress") or 0)
    result["priority"] = int(result.get("priority") or 3)
    return result


def create_goal(user_id: str = DEFAULT_USER_ID, title: str = "", description: str = "", priority: int = 3, target_date: str | None = None) -> dict[str, Any] | None:
    title = _validate_title(title)
    priority = max(1, min(int(priority), 5))
    conn = get_db_connection()
    if not conn:
        return None
    cursor = None
    try:
        _ensure_goal_table(conn)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "INSERT INTO personal_goals (user_id, title, description, priority, target_date) VALUES (%s, %s, %s, %s, %s)",
            (user_id, title, str(description or "").strip(), priority, target_date or None),
        )
        goal_id = cursor.lastrowid
        conn.commit()
        cursor.execute(
            "SELECT id, user_id, title, description, status, priority, progress, target_date, created_at, updated_at FROM personal_goals WHERE id = %s AND user_id = %s",
            (goal_id, user_id),
        )
        return _row(cursor.fetchone())
    except Exception as exc:
        print(f"Lỗi tạo goal: {exc}")
        return None
    finally:
        if conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def list_goals(user_id: str = DEFAULT_USER_ID, include_archived: bool = False) -> list[dict[str, Any]]:
    conn = get_db_connection()
    if not conn:
        return []
    cursor = None
    try:
        _ensure_goal_table(conn)
        cursor = conn.cursor(dictionary=True)
        if include_archived:
            cursor.execute("SELECT id, user_id, title, description, status, priority, progress, target_date, created_at, updated_at FROM personal_goals WHERE user_id = %s ORDER BY priority ASC, updated_at DESC", (user_id,))
        else:
            cursor.execute("SELECT id, user_id, title, description, status, priority, progress, target_date, created_at, updated_at FROM personal_goals WHERE user_id = %s AND status <> 'archived' ORDER BY priority ASC, updated_at DESC", (user_id,))
        return [_row(item) for item in (cursor.fetchall() or [])]
    except Exception as exc:
        print(f"Lỗi liệt kê goal: {exc}")
        return []
    finally:
        if conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def get_goal(goal_id: int, user_id: str = DEFAULT_USER_ID) -> dict[str, Any] | None:
    conn = get_db_connection()
    if not conn:
        return None
    cursor = None
    try:
        _ensure_goal_table(conn)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, user_id, title, description, status, priority, progress, target_date, created_at, updated_at FROM personal_goals WHERE id = %s AND user_id = %s LIMIT 1", (goal_id, user_id))
        return _row(cursor.fetchone())
    except Exception as exc:
        print(f"Lỗi đọc goal: {exc}")
        return None
    finally:
        if conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def update_goal(goal_id: int, user_id: str = DEFAULT_USER_ID, title: str | None = None, description: str | None = None, status: str | None = None, priority: int | None = None, progress: int | None = None, target_date: str | None = None) -> dict[str, Any] | None:
    fields: list[str] = []
    values: list[Any] = []
    if title is not None:
        fields.append("title = %s")
        values.append(_validate_title(title))
    if description is not None:
        fields.append("description = %s")
        values.append(str(description).strip())
    if status is not None:
        if status not in GOAL_STATUSES:
            raise ValueError("Status goal không hợp lệ")
        fields.append("status = %s")
        values.append(status)
    if priority is not None:
        fields.append("priority = %s")
        values.append(max(1, min(int(priority), 5)))
    if progress is not None:
        progress = _validate_progress(progress)
        fields.append("progress = %s")
        values.append(progress)
        if progress == 100 and status is None:
            fields.extend(["status = %s"])
            values.append("completed")
    if target_date is not None:
        fields.append("target_date = %s")
        values.append(target_date or None)
    if not fields:
        raise ValueError("Không có trường goal cần cập nhật")

    conn = get_db_connection()
    if not conn:
        return None
    cursor = None
    try:
        _ensure_goal_table(conn)
        cursor = conn.cursor(dictionary=True)
        values.extend([goal_id, user_id])
        cursor.execute(f"UPDATE personal_goals SET {', '.join(fields)} WHERE id = %s AND user_id = %s", tuple(values))
        if cursor.rowcount == 0:
            return None
        conn.commit()
        cursor.execute("SELECT id, user_id, title, description, status, priority, progress, target_date, created_at, updated_at FROM personal_goals WHERE id = %s AND user_id = %s LIMIT 1", (goal_id, user_id))
        return _row(cursor.fetchone())
    except Exception as exc:
        print(f"Lỗi cập nhật goal: {exc}")
        return None
    finally:
        if conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()
