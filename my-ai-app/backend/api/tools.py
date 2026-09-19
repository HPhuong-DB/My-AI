from fastapi import APIRouter, Body, Query
from pydantic import BaseModel, Field

from services.notes_service import (
    archive_note,
    create_note,
    get_note,
    list_notes,
    update_note,
)

from services.tool_service import (
    DEFAULT_USER_ID,
    TOOL_REGISTRY,
    complete_reminder,
    complete_reminder_with_feedback,
    create_reminder,
    create_task,
    deliver_due_reminder_notifications,
    get_due_reminders,
    get_upcoming_reminders,
    list_tasks,
    poll_due_reminder_notifications_for_all_users,
    trigger_due_reminder_notification,
    execute_tool_call,
    tool_executor,
)


class ReminderCompletionPayload(BaseModel):
    completion_message: str = ""
    emotion: str = "neutral"


class NoteCreatePayload(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1, max_length=100000)
    tags: list[str] = Field(default_factory=list, max_length=20)


class NoteUpdatePayload(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = Field(default=None, min_length=1, max_length=100000)
    tags: list[str] | None = Field(default=None, max_length=20)


class ToolCallPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    arguments: dict = Field(default_factory=dict)
    confirmed: bool = False
    confirmation_id: str | None = None

router = APIRouter()


@router.get("/tools")
async def list_tools():
    standard_tools = [definition.as_dict() for definition in tool_executor.registry.definitions()]
    standard_names = {tool["name"] for tool in standard_tools}
    legacy_tools = [tool for tool in TOOL_REGISTRY if tool["name"] not in standard_names]
    return {"tools": standard_tools + legacy_tools}


@router.post("/tools/execute")
async def execute_tool_endpoint(
    payload: ToolCallPayload,
    user_id: str = Query(DEFAULT_USER_ID, min_length=1, max_length=100),
):
    return await execute_tool_call(
        payload.name,
        user_id,
        payload.arguments,
        confirmed=payload.confirmed,
        confirmation_id=payload.confirmation_id,
    )


@router.get("/tools/audit")
async def tool_audit_endpoint(
    user_id: str = Query(DEFAULT_USER_ID, min_length=1, max_length=100),
    limit: int = Query(50, ge=1, le=100),
):
    return {"user_id": user_id, "entries": tool_executor.get_audit(user_id, limit)}


@router.post("/tools/reminders")
async def create_reminder_endpoint(
    title: str,
    scheduled_for: str,
    note: str = "",
    user_id: str = Query(DEFAULT_USER_ID, min_length=1, max_length=100),
):
    ok = create_reminder(user_id=user_id, title=title, scheduled_for=scheduled_for, note=note)
    return {"ok": ok, "user_id": user_id}


@router.post("/tools/tasks")
async def create_task_endpoint(
    title: str,
    description: str = "",
    user_id: str = Query(DEFAULT_USER_ID, min_length=1, max_length=100),
):
    ok = create_task(user_id=user_id, title=title, description=description)
    return {"ok": ok, "user_id": user_id}


@router.get("/tools/tasks")
async def list_tasks_endpoint(
    include_done: bool = False,
    user_id: str = Query(DEFAULT_USER_ID, min_length=1, max_length=100),
):
    return {"user_id": user_id, "tasks": list_tasks(user_id=user_id, include_done=include_done)}


@router.post("/tools/notes")
async def create_note_endpoint(
    payload: NoteCreatePayload,
    user_id: str = Query(DEFAULT_USER_ID, min_length=1, max_length=100),
):
    try:
        note = create_note(
            user_id=user_id,
            title=payload.title,
            content=payload.content,
            tags=payload.tags,
        )
    except ValueError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if note is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="Không thể lưu note")
    return {"ok": True, "note": note}


@router.get("/tools/notes")
async def list_notes_endpoint(
    search: str = "",
    include_archived: bool = False,
    limit: int = 50,
    user_id: str = Query(DEFAULT_USER_ID, min_length=1, max_length=100),
):
    return {
        "user_id": user_id,
        "notes": list_notes(
            user_id=user_id,
            search=search,
            include_archived=include_archived,
            limit=limit,
        ),
    }


@router.get("/tools/notes/{note_id}")
async def get_note_endpoint(
    note_id: int,
    user_id: str = Query(DEFAULT_USER_ID, min_length=1, max_length=100),
):
    note = get_note(note_id=note_id, user_id=user_id)
    if note is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Không tìm thấy note")
    return {"user_id": user_id, "note": note}


@router.patch("/tools/notes/{note_id}")
async def update_note_endpoint(
    note_id: int,
    payload: NoteUpdatePayload,
    user_id: str = Query(DEFAULT_USER_ID, min_length=1, max_length=100),
):
    try:
        note = update_note(
            note_id=note_id,
            user_id=user_id,
            title=payload.title,
            content=payload.content,
            tags=payload.tags,
        )
    except ValueError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if note is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Không tìm thấy note")
    return {"ok": True, "note": note}


@router.post("/tools/notes/{note_id}/archive")
async def archive_note_endpoint(
    note_id: int,
    user_id: str = Query(DEFAULT_USER_ID, min_length=1, max_length=100),
):
    if not archive_note(note_id=note_id, user_id=user_id):
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Không tìm thấy note")
    return {"ok": True, "archived": True, "note_id": note_id, "user_id": user_id}


@router.get("/tools/reminders")
async def list_reminders_endpoint(
    user_id: str = Query(DEFAULT_USER_ID, min_length=1, max_length=100),
):
    return {
        "user_id": user_id,
        "upcoming": get_upcoming_reminders(user_id=user_id, limit=20),
        "due": get_due_reminders(user_id=user_id, limit=20),
    }


@router.post("/tools/reminders/{reminder_id}/complete")
async def complete_reminder_endpoint(
    reminder_id: int,
    user_id: str = Query(DEFAULT_USER_ID, min_length=1, max_length=100),
    payload: ReminderCompletionPayload = Body(default_factory=ReminderCompletionPayload),
):
    result = complete_reminder_with_feedback(
        reminder_id=reminder_id,
        user_id=user_id,
        completion_message=payload.completion_message,
        emotion=payload.emotion,
    )
    return {
        "ok": result.get("ok", False),
        "user_id": user_id,
        "reminder_id": reminder_id,
        "emotion": result.get("emotion", payload.emotion),
        "message": result.get("message", ""),
    }


@router.get("/tools/reminders/due-check")
async def due_reminder_check_endpoint(
    user_id: str = Query(DEFAULT_USER_ID, min_length=1, max_length=100),
):
    return trigger_due_reminder_notification(user_id=user_id)


@router.get("/tools/reminders/notifications")
async def due_reminder_notifications_endpoint(
    user_id: str = Query(DEFAULT_USER_ID, min_length=1, max_length=100),
):
    return deliver_due_reminder_notifications(user_id=user_id)


@router.get("/tools/reminders/background-scan")
async def background_reminder_scan_endpoint():
    return {"results": poll_due_reminder_notifications_for_all_users()}
