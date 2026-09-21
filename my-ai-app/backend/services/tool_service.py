import os

from core.database import get_db_connection
from agent.tooling import ToolDefinition, ToolExecutor, ToolRegistry
from services.file_tool_service import read_file, write_file
from services.web_search_service import search_web
from services.memory_service import get_relationship_tone, get_user_profile
from services.notes_service import archive_note, create_note, get_note, list_notes, update_note
from services.goal_service import create_goal as create_long_term_goal, get_goal as get_long_term_goal, list_goals as list_long_term_goals, update_goal as update_long_term_goal
from services.planner_service import create_plan, get_plan, update_step

DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "default")

TOOL_REGISTRY = [
    {
        "name": "set_reminder",
        "description": "Đặt nhắc nhở cá nhân cho user theo thời gian cụ thể.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "scheduled_for": {"type": "string"},
                "note": {"type": "string"},
            },
            "required": ["title", "scheduled_for"],
        },
    },
    {
        "name": "create_task",
        "description": "Tạo task cá nhân cho user, ví dụ học tập, công việc, chăm sóc bản thân.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "list_tasks",
        "description": "Liệt kê tasks còn chưa hoàn thành hoặc toàn bộ task của user.",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_done": {"type": "boolean"},
            },
        },
    },
    {
        "name": "update_task",
        "description": "Cập nhật trạng thái và phần trăm tiến độ của task.",
        "input_schema": {"type": "object", "properties": {"task_id": {"type": "integer"}, "status": {"type": "string"}, "progress": {"type": "integer", "minimum": 0, "maximum": 100}}, "required": ["task_id"]},
    },
    {
        "name": "get_task_progress",
        "description": "Xem tiến độ các task cá nhân.",
        "input_schema": {"type": "object", "properties": {"include_done": {"type": "boolean"}}},
    },
    {
        "name": "create_note",
        "description": "Lưu một ghi chú cá nhân cho user.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "maxLength": 255},
                "content": {"type": "string", "maxLength": 100000},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "list_notes",
        "description": "Tìm và liệt kê ghi chú cá nhân của user.",
        "input_schema": {
            "type": "object",
            "properties": {
                "search": {"type": "string"},
                "include_archived": {"type": "boolean"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
        },
    },
    {
        "name": "get_note",
        "description": "Đọc một ghi chú cá nhân theo id.",
        "input_schema": {
            "type": "object",
            "properties": {"note_id": {"type": "integer"}},
            "required": ["note_id"],
        },
    },
    {
        "name": "update_note",
        "description": "Cập nhật tiêu đề, nội dung hoặc tag của ghi chú cá nhân.",
        "input_schema": {
            "type": "object",
            "properties": {
                "note_id": {"type": "integer"},
                "title": {"type": "string", "maxLength": 255},
                "content": {"type": "string", "maxLength": 100000},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["note_id"],
        },
    },
    {
        "name": "archive_note",
        "description": "Ẩn ghi chú cá nhân thay vì xóa vĩnh viễn.",
        "input_schema": {
            "type": "object",
            "properties": {"note_id": {"type": "integer"}},
            "required": ["note_id"],
        },
    },
    {
        "name": "read_file",
        "description": "Đọc file văn bản trong thư mục riêng của user.",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    },
    {
        "name": "write_file",
        "description": "Ghi file văn bản trong thư mục riêng của user; cần xác nhận trước.",
        "requires_confirmation": True,
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]},
    },
    {
        "name": "web_search",
        "description": "Tìm kiếm thông tin công khai trên web với giới hạn kết quả.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer"}}, "required": ["query"]},
    },
    {
        "name": "create_goal",
        "description": "Tạo mục tiêu dài hạn cá nhân.",
        "input_schema": {"type": "object", "properties": {"title": {"type": "string"}, "description": {"type": "string"}, "priority": {"type": "integer"}, "target_date": {"type": "string"}}, "required": ["title"]},
    },
    {
        "name": "list_goals",
        "description": "Liệt kê mục tiêu dài hạn cá nhân.",
        "input_schema": {"type": "object", "properties": {"include_archived": {"type": "boolean"}}},
    },
    {
        "name": "update_goal",
        "description": "Cập nhật trạng thái hoặc tiến độ mục tiêu.",
        "input_schema": {"type": "object", "properties": {"goal_id": {"type": "integer"}, "status": {"type": "string"}, "progress": {"type": "integer"}}, "required": ["goal_id"]},
    },
    {
        "name": "create_plan",
        "description": "Chia một goal thành các bước nhỏ có thứ tự.",
        "input_schema": {"type": "object", "properties": {"goal_id": {"type": "integer"}, "steps": {"type": "array"}}, "required": ["goal_id"]},
    },
    {
        "name": "get_goal_plan",
        "description": "Xem các bước và tiến độ của goal.",
        "input_schema": {"type": "object", "properties": {"goal_id": {"type": "integer"}}, "required": ["goal_id"]},
    },
    {
        "name": "update_goal_step",
        "description": "Cập nhật tiến độ một bước trong kế hoạch.",
        "input_schema": {"type": "object", "properties": {"step_id": {"type": "integer"}, "status": {"type": "string"}, "progress": {"type": "integer"}}, "required": ["step_id"]},
    },
    {
        "name": "research_topic",
        "description": "Tìm kiếm web, đọc nguồn, tóm tắt và lưu kiến thức về một chủ đề.",
        "timeout_seconds": 60,
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "max_sources": {"type": "integer"}, "save": {"type": "boolean"}}, "required": ["query"]},
    },
    {
        "name": "list_knowledge",
        "description": "Đọc lại các kết quả nghiên cứu đã lưu của user.",
        "input_schema": {"type": "object", "properties": {"limit": {"type": "integer"}}},
    },
    {
        "name": "save_experience",
        "description": "Lưu một bài học hoặc kinh nghiệm đã rút ra.",
        "input_schema": {"type": "object", "properties": {"title": {"type": "string"}, "lesson": {"type": "string"}, "context": {"type": "string"}}, "required": ["title", "lesson"]},
    },
    {
        "name": "get_long_term_memory",
        "description": "Đọc riêng biệt memory cá nhân, kiến thức và kinh nghiệm.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}},
    },
    {
        "name": "evaluate_progress",
        "description": "Đánh giá goal đang đúng tiến độ, có nguy cơ trễ hay bị đình trệ.",
        "input_schema": {"type": "object", "properties": {"include_archived": {"type": "boolean"}}},
    },
    {
        "name": "self_learn",
        "description": "Lưu kiến thức, memory hoặc experience đã học; tuyệt đối không sửa code, quyền hay cấu hình hệ thống.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "enum": ["memory", "knowledge", "experience"]},
                "title": {"type": "string", "maxLength": 255},
                "content": {"type": "string", "maxLength": 12000},
                "context": {"type": "string", "maxLength": 12000},
                "source_url": {"type": "string", "maxLength": 2000},
            },
            "required": ["target", "title", "content"],
        },
    },
]

