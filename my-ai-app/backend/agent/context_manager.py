"""Short-lived context awareness built from agent events and runtime state."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from agent.events import Event, EventType
from agent.state_manager import AgentActivity, AgentState


@dataclass(frozen=True, slots=True)
class ContextSnapshot:
    user_id: str
    mood: str
    energy: float
    activity: str
    attention: str
    current_topic: str | None
    last_input_source: str | None
    last_input_type: str | None
    recent_events: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["updated_at"] = self.updated_at.isoformat()
        data["recent_events"] = list(self.recent_events)
        return data


class ContextManager:
    """Maintain bounded, non-persistent context for autonomous decisions."""

    def __init__(self, *, max_recent_events: int = 12, max_preview_chars: int = 240) -> None:
        if max_recent_events <= 0 or max_preview_chars <= 0:
            raise ValueError("Giới hạn context phải lớn hơn 0")
        self._max_preview_chars = max_preview_chars
        self._events: dict[str, deque[dict[str, Any]]] = {}
        self._snapshots: dict[str, ContextSnapshot] = {}
        self._max_recent_events = max_recent_events

    @staticmethod
    def _attention(activity: str) -> str:
        if activity in {AgentActivity.LISTENING, AgentActivity.THINKING, AgentActivity.WORKING}:
            return "focused"
        if activity == AgentActivity.IDLE:
            return "available"
        return "unknown"

    def _preview(self, event: Event) -> str | None:
        payload = event.payload
        value = payload.get("text") or payload.get("content") or payload.get("question")
        if value is None:
            return None
        return str(value).strip()[: self._max_preview_chars]

    def observe(self, event: Event, state: AgentState) -> ContextSnapshot:
        if event.user_id != state.user_id:
            raise ValueError("Event và state phải cùng user_id")

        history = self._events.setdefault(
            event.user_id,
            deque(maxlen=self._max_recent_events),
        )
        item = {
            "event_id": event.event_id,
            "type": event.type,
            "created_at": event.created_at.isoformat(),
        }
        preview = self._preview(event)
        if preview:
            item["preview"] = preview
        if event.type == EventType.PERCEPTION_INPUT:
            item["source"] = event.payload.get("source")
            item["content_type"] = event.payload.get("content_type")
        history.append(item)

        snapshot = ContextSnapshot(
            user_id=state.user_id,
            mood=state.mood,
            energy=state.energy,
            activity=state.activity,
            attention=self._attention(state.activity),
            current_topic=preview,
            last_input_source=state.metadata.get("last_perception_source"),
            last_input_type=state.metadata.get("last_perception_type"),
            recent_events=tuple(history),
        )
        self._snapshots[event.user_id] = snapshot
        return snapshot

    def get(self, user_id: str = "default") -> ContextSnapshot | None:
        return self._snapshots.get(user_id)

    def clear(self, user_id: str | None = None) -> None:
        if user_id is None:
            self._events.clear()
            self._snapshots.clear()
            return
        self._events.pop(user_id, None)
        self._snapshots.pop(user_id, None)
