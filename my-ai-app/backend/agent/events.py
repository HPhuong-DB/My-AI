"""Event primitives shared by the autonomous agent components."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4


class EventType:
    """Names of events understood by the first agent iteration."""

    USER_MESSAGE = "user_message"
    TIMER_TICK = "timer_tick"
    REMINDER_DUE = "reminder_due"
    IDLE_TIMEOUT = "idle_timeout"
    RESEARCH_COMPLETED = "research_completed"
    AGENT_OUTPUT = "agent_output"
    PERCEPTION_INPUT = "perception_input"
    PERCEPTION_STARTED = "perception_started"
    PERCEPTION_COMPLETED = "perception_completed"
    PERCEPTION_FAILED = "perception_failed"
    PROACTIVE_REMINDER = "proactive_reminder"
    PROACTIVE_SUGGESTION = "proactive_suggestion"
    SYSTEM = "system_event"


@dataclass(frozen=True, slots=True)
class Event:
    """An immutable event envelope.

    Payload remains intentionally flexible because different integrations will
    eventually produce different event data. The envelope itself stays stable.
    """

    type: str
    user_id: str = "default"
    payload: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_id: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self) -> None:
        if not self.type or not self.type.strip():
            raise ValueError("Event type không được để trống")
        if not self.user_id or not self.user_id.strip():
            raise ValueError("Event user_id không được để trống")
        if self.created_at.tzinfo is None:
            raise ValueError("Event created_at phải có timezone")

    @classmethod
    def create(
        cls,
        event_type: str,
        *,
        user_id: str = "default",
        payload: Mapping[str, Any] | None = None,
    ) -> "Event":
        return cls(
            type=event_type,
            user_id=user_id,
            payload=dict(payload or {}),
        )
