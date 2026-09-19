"""Read-only personality contract exposed to the frontend."""

from fastapi import APIRouter

from services.personality_service import personality_engine

router = APIRouter()


@router.get("/personality")
async def personality_profile():
    return personality_engine.public_profile()
