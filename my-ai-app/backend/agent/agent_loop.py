"""Runtime loop that connects events, state and decisions."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable

from agent.decision_engine import Decision, DecisionEngine
from agent.context_manager import ContextManager
from agent.event_bus import EventBus, EventBusClosed
from agent.events import Event
from agent.state_manager import AgentState, StateManager

logger = logging.getLogger(__name__)

DecisionHandler = Callable[[Decision, Event, AgentState], Awaitable[None] | None]


class AgentLoop:
    """Consume events and delegate approved actions to an executor callback."""

    def __init__(
        self,
        event_bus: EventBus,
        state_manager: StateManager,
        decision_engine: DecisionEngine,
        *,
        on_decision: DecisionHandler | None = None,
        context_manager: ContextManager | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.state_manager = state_manager
        self.decision_engine = decision_engine
        self.on_decision = on_decision
        self.context_manager = context_manager
        self._task: asyncio.Task[None] | None = None
        self._stopping = False

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> asyncio.Task[None]:
        """Start the background loop and return its task."""
        if self.running:
            return self._task  # type: ignore[return-value]
        self._stopping = False
        self._task = asyncio.create_task(self.run(), name="huohuo-agent-loop")
        return self._task

    async def run(self) -> None:
        """Process events until stopped or the Event Bus is closed."""
        try:
            while not self._stopping:
                event = await self.event_bus.get()
                await self.process_event(event)
        except EventBusClosed:
            logger.info("Agent Loop dừng vì Event Bus đã đóng")
        except asyncio.CancelledError:
            logger.info("Agent Loop đã bị cancel")
            raise

    async def process_event(self, event: Event) -> Decision:
        """Apply one event and execute its decision if actionable."""
        state = self.state_manager.apply_event(event)
        if self.context_manager is not None:
            self.context_manager.observe(event, state)
        decision = self.decision_engine.decide(event, state)
        if not decision.should_respond:
            logger.debug("Bỏ qua event %s: %s", event.type, decision.reason)
            return decision

        self.state_manager.record_action(decision.action, user_id=event.user_id)
        if self.on_decision is not None:
            result = self.on_decision(decision, event, self.state_manager.get_state(event.user_id))
            if inspect.isawaitable(result):
                await result
        return decision

    async def stop(self, *, cancel: bool = True) -> None:
        """Stop the loop; optionally cancel a task waiting for a new event."""
        self._stopping = True
        task = self._task
        if task is None:
            return
        if cancel and not task.done():
            task.cancel()
        if not task.done():
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._task = None
