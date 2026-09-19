"""Shared runtime instances used by the FastAPI application."""

import logging
import os

from agent.agent_loop import AgentLoop
from agent.context_manager import ContextManager
from agent.decision_engine import DecisionEngine, Decision
from agent.event_bus import EventBus
from agent.events import Event, EventType
from agent.executor import AgentExecutor, ExecutionResult
from agent.state_manager import AgentState, StateManager
from agent.privacy import PrivacyManager
from agent.proactive_scheduler import ProactiveScheduler
from services.self_learning_service import SelfLearningService

logger = logging.getLogger("uvicorn.error")

event_bus = EventBus()
output_bus = EventBus()
state_manager = StateManager()
context_manager = ContextManager()
privacy_manager = PrivacyManager()
decision_engine = DecisionEngine(
    idle_after_seconds=float(os.getenv("AGENT_IDLE_AFTER_SECONDS")),
    idle_cooldown_seconds=float(os.getenv("AGENT_IDLE_COOLDOWN_SECONDS")),
    action_cooldown_seconds=float(os.getenv("AGENT_ACTION_COOLDOWN_SECONDS")),
    minimum_energy=float(os.getenv("AGENT_MINIMUM_ENERGY")),
)


executor = AgentExecutor()


async def execute_decision(decision: Decision, event: Event, state: AgentState) -> None:
    result: ExecutionResult = await executor.execute(decision, event, state)
    await output_bus.publish(
        Event.create(
            EventType.AGENT_OUTPUT,
            user_id=event.user_id,
            payload={
                "source_event": event.type,
                "action": decision.action,
                "status": result.status,
                "reason": decision.reason,
                "data": dict(result.data),
            },
        )
    )
    logger.info(
        "[agent] event=%s user=%s action=%s decision=%s execution=%s reason=%s activity=%s",
        event.type,
        event.user_id,
        decision.action,
        decision.should_respond,
        result.status,
        decision.reason,
        state.activity,
    )


agent_loop = AgentLoop(
    event_bus,
    state_manager,
    decision_engine,
    on_decision=execute_decision,
    context_manager=context_manager,
)

proactive_scheduler = ProactiveScheduler(
    output_bus,
    state_manager,
    interval_seconds=float(os.getenv("REMINDER_SCHEDULER_INTERVAL_SECONDS", "60")),
    cooldown_seconds=float(os.getenv("PROACTIVE_SCHEDULER_COOLDOWN_SECONDS", "900")),
    idle_after_seconds=float(os.getenv("AGENT_IDLE_AFTER_SECONDS", "300")),
    max_events_per_cycle=int(os.getenv("PROACTIVE_MAX_EVENTS_PER_CYCLE", "5")),
    max_events_per_window=int(os.getenv("PROACTIVE_MAX_EVENTS_PER_WINDOW", "30")),
    action_window_seconds=float(os.getenv("PROACTIVE_ACTION_WINDOW_SECONDS", "3600")),
    user_cooldown_seconds=float(os.getenv("PROACTIVE_USER_COOLDOWN_SECONDS", "900")),
    max_events_per_user_window=int(os.getenv("PROACTIVE_MAX_EVENTS_PER_USER_WINDOW", "3")),
)

self_learning_service = SelfLearningService(
    state_manager,
    max_updates=int(os.getenv("SELF_LEARNING_MAX_UPDATES", "10")),
    window_seconds=float(os.getenv("SELF_LEARNING_WINDOW_SECONDS", "3600")),
    max_content_chars=int(os.getenv("SELF_LEARNING_MAX_CONTENT_CHARS", "12000")),
)
