"""Mood and relationship views for the personality layer."""

from fastapi import APIRouter, Query

from services.mood_service import mood_manager
from services.relationship_service import get_relationship

router = APIRouter()


@router.get("/mood/summary")
async def mood_summary(
    user_id: str = Query("default", min_length=1, max_length=100),
    limit: int = Query(20, ge=1, le=100),
):
    return mood_manager.summarize(user_id, limit)


@router.post("/mood/analyze")
async def analyze_mood(message: str):
    return mood_manager.analyze_message(message)


@router.get("/relationship")
async def relationship_state(user_id: str = Query("default", min_length=1, max_length=100)):
    return get_relationship(user_id)
