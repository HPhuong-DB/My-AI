from fastapi import APIRouter, HTTPException, Query
import asyncio
from pydantic import BaseModel, Field
from services.session_service import user_lock

from services.memory_service import DEFAULT_USER_ID
from services.memory_orchestrator import memory_orchestrator
from services.mood_service import mood_manager

router = APIRouter()


@router.get("/memories")
def list_memories(
    user_id: str = Query(DEFAULT_USER_ID, min_length=1, max_length=100),
):
    snapshot = memory_orchestrator.personal_snapshot(user_id)
    memories = snapshot["memories"]
    profile = snapshot["profile"]
    mood_timeline = snapshot["mood_timeline"]
    return {
        "user_id": user_id,
        "profile": profile,
        "mood_timeline": mood_timeline,
        "mood_summary": mood_manager.summarize(user_id=user_id, limit=20, timeline=mood_timeline),
        "memories": memories,
    }


@router.get("/profile")
async def get_profile(
    user_id: str = Query(DEFAULT_USER_ID, min_length=1, max_length=100),
):
    snapshot = memory_orchestrator.personal_snapshot(user_id, memory_limit=0)
    return {
        "user_id": user_id,
        "profile": snapshot["profile"],
        "mood_timeline": snapshot["mood_timeline"],
    }


@router.get("/conversation-memory")
async def conversation_memory(
    user_id: str = Query(DEFAULT_USER_ID, min_length=1, max_length=100),
    session_limit: int = Query(10, ge=1, le=50),
    episode_limit: int = Query(40, ge=1, le=100),
):
    return await asyncio.to_thread(
        memory_orchestrator.conversation_snapshot,
        user_id,
        session_limit=session_limit,
        episode_limit=episode_limit,
    )


@router.get("/memory-audit")
async def memory_audit(
    user_id: str = Query(DEFAULT_USER_ID, min_length=1, max_length=100),
    limit: int = Query(100, ge=1, le=500),
):
    return {
        "user_id": user_id,
        "memories": await asyncio.to_thread(memory_orchestrator.audit, user_id, limit=limit),
    }


@router.post("/memories/forget-expired")
async def forget_expired(
    user_id: str = Query(DEFAULT_USER_ID, min_length=1, max_length=100),
):
    async with user_lock(user_id):
        return await asyncio.to_thread(memory_orchestrator.maintain, user_id, strict=True)


@router.delete("/memories/{memory_id}")
async def remove_memory(
    memory_id: int,
    user_id: str = Query(DEFAULT_USER_ID, min_length=1, max_length=100),
):
    async with user_lock(user_id):
        if not await asyncio.to_thread(memory_orchestrator.forget, memory_id, user_id):
            raise HTTPException(status_code=404, detail="Không tìm thấy memory")
    return {"deleted": True, "id": memory_id, "user_id": user_id}


class MemoryUpdate(BaseModel):
    fact: str = Field(min_length=1, max_length=2000)


@router.patch("/memories/{memory_id}")
async def edit_memory(memory_id: int, payload: MemoryUpdate, user_id: str = Query(DEFAULT_USER_ID, min_length=1, max_length=100)):
    async with user_lock(user_id):
        try:
            found = await asyncio.to_thread(memory_orchestrator.update, memory_id, payload.fact, user_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if not found:
            raise HTTPException(status_code=404, detail="Không tìm thấy memory")
    return {"updated": True, "id": memory_id, "user_id": user_id}
