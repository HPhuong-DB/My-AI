"""Runtime controls for the personal autonomous agent."""

from typing import Literal

from fastapi import APIRouter, Body, Query
from pydantic import BaseModel

from agent.runtime import context_manager, privacy_manager, state_manager

router = APIRouter()


class ConsentPayload(BaseModel):
    permission: Literal["microphone", "screen", "document", "image"]
    granted: bool


@router.get("/agent/state")
async def get_agent_state(user_id: str = Query("default", min_length=1, max_length=100)):
    state = state_manager.get_state(user_id)
    return {
        "user_id": state.user_id,
        "mood": state.mood,
        "energy": state.energy,
        "activity": state.activity,
        "is_speaking": state.is_speaking,
        "autonomous_enabled": state.autonomous_enabled,
        "emergency_stopped": state.emergency_stopped,
        "last_interaction": state.last_interaction,
        "last_action": state.last_action,
        "last_action_at": state.last_action_at,
        "interaction_count": state.interaction_count,
    }


@router.post("/agent/emergency-stop")
async def emergency_stop():
    state_manager.set_emergency_stop(True)
    privacy_manager.revoke_capture_permissions()
    return {"ok": True, "emergency_stopped": True}


@router.post("/agent/resume")
async def resume_agent():
    state_manager.set_emergency_stop(False)
    return {"ok": True, "emergency_stopped": False}


@router.get("/privacy/consent")
async def get_privacy_consent(user_id: str = Query("default", min_length=1, max_length=100)):
    return {"user_id": user_id, "consent": privacy_manager.get_consents(user_id)}


@router.post("/privacy/consent")
async def set_privacy_consent(
    payload: ConsentPayload = Body(...),
    user_id: str = Query("default", min_length=1, max_length=100),
):
    privacy_manager.set_consent(user_id, payload.permission, payload.granted)
    return {"ok": True, "user_id": user_id, "consent": privacy_manager.get_consents(user_id)}


@router.get("/privacy/audit")
async def get_privacy_audit(
    user_id: str = Query("default", min_length=1, max_length=100),
    limit: int = Query(50, ge=1, le=100),
):
    return {"user_id": user_id, "entries": privacy_manager.get_audit(user_id, limit=limit)}


@router.get("/agent/context")
async def get_agent_context(user_id: str = Query("default", min_length=1, max_length=100)):
    context = context_manager.get(user_id)
    return {
        "user_id": user_id,
        "context": context.to_dict() if context else None,
    }
