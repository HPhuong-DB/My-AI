"""WebSocket transport for agent events sent to the frontend."""

import asyncio
import json
import os
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from agent.runtime import output_bus, proactive_scheduler
from core.database import DatabaseUnavailable

router = APIRouter()


def _event_message(event) -> dict:
    return {
        "type": event.type,
        "event_id": event.event_id,
        "user_id": event.user_id,
        "created_at": event.created_at.isoformat(),
        "payload": dict(event.payload),
    }


@router.websocket("/ws")
async def agent_websocket(websocket: WebSocket):
    origin = websocket.headers.get("origin")
    allowed_origins = {
        item.strip()
        for item in os.getenv(
            "WS_ALLOWED_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,http://127.0.0.1:5174",
        ).split(",")
        if item.strip()
    }
    if origin and origin not in allowed_origins:
        await websocket.close(code=1008, reason="Origin không được phép")
        return
    user_id = websocket.query_params.get("user_id", "default").strip()
    if not user_id or len(user_id) > 100:
        await websocket.close(code=1008, reason="user_id không hợp lệ")
        return

    await websocket.accept()
    connection_id = uuid4().hex
    subscription = output_bus.subscribe()
    event_task = asyncio.create_task(subscription.get())
    receive_task = asyncio.create_task(websocket.receive_text())

    try:
        await websocket.send_json({"type": "connected", "user_id": user_id})
        while True:
            done, _ = await asyncio.wait(
                {event_task, receive_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            if event_task in done:
                event = event_task.result()
                if event.user_id == user_id:
                    await websocket.send_json(_event_message(event))
                event_task = asyncio.create_task(subscription.get())

            if receive_task in done:
                message = receive_task.result()
                if message.strip().lower() == "ping":
                    await websocket.send_json({"type": "pong"})
                else:
                    try:
                        payload = json.loads(message)
                    except json.JSONDecodeError:
                        payload = {}
                    if not isinstance(payload, dict):
                        payload = {}
                    if payload.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                    elif payload.get('type') == 'presence':
                        proactive_scheduler.presence.update(connection_id, user_id, payload)
                    elif payload.get('type') == 'proactive_seen' and isinstance(payload.get('event_id'), str):
                        try:
                            accepted = await proactive_scheduler.acknowledge(user_id, payload['event_id'])
                        except DatabaseUnavailable:
                            accepted = False
                        await websocket.send_json({'type': 'proactive_ack', 'accepted': accepted})
                receive_task = asyncio.create_task(websocket.receive_text())
    except (WebSocketDisconnect, RuntimeError, asyncio.CancelledError):
        pass
    finally:
        proactive_scheduler.presence.remove(connection_id)
        subscription.close()
        for task in (event_task, receive_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(event_task, receive_task, return_exceptions=True)