PERSONAL_TOOL_NAMES = frozenset({
    "set_reminder",
    "create_task",
    "list_tasks",
    "update_task",
    "get_task_progress",
    "create_note",
    "list_notes",
    "get_note",
    "update_note",
    "archive_note",
    "read_file",
    "write_file",
    "web_search",
    "create_goal",
    "list_goals",
    "update_goal",
    "create_plan",
    "get_goal_plan",
    "update_goal_step",
    "research_topic",
    "list_knowledge",
    "save_experience",
    "get_long_term_memory",
    "evaluate_progress",
    "self_learn",
})


def execute_registered_tool(
    tool_name: str,
    arguments: dict | None = None,
    user_id: str = DEFAULT_USER_ID,
) -> dict:
    """Execute a registered Notes tool with the user scope supplied by the server."""
    if tool_name not in PERSONAL_TOOL_NAMES:
        raise ValueError(f"Tool chưa được hỗ trợ: {tool_name}")

    args = dict(arguments or {})
    try:
        if tool_name == "set_reminder":
            ok = create_reminder(
                user_id=user_id,
                title=args.get("title", ""),
                scheduled_for=args.get("scheduled_for", ""),
                note=args.get("note", ""),
            )
            return {"ok": ok}
        if tool_name == "create_task":
            return {"ok": create_task(user_id=user_id, title=args.get("title", ""), description=args.get("description", ""))}
        if tool_name == "list_tasks":
            return {"ok": True, "tasks": list_tasks(user_id=user_id, include_done=bool(args.get("include_done", False)))}
        if tool_name == "update_task":
            return update_task(user_id=user_id, task_id=int(args["task_id"]), status=args.get("status"), progress=args.get("progress"))
        if tool_name == "get_task_progress":
            return {"ok": True, "tasks": get_task_progress(user_id=user_id, include_done=bool(args.get("include_done", False)))}
        if tool_name == "create_goal":
            goal = create_long_term_goal(user_id, args.get("title", ""), args.get("description", ""), args.get("priority", 3), args.get("target_date"))
            return {"ok": goal is not None, "goal": goal}
        if tool_name == "list_goals":
            return {"ok": True, "goals": list_long_term_goals(user_id, bool(args.get("include_archived", False)))}
        if tool_name == "update_goal":
            goal = update_long_term_goal(int(args["goal_id"]), user_id, status=args.get("status"), progress=args.get("progress"))
            return {"ok": goal is not None, "goal": goal}
        if tool_name == "create_plan":
            return {"ok": True, "steps": create_plan(int(args["goal_id"]), user_id, args.get("steps"))}
        if tool_name == "get_goal_plan":
            return {"ok": True, "steps": get_plan(int(args["goal_id"]), user_id)}
        if tool_name == "update_goal_step":
            step = update_step(int(args["step_id"]), user_id, args.get("status"), args.get("progress"))
            return {"ok": step is not None, "step": step}
        if tool_name == "list_knowledge":
            from services.research_service import list_knowledge

            return {"ok": True, "knowledge": list_knowledge(user_id, args.get("limit", 20))}
        if tool_name == "save_experience":
            from services.memory_orchestrator import memory_orchestrator

            experience = memory_orchestrator.remember_experience(
                user_id,
                args.get("title", ""),
                args.get("lesson", ""),
                args.get("context", ""),
            )
            return {"ok": experience is not None, "experience": experience}
        if tool_name == "get_long_term_memory":
            from services.memory_orchestrator import memory_orchestrator

            return {
                "ok": True,
                "memory": memory_orchestrator.recall_long_term(
                    user_id,
                    args.get("query", ""),
                    args.get("limit", 10),
                ),
            }
        if tool_name == "evaluate_progress":
            from services.progress_service import evaluate_progress

            return {"ok": True, "evaluation": evaluate_progress(user_id, bool(args.get("include_archived", False)))}
        if tool_name == "self_learn":
            from agent.runtime import self_learning_service

            return self_learning_service.learn(
                user_id,
                target=args.get("target", ""),
                title=args.get("title", ""),
                content=args.get("content", ""),
                context=args.get("context", ""),
                source_url=args.get("source_url", ""),
            )
        if tool_name == "research_topic":
            raise ValueError("research_topic phải chạy qua execute_tool_call bất đồng bộ")
        if tool_name == "create_note":
            note = create_note(
                user_id=user_id,
                title=args.get("title", ""),
                content=args.get("content", ""),
                tags=args.get("tags"),
            )
            return {"ok": note is not None, "note": note}
        if tool_name == "read_file":
            return read_file(user_id, args.get("path", ""))
        if tool_name == "write_file":
            return write_file(user_id, args.get("path", ""), args.get("content", ""))
        if tool_name == "web_search":
            raise ValueError("web_search phải chạy qua execute_tool_call bất đồng bộ")
        if tool_name == "list_notes":
            return {
                "ok": True,
                "notes": list_notes(
                    user_id=user_id,
                    search=args.get("search", ""),
                    include_archived=bool(args.get("include_archived", False)),
                    limit=int(args.get("limit", 50)),
                ),
            }
        if tool_name == "get_note":
            note = get_note(note_id=int(args["note_id"]), user_id=user_id)
            return {"ok": note is not None, "note": note}
        if tool_name == "update_note":
            note_id = int(args["note_id"])
            note = update_note(
                note_id=note_id,
                user_id=user_id,
                title=args.get("title"),
                content=args.get("content"),
                tags=args.get("tags"),
            )
            return {"ok": note is not None, "note": note}
        return {
            "ok": archive_note(note_id=int(args["note_id"]), user_id=user_id),
            "note_id": int(args["note_id"]),
        }
    except (KeyError, TypeError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}


