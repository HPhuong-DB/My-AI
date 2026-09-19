"""API for explicitly approved, bounded self-learning updates."""

import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from agent.runtime import self_learning_service
from services.self_learning_service import SelfLearningError, SelfLearningRateLimitError, learning_policy

router = APIRouter()


class LearningPayload(BaseModel):
    target: Literal["memory", "knowledge", "experience"]
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1, max_length=12000)
    context: str = Field(default="", max_length=12000)
    source_url: str = Field(default="", max_length=2000)


@router.get("/self-learning/policy")
async def self_learning_policy_endpoint():
    policy = learning_policy()
    policy.update({
        "max_updates": self_learning_service.max_updates,
        "window_seconds": self_learning_service.window_seconds,
        "max_content_chars": self_learning_service.max_content_chars,
    })
    return policy


@router.post("/self-learning/learn")
async def self_learning_endpoint(
    payload: LearningPayload,
    user_id: str = Query("default", min_length=1, max_length=100),
):
    try:
        result = await asyncio.to_thread(
            self_learning_service.learn,
            user_id,
            target=payload.target,
            title=payload.title,
            content=payload.content,
            context=payload.context,
            source_url=payload.source_url,
        )
    except SelfLearningRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except SelfLearningError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not result.get("ok"):
        raise HTTPException(status_code=503, detail=result.get("error", "learning_failed"))
    return result
