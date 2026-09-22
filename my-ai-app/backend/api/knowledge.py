from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.knowledge_service import list_experiences
from services.memory_orchestrator import memory_orchestrator

router = APIRouter()


class ExperiencePayload(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    lesson: str = Field(..., min_length=1, max_length=10000)
    context: str = Field(default="", max_length=10000)
    source_type: str = Field(default="goal", max_length=50)
    source_id: int | None = None
    source_ref: str | None = Field(default=None, max_length=255)
    confidence: float = Field(default=0.80, ge=0, le=1)
    importance: float = Field(default=0.75, ge=0, le=1)
    expires_at: datetime | None = None


@router.get("/long-term-memory")
async def long_term_memory_endpoint(user_id: str = Query("default", min_length=1, max_length=100), query: str = "", limit: int = Query(10, ge=1, le=50)):
    return memory_orchestrator.recall_long_term(user_id, query, limit)


@router.post("/experiences")
async def save_experience_endpoint(payload: ExperiencePayload, user_id: str = Query("default", min_length=1, max_length=100)):
    try:
        experience = memory_orchestrator.remember_experience(
            user_id,
            payload.title,
            payload.lesson,
            payload.context,
            payload.source_type,
            payload.source_id,
            source_ref=payload.source_ref,
            confidence=payload.confidence,
            importance=payload.importance,
            expires_at=payload.expires_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if experience is None:
        raise HTTPException(status_code=503, detail="Không thể lưu experience")
    return {"ok": True, "experience": experience}


@router.get("/experiences")
async def list_experiences_endpoint(user_id: str = Query("default", min_length=1, max_length=100), limit: int = Query(20, ge=1, le=50)):
    return {"user_id": user_id, "experiences": list_experiences(user_id, limit)}
