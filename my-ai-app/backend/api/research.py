from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from services.research_service import list_knowledge, run_research

router = APIRouter()


class ResearchPayload(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)
    max_sources: int = Field(default=3, ge=1, le=5)
    save: bool = True


@router.post("/research")
async def research_endpoint(payload: ResearchPayload, user_id: str = Query("default", min_length=1, max_length=100)):
    return await run_research(payload.query, user_id, payload.max_sources, payload.save)


@router.get("/knowledge")
async def knowledge_endpoint(user_id: str = Query("default", min_length=1, max_length=100), limit: int = Query(20, ge=1, le=50)):
    return {"user_id": user_id, "knowledge": list_knowledge(user_id, limit)}
