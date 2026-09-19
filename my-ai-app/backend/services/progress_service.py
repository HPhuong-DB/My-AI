"""Evaluate goal progress without mutating goals automatically."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from services.goal_service import list_goals
from services.planner_service import get_plan


def _as_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def evaluate_goal(goal: dict[str, Any], steps: list[dict[str, Any]], now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    progress = int(goal.get("progress") or 0)
    target = _as_datetime(goal.get("target_date"))
    created = _as_datetime(goal.get("created_at"))
    step_progress = round(sum(int(step.get("progress") or 0) for step in steps) / len(steps)) if steps else progress
    recommendations: list[str] = []
    status = "on_track"
    expected = None
    if progress >= 100 or goal.get("status") == "completed":
        status = "completed"
    elif target and target < current:
        status = "overdue"
        recommendations.append("Lùi deadline hoặc chia lại các bước còn lại.")
    elif target and created and target > created:
        total_seconds = (target - created).total_seconds()
        elapsed_seconds = max(0, (current - created).total_seconds())
        expected = min(100, round(elapsed_seconds / total_seconds * 100))
        if progress + 15 < expected:
            status = "at_risk"
            recommendations.append("Đang chậm hơn kế hoạch; ưu tiên bước nhỏ nhất chưa hoàn thành.")
    updated = _as_datetime(goal.get("updated_at"))
    if updated and (current - updated).days >= 7 and progress < 100:
        status = "stalled" if status == "on_track" else status
        recommendations.append("Goal chưa được cập nhật trong 7 ngày; cần kiểm tra trở ngại.")
    if not steps and progress < 100:
        recommendations.append("Tạo plan và chia goal thành các bước cụ thể.")
    if not target and progress < 100:
        recommendations.append("Đặt deadline để đo tiến độ rõ hơn.")
    return {"goal_id": goal.get("id"), "title": goal.get("title"), "status": status, "actual_progress": progress, "step_progress": step_progress, "expected_progress": expected, "target_date": goal.get("target_date"), "recommendations": recommendations}


def evaluate_progress(user_id: str, include_archived: bool = False) -> dict[str, Any]:
    evaluations = []
    for goal in list_goals(user_id, include_archived):
        evaluations.append(evaluate_goal(goal, get_plan(int(goal["id"]), user_id)))
    counts: dict[str, int] = {}
    for item in evaluations:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return {"user_id": user_id, "goals": evaluations, "summary": {"total": len(evaluations), "by_status": counts}}
