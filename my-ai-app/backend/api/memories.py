from fastapi import APIRouter, HTTPException, Query
import asyncio
from pydantic import BaseModel, Field
from services.session_service import user_lock

from services.memory_service import (
    DEFAULT_USER_ID,
    delete_memory,
    update_memory,
    get_recent_memories,
    get_user_mood_timeline,
    get_user_profile,
)
from services.mood_service import mood_manager

router = APIRouter()


@router.get("/memories")
def list_memories(
    user_id: str = Query(DEFAULT_USER_ID, min_length=1, max_length=100),
):
    memories = get_recent_memories(limit=100, user_id=user_id, strict=True)
    profile = get_user_profile(user_id=user_id)
    mood_timeline = get_user_mood_timeline(user_id=user_id, limit=20)
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
    return {
        "user_id": user_id,
        "profile": get_user_profile(user_id=user_id),
        "mood_timeline": get_user_mood_timeline(user_id=user_id, limit=20),
    }


@router.delete("/memories/{memory_id}")
async def remove_memory(
    memory_id: int,
    user_id: str = Query(DEFAULT_USER_ID, min_length=1, max_length=100),
):
    async with user_lock(user_id):
        if not await asyncio.to_thread(delete_memory, memory_id, user_id):
            raise HTTPException(status_code=404, detail="Không tìm thấy memory")
    return {"deleted": True, "id": memory_id, "user_id": user_id}


class MemoryUpdate(BaseModel):
    fact: str = Field(min_length=1, max_length=2000)


@router.patch("/memories/{memory_id}")
async def edit_memory(memory_id: int, payload: MemoryUpdate, user_id: str = Query(DEFAULT_USER_ID, min_length=1, max_length=100)):
    async with user_lock(user_id):
        try:
            found = await asyncio.to_thread(update_memory, memory_id, payload.fact, user_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if not found:
            raise HTTPException(status_code=404, detail="Không tìm thấy memory")
    return {"updated": True, "id": memory_id, "user_id": user_id}
