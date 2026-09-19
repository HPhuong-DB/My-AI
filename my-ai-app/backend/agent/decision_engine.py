"""Rule-based decision layer for Huohuo's autonomous agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from agent.events import Event, EventType
from agent.state_manager import AgentState


class AgentAction:
    RESPOND = "respond"
    NOTIFY = "notify"
    IDLE_PROMPT = "idle_prompt"
    RESEARCH_RESULT = "research_result"
    IGNORE = "ignore"


@dataclass(frozen=True, slots=True)
class Decision:
    """Decision produced for one event; execution happens elsewhere."""

    should_respond: bool
    action: str
    reason: str
    user_id: str
    event_id: str
    response_mode: str = "fast"
    metadata: Mapping[str, Any] = field(default_factory=dict)


class DecisionEngine:
    """Make deterministic, inexpensive decisions before invoking an LLM."""

    def __init__(
        self,
        *,
        idle_after_seconds: float = 300,
        idle_cooldown_seconds: float = 300,
        action_cooldown_seconds: float = 10,
        minimum_energy: float = 0.05,
    ) -> None:
        if idle_after_seconds < 0 or idle_cooldown_seconds < 0 or action_cooldown_seconds < 0:
            raise ValueError("Các cooldown không được âm")
        if not 0 <= minimum_energy <= 1:
            raise ValueError("minimum_energy phải nằm trong khoảng 0 đến 1")
        self.idle_after = timedelta(seconds=idle_after_seconds)
        self.idle_cooldown = timedelta(seconds=idle_cooldown_seconds)
        self.action_cooldown = timedelta(seconds=action_cooldown_seconds)
        self.minimum_energy = minimum_energy

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _ignored(event: Event, reason: str) -> Decision:
        return Decision(
            should_respond=False,
            action=AgentAction.IGNORE,
            reason=reason,
            user_id=event.user_id,
            event_id=event.event_id,
        )

    def _is_in_cooldown(self, state: AgentState, now: datetime, cooldown: timedelta) -> bool:
        return bool(state.last_action_at and now - state.last_action_at < cooldown)

    def decide(self, event: Event, state: AgentState, *, now: datetime | None = None) -> Decision:
        """Return a decision without mutating the supplied event or state."""
        if event.user_id != state.user_id:
            raise ValueError("Event và state phải cùng user_id")
        reference_time = now or self._now()

        if state.emergency_stopped:
            return self._ignored(event, "emergency_stop_enabled")
        if not state.autonomous_enabled and event.type != EventType.USER_MESSAGE:
            return self._ignored(event, "autonomous_mode_disabled")
        if state.energy < self.minimum_energy and event.type != EventType.USER_MESSAGE:
            return self._ignored(event, "agent_energy_too_low")
        if state.is_speaking and event.type == EventType.IDLE_TIMEOUT:
            return self._ignored(event, "agent_is_already_speaking")

        if event.type == EventType.USER_MESSAGE:
            return Decision(
                should_respond=True,
                action=AgentAction.RESPOND,
                reason="user_message_requires_response",
                user_id=event.user_id,
                event_id=event.event_id,
                response_mode=str(event.payload.get("response_mode", "auto")),
            )

        if event.type == EventType.REMINDER_DUE:
            if self._is_in_cooldown(state, reference_time, self.action_cooldown):
                return self._ignored(event, "action_cooldown")
            return Decision(
                should_respond=True,
                action=AgentAction.NOTIFY,
                reason="reminder_is_due",
                user_id=event.user_id,
                event_id=event.event_id,
                metadata={"reminder_id": event.payload.get("reminder_id")},
            )

        if event.type == EventType.IDLE_TIMEOUT:
            if not state.last_interaction:
                return self._ignored(event, "no_interaction_history")
            if reference_time - state.last_interaction < self.idle_after:
                return self._ignored(event, "idle_threshold_not_reached")
            if self._is_in_cooldown(state, reference_time, self.idle_cooldown):
                return self._ignored(event, "idle_cooldown")
            return Decision(
                should_respond=True,
                action=AgentAction.IDLE_PROMPT,
                reason="user_has_been_idle",
                user_id=event.user_id,
                event_id=event.event_id,
            )

        if event.type == EventType.RESEARCH_COMPLETED:
            return Decision(
                should_respond=True,
                action=AgentAction.RESEARCH_RESULT,
                reason="research_completed",
                user_id=event.user_id,
                event_id=event.event_id,
                response_mode="deep",
            )

        return self._ignored(event, "event_type_not_actionable")
