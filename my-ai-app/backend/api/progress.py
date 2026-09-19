from fastapi import APIRouter, Query

from services.progress_service import evaluate_progress

router = APIRouter()


@router.get("/progress/evaluate")
async def evaluate_progress_endpoint(user_id: str = Query("default", min_length=1, max_length=100), include_archived: bool = False):
    return evaluate_progress(user_id, include_archived)
