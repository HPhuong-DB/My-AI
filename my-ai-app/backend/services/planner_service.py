"""Create and track ordered steps for long-term goals."""

from __future__ import annotations

from typing import Any

from core.database import get_db_connection
from services.goal_service import get_goal, update_goal


def _ensure_steps_table(conn) -> None:
    if not conn:
        return
    from core.migrations import ensure_schema

    ensure_schema(conn)


def _normalize_steps(steps: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not steps or len(steps) > 30:
        raise ValueError("Plan phải có từ 1 đến 30 bước")
    normalized = []
    for item in steps:
        title = str(item.get("title") or "").strip()
        if not title or len(title) > 255:
            raise ValueError("Tiêu đề step không hợp lệ")
        normalized.append({"title": title, "description": str(item.get("description") or "").strip()})
    return normalized


def suggest_steps(title: str, description: str = "") -> list[dict[str, str]]:
    """Return a safe generic plan when the caller has not supplied steps."""
    subject = title.strip()
    return [
        {"title": f"Xác định kết quả cần đạt: {subject}", "description": description.strip()},
        {"title": "Chuẩn bị nguồn lực và chia nhỏ công việc", "description": "Liệt kê thời gian, tài liệu và công cụ cần thiết."},
        {"title": "Thực hiện bước đầu tiên", "description": "Bắt đầu bằng việc nhỏ nhất có thể hoàn thành."},
        {"title": "Kiểm tra và điều chỉnh kế hoạch", "description": "Đánh giá tiến độ rồi cập nhật các bước tiếp theo."},
    ]


def create_plan(goal_id: int, user_id: str, steps: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    goal = get_goal(goal_id, user_id)
    if not goal:
        raise ValueError("Không tìm thấy goal")
    normalized = _normalize_steps(steps or suggest_steps(goal["title"], goal.get("description", "")))
    conn = get_db_connection()
    if not conn:
        return []
    cursor = None
    try:
        _ensure_steps_table(conn)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("DELETE FROM goal_steps WHERE goal_id = %s AND user_id = %s", (goal_id, user_id))
        for position, step in enumerate(normalized, start=1):
            cursor.execute("INSERT INTO goal_steps (goal_id, user_id, title, description, position) VALUES (%s, %s, %s, %s, %s)", (goal_id, user_id, step["title"], step["description"], position))
        conn.commit()
        return get_plan(goal_id, user_id)
    finally:
        if conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def get_plan(goal_id: int, user_id: str) -> list[dict[str, Any]]:
    conn = get_db_connection()
    if not conn:
        return []
    cursor = None
    try:
        _ensure_steps_table(conn)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, goal_id, user_id, title, description, position, status, progress, created_at, updated_at FROM goal_steps WHERE goal_id = %s AND user_id = %s ORDER BY position ASC", (goal_id, user_id))
        return [dict(item) for item in (cursor.fetchall() or [])]
    finally:
        if conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def update_step(step_id: int, user_id: str, status: str | None = None, progress: int | None = None) -> dict[str, Any] | None:
    if status is not None and status not in {"todo", "in_progress", "blocked", "done"}:
        raise ValueError("Status step không hợp lệ")
    if progress is not None and not 0 <= int(progress) <= 100:
        raise ValueError("Progress step phải từ 0 đến 100")
    if status == "done":
        progress = 100
    if progress == 100:
        status = "done"
    if status is None and progress is None:
        raise ValueError("Cần status hoặc progress")
    conn = get_db_connection()
    if not conn:
        return None
    cursor = None
    try:
        _ensure_steps_table(conn)
        cursor = conn.cursor(dictionary=True)
        fields, values = [], []
        if status is not None:
            fields.extend(["status = %s", "progress = %s"])
            values.extend([status, int(progress or 0)])
        elif progress is not None:
            fields.append("progress = %s")
            values.append(int(progress))
        values.extend([step_id, user_id])
        cursor.execute(f"UPDATE goal_steps SET {', '.join(fields)} WHERE id = %s AND user_id = %s", tuple(values))
        if cursor.rowcount == 0:
            return None
        conn.commit()
        cursor.execute("SELECT id, goal_id, user_id, title, description, position, status, progress, created_at, updated_at FROM goal_steps WHERE id = %s AND user_id = %s", (step_id, user_id))
        step = cursor.fetchone()
        if step:
            _sync_goal_progress(int(step["goal_id"]), user_id)
        return dict(step) if step else None
    finally:
        if conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def _sync_goal_progress(goal_id: int, user_id: str) -> None:
    plan = get_plan(goal_id, user_id)
    if not plan:
        return
    progress = round(sum(int(item.get("progress") or 0) for item in plan) / len(plan))
    update_goal(goal_id, user_id, progress=progress)