def _ensure_tool_tables(conn):
    if not conn:
        return
    from core.migrations import ensure_schema

    ensure_schema(conn)


def create_task(user_id=DEFAULT_USER_ID, title="", description=""):
    if not title:
        return False

    conn = get_db_connection()
    if not conn:
        return False

    cursor = None
    try:
        _ensure_tool_tables(conn)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO personal_tasks (user_id, title, description, done) VALUES (%s, %s, %s, %s)",
            (user_id, title, description or "", False),
        )
        conn.commit()
        return True
    except Exception as exc:
        print(f"Lỗi tạo task: {exc}")
        return False
    finally:
        if conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def list_tasks(user_id=DEFAULT_USER_ID, include_done=False):
    conn = get_db_connection()
    if not conn:
        return []

    cursor = None
    try:
        _ensure_tool_tables(conn)
        cursor = conn.cursor(dictionary=True)
        if include_done:
            cursor.execute(
                "SELECT id, user_id, title, description, done, status, progress, created_at FROM personal_tasks WHERE user_id = %s ORDER BY id DESC",
                (user_id,),
            )
        else:
            cursor.execute(
                "SELECT id, user_id, title, description, done, status, progress, created_at FROM personal_tasks WHERE user_id = %s AND done = 0 ORDER BY id DESC",
                (user_id,),
            )
        return cursor.fetchall()
    except Exception as exc:
        print(f"Lỗi liệt kê task: {exc}")
        return []
    finally:
        if conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def update_task(task_id, user_id=DEFAULT_USER_ID, status=None, progress=None):
    if status is None and progress is None:
        return {"ok": False, "error": "status_or_progress_required"}
    allowed_statuses = {"todo", "in_progress", "blocked", "done"}
    if status is not None and status not in allowed_statuses:
        return {"ok": False, "error": "invalid_status"}
    if progress is not None and (int(progress) < 0 or int(progress) > 100):
        return {"ok": False, "error": "invalid_progress"}
    if status == "done":
        progress = 100
    if progress == 100:
        status = "done"

    conn = get_db_connection()
    if not conn:
        return {"ok": False, "error": "database_unavailable"}
    cursor = None
    try:
        _ensure_tool_tables(conn)
        cursor = conn.cursor()
        fields = []
        values = []
        if status is not None:
            fields.extend(["status = %s", "done = %s"])
            values.extend([status, status == "done"])
        if progress is not None:
            fields.append("progress = %s")
            values.append(int(progress))
        values.extend([int(task_id), user_id])
        cursor.execute(f"UPDATE personal_tasks SET {', '.join(fields)} WHERE id = %s AND user_id = %s", tuple(values))
        if cursor.rowcount == 0:
            return {"ok": False, "error": "task_not_found"}
        conn.commit()
        return {"ok": True, "task_id": int(task_id), "status": status, "progress": progress}
    except Exception as exc:
        print(f"Lỗi cập nhật task: {exc}")
        return {"ok": False, "error": "task_update_failed"}
    finally:
        if conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def get_task_progress(user_id=DEFAULT_USER_ID, include_done=False):
    return list_tasks(user_id=user_id, include_done=include_done)


