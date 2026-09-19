"""Controls and diagnostics for the proactive scheduler."""

import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Query
from pydantic import BaseModel, StrictBool
from services import proactive_service
from services.session_service import user_lock

from agent.runtime import proactive_scheduler

router = APIRouter()


class ProactiveSettings(BaseModel):
    enabled: StrictBool


def serialize_preferences(settings):
    return {key: value.replace(tzinfo=timezone.utc) if isinstance(value, datetime) else value
            for key, value in settings.items()}


@router.get('/proactive/preferences')
async def read_preferences(user_id: str = Query('default', min_length=1, max_length=100)):
    return serialize_preferences(await asyncio.to_thread(proactive_service.preferences, user_id))


@router.patch('/proactive/preferences')
async def update_preferences(payload: ProactiveSettings, user_id: str = Query('default', min_length=1, max_length=100)):
    async with user_lock(user_id):
        return serialize_preferences(await asyncio.to_thread(proactive_service.set_enabled, user_id, payload.enabled))


@router.get("/proactive/status")
async def proactive_status():
    return {
        "running": proactive_scheduler.running,
        "interval_seconds": proactive_scheduler.interval_seconds,
        "cooldown_seconds": proactive_scheduler.cooldown_seconds,
        "idle_after_seconds": proactive_scheduler.idle_after_seconds,
        "max_events_per_cycle": proactive_scheduler.max_events_per_cycle,
        "max_events_per_window": proactive_scheduler.max_events_per_window,
        "action_window_seconds": proactive_scheduler.action_window_seconds,
        "user_cooldown_seconds": proactive_scheduler.user_cooldown_seconds,
        "max_events_per_user_window": proactive_scheduler.max_events_per_user_window,
        "interaction_engine": proactive_scheduler.interaction_engine.stats(),
    }


@router.post("/proactive/check")
async def proactive_check():
    events = await proactive_scheduler.tick()
    return {
        "ok": True,
        "events_emitted": len(events),
        "event_ids": [event.event_id for event in events],
    }
