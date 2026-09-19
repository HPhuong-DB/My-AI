"""In-process state for Huohuo's autonomous behavior."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Mapping

from agent.events import Event, EventType
from agent.perception import PerceptionSource, parse_perception_event


class AgentActivity:
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    WORKING = "working"


@dataclass(slots=True)
class AgentState:
    """Current runtime state for one user/agent relationship."""

    user_id: str
    mood: str = "neutral"
    energy: float = 1.0
    activity: str = AgentActivity.IDLE
    is_speaking: bool = False
    autonomous_enabled: bool = True
    emergency_stopped: bool = False
    last_interaction: datetime | None = None
    last_action: str | None = None
    last_action_at: datetime | None = None
    interaction_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class StateManager:
    """Manage isolated runtime state without persisting it to the database yet."""

    def __init__(self, *, default_energy: float = 1.0) -> None:
        self._states: dict[str, AgentState] = {}
        self._default_energy = self._clamp_energy(default_energy)
        self._emergency_stopped = False

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _clamp_energy(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @staticmethod
    def _validate_user_id(user_id: str) -> str:
        if not user_id or not user_id.strip():
            raise ValueError("State user_id không được để trống")
        return user_id

    def _get_or_create(self, user_id: str) -> AgentState:
        user_id = self._validate_user_id(user_id)
        if user_id not in self._states:
            self._states[user_id] = AgentState(
                user_id=user_id,
                energy=self._default_energy,
                emergency_stopped=self._emergency_stopped,
            )
        return self._states[user_id]

    @staticmethod
    def _copy(state: AgentState) -> AgentState:
        return replace(state, metadata=dict(state.metadata))

    def get_state(self, user_id: str = "default") -> AgentState:
        """Return a snapshot so callers cannot mutate manager state directly."""
        return self._copy(self._get_or_create(user_id))

    def user_ids(self) -> tuple[str, ...]:
        """Return users with an in-memory state snapshot."""
        return tuple(self._states)

    def update(
        self,
        user_id: str = "default",
        *,
        mood: str | None = None,
        energy: float | None = None,
        activity: str | None = None,
        autonomous_enabled: bool | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> AgentState:
        state = self._get_or_create(user_id)
        if mood is not None:
            if not mood.strip():
                raise ValueError("State mood không được để trống")
            state.mood = mood.strip()
        if energy is not None:
            state.energy = self._clamp_energy(energy)
        if activity is not None:
            if not activity.strip():
                raise ValueError("State activity không được để trống")
            state.activity = activity.strip()
            state.is_speaking = state.activity == AgentActivity.SPEAKING
        if autonomous_enabled is not None:
            state.autonomous_enabled = bool(autonomous_enabled)
        if metadata is not None:
            state.metadata.update(dict(metadata))
        return self._copy(state)

    def record_interaction(self, user_id: str = "default", *, mood: str | None = None) -> AgentState:
        state = self._get_or_create(user_id)
        state.last_interaction = self._now()
        state.interaction_count += 1
        state.activity = AgentActivity.LISTENING
        state.is_speaking = False
        if mood:
            state.mood = mood.strip()
        return self._copy(state)

    def record_action(self, action: str, user_id: str = "default") -> AgentState:
        if not action or not action.strip():
            raise ValueError("State action không được để trống")
        state = self._get_or_create(user_id)
        state.last_action = action.strip()
        state.last_action_at = self._now()
        return self._copy(state)

    def apply_event(self, event: Event) -> AgentState:
        """Apply the minimal state transition known by the initial agent core."""
        state = self._get_or_create(event.user_id)
        if event.type == EventType.USER_MESSAGE:
            return self.record_interaction(event.user_id, mood=event.payload.get("mood"))
        if event.type == EventType.IDLE_TIMEOUT:
            return self.update(event.user_id, activity=AgentActivity.IDLE)
        if event.type == EventType.REMINDER_DUE:
            return self.update(event.user_id, activity=AgentActivity.WORKING)
        if event.type == EventType.PERCEPTION_INPUT:
            perception = parse_perception_event(event)
            activity = (
                AgentActivity.LISTENING
                if perception.source == PerceptionSource.MICROPHONE
                else AgentActivity.THINKING
            )
            return self.update(
                event.user_id,
                activity=activity,
                metadata={
                    "last_perception_source": perception.source,
                    "last_perception_type": perception.content_type,
                    "last_perception_confidence": perception.confidence,
                },
            )
        return self._copy(state)

    def set_speaking(self, speaking: bool, user_id: str = "default") -> AgentState:
        return self.update(
            user_id,
            activity=AgentActivity.SPEAKING if speaking else AgentActivity.IDLE,
        )

    @property
    def emergency_stopped(self) -> bool:
        return self._emergency_stopped

    def set_emergency_stop(self, stopped: bool = True) -> None:
        """Enable/disable the global kill switch for autonomous actions."""
        self._emergency_stopped = bool(stopped)
        for state in self._states.values():
            state.emergency_stopped = self._emergency_stopped

    def remove(self, user_id: str) -> None:
        self._states.pop(self._validate_user_id(user_id), None)

    def clear(self) -> None:
        self._states.clear()
