from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.knowledge_service import get_long_term_memory, list_experiences, save_experience

router = APIRouter()


class ExperiencePayload(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    lesson: str = Field(..., min_length=1, max_length=10000)
    context: str = Field(default="", max_length=10000)
    source_type: str = Field(default="goal", max_length=50)
    source_id: int | None = None


@router.get("/long-term-memory")
async def long_term_memory_endpoint(user_id: str = Query("default", min_length=1, max_length=100), query: str = "", limit: int = Query(10, ge=1, le=50)):
    return get_long_term_memory(user_id, query, limit)


@router.post("/experiences")
async def save_experience_endpoint(payload: ExperiencePayload, user_id: str = Query("default", min_length=1, max_length=100)):
    try:
        experience = save_experience(user_id, payload.title, payload.lesson, payload.context, payload.source_type, payload.source_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if experience is None:
        raise HTTPException(status_code=503, detail="Không thể lưu experience")
    return {"ok": True, "experience": experience}


@router.get("/experiences")
async def list_experiences_endpoint(user_id: str = Query("default", min_length=1, max_length=100), limit: int = Query(20, ge=1, le=50)):
    return {"user_id": user_id, "experiences": list_experiences(user_id, limit)}
