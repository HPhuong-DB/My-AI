"""Execution layer for decisions produced by the autonomous agent."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Mapping

from agent.decision_engine import AgentAction, Decision
from agent.events import Event
from agent.state_manager import AgentState

logger = logging.getLogger(__name__)

ActionHandler = Callable[[Decision, Event, AgentState], Awaitable[Mapping[str, Any] | None] | Mapping[str, Any] | None]


class ExecutionStatus:
    EXECUTED = "executed"
    DEFERRED = "deferred"
    IGNORED = "ignored"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    action: str
    status: str
    user_id: str
    event_id: str
    message: str = ""
    data: Mapping[str, Any] = field(default_factory=dict)


class AgentExecutor:
    """Dispatch approved decisions to safe, replaceable action handlers."""

    ALLOWED_ACTIONS = frozenset(
        {
            AgentAction.RESPOND,
            AgentAction.NOTIFY,
            AgentAction.IDLE_PROMPT,
            AgentAction.RESEARCH_RESULT,
        }
    )

    def __init__(self, handlers: Mapping[str, ActionHandler] | None = None) -> None:
        self._handlers: dict[str, ActionHandler] = dict(handlers or {})

    def register(self, action: str, handler: ActionHandler) -> None:
        if action not in self.ALLOWED_ACTIONS:
            raise ValueError(f"Action không được phép: {action}")
        self._handlers[action] = handler

    async def execute(
        self,
        decision: Decision,
        event: Event,
        state: AgentState,
    ) -> ExecutionResult:
        """Execute one decision and convert handler output to a stable result."""
        if decision.user_id != event.user_id or state.user_id != event.user_id:
            raise ValueError("Decision, event và state phải cùng user_id")
        if not decision.should_respond or decision.action == AgentAction.IGNORE:
            return ExecutionResult(
                action=decision.action,
                status=ExecutionStatus.IGNORED,
                user_id=event.user_id,
                event_id=event.event_id,
                message=decision.reason,
            )
        if decision.action not in self.ALLOWED_ACTIONS:
            return ExecutionResult(
                action=decision.action,
                status=ExecutionStatus.FAILED,
                user_id=event.user_id,
                event_id=event.event_id,
                message="action_not_allowed",
            )

        handler = self._handlers.get(decision.action)
        if handler is None:
            return ExecutionResult(
                action=decision.action,
                status=ExecutionStatus.DEFERRED,
                user_id=event.user_id,
                event_id=event.event_id,
                message="handler_not_registered",
            )

        try:
            output = handler(decision, event, state)
            if inspect.isawaitable(output):
                output = await output
            data = dict(output or {})
            return ExecutionResult(
                action=decision.action,
                status=ExecutionStatus.EXECUTED,
                user_id=event.user_id,
                event_id=event.event_id,
                message=str(data.pop("message", "")),
                data=data,
            )
        except Exception as exc:
            logger.exception("Executor lỗi với action=%s: %s", decision.action, exc)
            return ExecutionResult(
                action=decision.action,
                status=ExecutionStatus.FAILED,
                user_id=event.user_id,
                event_id=event.event_id,
                message="handler_failed",
            )