def create_reminder(user_id=DEFAULT_USER_ID, title="", scheduled_for="", note=""):
    if not title or not scheduled_for:
        return False

    conn = get_db_connection()
    if not conn:
        return False

    cursor = None
    try:
        _ensure_tool_tables(conn)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO personal_reminders (user_id, title, scheduled_for, note, done) VALUES (%s, %s, %s, %s, %s)",
            (user_id, title, scheduled_for, note or "", False),
        )
        conn.commit()
        return True
    except Exception as exc:
        print(f"Lỗi tạo reminder: {exc}")
        return False
    finally:
        if conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def get_upcoming_reminders(user_id=DEFAULT_USER_ID, limit=10):
    conn = get_db_connection()
    if not conn:
        return []

    cursor = None
    try:
        _ensure_tool_tables(conn)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, user_id, title, scheduled_for, note, done FROM personal_reminders WHERE user_id = %s AND done = 0 ORDER BY scheduled_for ASC LIMIT %s",
            (user_id, limit),
        )
        return cursor.fetchall()
    except Exception as exc:
        print(f"Lỗi đọc reminder: {exc}")
        return []
    finally:
        if conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def get_due_reminders(user_id=DEFAULT_USER_ID, now=None, limit=20):
    conn = get_db_connection()
    if not conn:
        return []

    cursor = None
    try:
        _ensure_tool_tables(conn)
        cursor = conn.cursor(dictionary=True)
        from datetime import datetime, UTC

        reference = now or datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "SELECT id, user_id, title, scheduled_for, note, done FROM personal_reminders WHERE user_id = %s AND done = 0 AND scheduled_for <= %s ORDER BY scheduled_for ASC LIMIT %s",
            (user_id, reference, limit),
        )
        return cursor.fetchall()
    except Exception as exc:
        print(f"Lỗi đọc reminder quá hạn: {exc}")
        return []
    finally:
        if conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def complete_reminder(reminder_id, user_id=DEFAULT_USER_ID):
    conn = get_db_connection()
    if not conn:
        return False

    cursor = None
    try:
        _ensure_tool_tables(conn)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE personal_reminders SET done = 1 WHERE id = %s AND user_id = %s",
            (reminder_id, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as exc:
        print(f"Lỗi hoàn thành reminder: {exc}")
        return False
    finally:
        if conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def complete_reminder_with_feedback(reminder_id, user_id=DEFAULT_USER_ID, completion_message="", emotion="neutral"):
    result = complete_reminder(reminder_id=reminder_id, user_id=user_id)
    if not result:
        return {"ok": False, "message": "Không thể đánh dấu hoàn thành reminder.", "emotion": emotion}

    profile = get_user_profile(user_id=user_id)
    tone = get_relationship_tone(profile.get("affection_level", 0)) if profile else "mới gặp, nên nói lịch sự và giữ khoảng cách"
    username = profile.get("username") if profile else "bạn"
    mood = (profile.get("mood") or "neutral") if profile else "neutral"

    feedback_message = completion_message.strip() or "Mình đã hoàn thành xong rồi, cảm thấy nhẹ hơn nhiều."
    emotion_map = {
        "happy": "Tuyệt vời! Mình thấy bạn đang rất vui và mình cũng muốn cùng vui với bạn.",
        "relieved": "Thật là nhẹ nhõm! Mình thấy bạn đã giải quyết xong và mình rất vui vì điều đó.",
        "stressed": "Mình biết hôm nay bạn đang căng thẳng, nên mình rất vui vì bạn đã làm xong. Hãy nghỉ ngơi một chút nhé.",
        "sad": "Mình biết bạn có thể đang mệt hoặc buồn, nhưng bạn đã vượt qua được một việc rồi. Cố lên nhé.",
        "neutral": "Tốt lắm! Việc này đã được xử lý xong rồi.",
    }
    greeting = f"{username}, " if username and username != "None" else ""
    tone_note = f" Mình nói chuyện với bạn theo cách {tone}."

    if mood == "happy":
        response_message = greeting + "Tuyệt vời! Mình thấy bạn đang rất vui, và mình cũng cảm thấy vui theo. " + tone_note + f" {feedback_message}"
    elif mood == "stressed":
        response_message = greeting + "Mình biết bạn đang rất mệt và căng thẳng. Nhưng bạn đã hoàn thành rồi, thật tốt. Hãy thở sâu và nghỉ ngơi một chút. " + tone_note + f" {feedback_message}"
    elif mood == "sad":
        response_message = greeting + "Mình thấy bạn có thể đang mệt hoặc buồn. Đừng quá đánh giá bản thân, bạn đã làm xong rồi đó. " + tone_note + f" {feedback_message}"
    else:
        response_message = greeting + emotion_map.get(emotion, emotion_map["neutral"]) + tone_note + f" {feedback_message}"

    return {
        "ok": True,
        "reminder_id": reminder_id,
        "user_id": user_id,
        "emotion": emotion,
        "message": response_message,
    }


def trigger_due_reminder_notification(user_id=DEFAULT_USER_ID, now=None):
    reminders = get_due_reminders(user_id=user_id, now=now)
    summary = {
        "user_id": user_id,
        "count": len(reminders),
        "reminders": [],
    }

    for item in reminders:
        title = item.get("title") or "Nhắc nhở"
        note = item.get("note") or ""
        message = f"Nhắc nhở: {title}."
        if note:
            message = f"{message} {note}"
        summary["reminders"].append(
            {
                "id": item.get("id"),
                "title": title,
                "scheduled_for": item.get("scheduled_for"),
                "note": note,
                "message": message,
                "done": bool(item.get("done")),
            }
        )

    return summary


def build_due_reminder_context(user_id=DEFAULT_USER_ID, now=None):
    summary = trigger_due_reminder_notification(user_id=user_id, now=now)
    if summary["count"] == 0:
        return ""

    lines = [
        f"Bạn đang có {summary['count']} nhắc nhở đến hạn cần xử lý:"
    ]
    for reminder in summary["reminders"]:
        schedule = reminder.get("scheduled_for") or "không rõ thời gian"
        note = reminder.get("note") or ""
        suffix = f" - {note}" if note else ""
        lines.append(f"- {reminder['title']} ({schedule}){suffix}")
    return "\n".join(lines)


def deliver_due_reminder_notifications(user_id=DEFAULT_USER_ID, now=None):
    summary = trigger_due_reminder_notification(user_id=user_id, now=now)
    notifications = []

    for reminder in summary["reminders"]:
        route = {
            "user_id": user_id,
            "id": reminder["id"],
            "title": reminder["title"],
            "message": reminder["message"],
            "scheduled_for": reminder["scheduled_for"],
            "status": "sent",
        }
        notifications.append(route)

    return {
        "user_id": user_id,
        "count": len(notifications),
        "notifications": notifications,
    }


def poll_due_reminder_notifications_for_all_users():
    conn = get_db_connection()
    if not conn:
        return []

    cursor = None
    try:
        _ensure_tool_tables(conn)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT DISTINCT user_id FROM personal_reminders WHERE done = 0 ORDER BY user_id ASC"
        )
        users = cursor.fetchall() or []

        results = []
        for row in users:
            user_id = row.get("user_id") or DEFAULT_USER_ID
            result = deliver_due_reminder_notifications(user_id=user_id)
            results.append(result)
        return results
    except Exception as exc:
        print(f"Lỗi quét reminder background: {exc}")
        return []
    finally:
        if conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def _registry_handler(tool_name: str):
    if tool_name in {"web_search", "research_topic"}:
        async def async_handler(user_id: str, arguments: dict):
            if tool_name == "research_topic":
                from services.research_service import run_research

                return await run_research(arguments.get("query", ""), user_id, arguments.get("max_sources", 3), arguments.get("save", True))
            return await search_web(arguments.get("query", ""), arguments.get("max_results", 5))

        return async_handler

    def handler(user_id: str, arguments: dict):
        return execute_registered_tool(tool_name, arguments, user_id)

    return handler


# Standard registry used by the future LLM tool-calling loop. The legacy
# TOOL_REGISTRY list remains available for API compatibility.
tool_registry = ToolRegistry()
for _definition in TOOL_REGISTRY:
    if _definition["name"] in PERSONAL_TOOL_NAMES:
        tool_registry.register(
            ToolDefinition(
                name=_definition["name"],
                description=_definition["description"],
                input_schema=_definition["input_schema"],
                requires_confirmation=_definition.get("requires_confirmation", False),
                timeout_seconds=_definition.get("timeout_seconds"),
            ),
            _registry_handler(_definition["name"]),
        )

tool_executor = ToolExecutor(
    tool_registry,
    max_calls=int(os.getenv("TOOL_MAX_CALLS_PER_MINUTE")),
    timeout_seconds=float(os.getenv("TOOL_TIMEOUT_SECONDS")),
)


async def execute_tool_call(
    tool_name: str,
    user_id: str,
    arguments: dict | None = None,
    *,
    confirmed: bool = False,
    confirmation_id: str | None = None,
) -> dict:
    result = await tool_executor.execute(
        tool_name,
        user_id,
        arguments,
        confirmed=confirmed,
        confirmation_id=confirmation_id,
    )
    return result.as_dict()
