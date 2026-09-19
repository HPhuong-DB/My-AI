"""Safe, cooldown-aware scheduler for reminders and progress suggestions."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import Any

from agent.event_bus import EventBus
from agent.events import Event, EventType
from agent.state_manager import StateManager
from services.interaction_service import NaturalInteractionEngine
from agent.presence import Presence
from services import proactive_service as context
from services.chat_service import get_recent_chat_history, save_chat_message
from services.memory_service import get_recent_memories
from services.session_service import user_lock
from services.progress_service import evaluate_progress
from services.tool_service import poll_due_reminder_notifications_for_all_users

logger = logging.getLogger("uvicorn.error")


class ProactiveScheduler:
    """Periodically publish safe suggestions to the output event bus.

    The scheduler only observes reminders/goals and emits UI events. It does
    not call the LLM, mutate goals, complete reminders, or execute tools.
    """

    _RISK_STATUSES = frozenset({"at_risk", "stalled", "overdue"})

    def __init__(
        self,
        output_bus: EventBus,
        state_manager: StateManager,
        *,
        interval_seconds: float = 60,
        cooldown_seconds: float = 900,
        idle_after_seconds: float = 300,
        max_events_per_cycle: int = 5,
        max_events_per_window: int = 30,
        action_window_seconds: float = 3600,
        user_cooldown_seconds: float = 900,
        max_events_per_user_window: int = 3,
        presence: Presence | None = None,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds phải lớn hơn 0")
        if cooldown_seconds < 0:
            raise ValueError("cooldown_seconds không được âm")
        if idle_after_seconds < 0:
            raise ValueError("idle_after_seconds không được âm")
        if max_events_per_cycle <= 0 or max_events_per_window <= 0:
            raise ValueError("Giới hạn event phải lớn hơn 0")
        if action_window_seconds <= 0:
            raise ValueError("action_window_seconds phải lớn hơn 0")
        if user_cooldown_seconds < 0 or max_events_per_user_window <= 0:
            raise ValueError("Giới hạn theo user không hợp lệ")
        self.output_bus = output_bus
        self.state_manager = state_manager
        self.interval_seconds = float(interval_seconds)
        self.cooldown_seconds = float(cooldown_seconds)
        self.idle_after_seconds = float(idle_after_seconds)
        self.max_events_per_cycle = int(max_events_per_cycle)
        self.max_events_per_window = int(max_events_per_window)
        self.action_window_seconds = float(action_window_seconds)
        self.user_cooldown_seconds = float(user_cooldown_seconds)
        self.max_events_per_user_window = int(max_events_per_user_window)
        self._task: asyncio.Task[None] | None = None
        self._tick_lock = asyncio.Lock()
        self._last_emitted: dict[tuple[str, str, str], float] = {}
        self._window_started = time.monotonic()
        self._window_emitted = 0
        self._cycle_emitted = 0
        self._user_emitted: dict[str, deque[float]] = defaultdict(deque)
        self.interaction_engine = NaturalInteractionEngine()
        self.presence = presence or Presence()
        self._pending = {}
        self.last_reason: dict[str, str] = {}

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        """Start the background loop once the application event loop exists."""
        if self.running:
            return
        self._task = asyncio.create_task(self._run(), name="proactive-scheduler")

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def _run(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[proactive] scheduler tick thất bại")
            await asyncio.sleep(self.interval_seconds)

    def _allowed_for_user(self, user_id: str) -> bool:
        state = self.state_manager.get_state(user_id)
        return not state.emergency_stopped and state.autonomous_enabled and not state.is_speaking and self.presence.reason(user_id) is None

    def _should_emit(self, user_id: str, kind: str, key: str) -> bool:
        now = time.monotonic()
        event_key = (user_id, kind, key)
        last = self._last_emitted.get(event_key)
        if last is not None and now - last < self.cooldown_seconds:
            return False
        self._last_emitted[event_key] = now
        return True

    def _reset_budget(self) -> None:
        now = time.monotonic()
        if now - self._window_started >= self.action_window_seconds:
            self._window_started = now
            self._window_emitted = 0
        self._cycle_emitted = 0

    def _budget_available(self) -> bool:
        return (
            self._cycle_emitted < self.max_events_per_cycle
            and self._window_emitted < self.max_events_per_window
        )

    def _user_budget_available(self, user_id: str) -> bool:
        now = time.monotonic()
        emitted = self._user_emitted[user_id]
        while emitted and now - emitted[0] >= self.action_window_seconds:
            emitted.popleft()
        if len(emitted) >= self.max_events_per_user_window:
            return False
        return not emitted or now - emitted[-1] >= self.user_cooldown_seconds

    async def _publish(
        self,
        event_type: str,
        user_id: str,
        *,
        kind: str,
        key: str,
        payload: dict[str, Any],
    ) -> Event | None:
        async with user_lock(user_id):
            if not self._allowed_for_user(user_id):
                self.last_reason[user_id] = self.presence.reason(user_id) or 'agent_paused'
                return None
            settings = await asyncio.to_thread(context.preferences, user_id)
            now = context.utcnow()
            is_reminder = kind == 'reminder'
            reason = None
            if not settings['enabled']:
                reason = 'quiet_requested'
            elif not is_reminder and settings['awaiting_reply']:
                reason = 'awaiting_reply'
            elif not is_reminder and settings['last_user_at'] != payload.get('_context_turn'):
                reason = 'context_changed'
            elif settings['last_user_at'] and (now - settings['last_user_at']).total_seconds() < (30 if is_reminder else self.idle_after_seconds):
                reason = 'recent_conversation'
            elif settings['last_sent_at'] and (now - settings['last_sent_at']).total_seconds() < self.user_cooldown_seconds:
                reason = 'user_cooldown'
            if reason:
                self.last_reason[user_id] = reason
                return None
            if not is_reminder:
                # Read evidence under the same lock used by chat and memory deletion.
                history = await asyncio.to_thread(get_recent_chat_history, limit=8, user_id=user_id, strict=True)
                memories = await asyncio.to_thread(get_recent_memories, limit=200, user_id=user_id, strict=True)
                evaluation = await asyncio.to_thread(evaluate_progress, user_id)
                topic = context.choose_topic(history, memories, evaluation.get('goals') or [])
                if not topic:
                    self.last_reason[user_id] = 'no_relevant_topic'
                    return None
                kind, key = topic['kind'], topic['key']
                payload = {**payload, 'kind': kind, 'message': topic['message']}
            if settings['last_topic'] == key and settings['last_sent_at'] and (now - settings['last_sent_at']).total_seconds() < 86400:
                self.last_reason[user_id] = 'topic_already_used'
                return None
            if not self._budget_available() or not self._user_budget_available(user_id) or not self._should_emit(user_id, kind, key):
                self.last_reason[user_id] = 'rate_limit'
                return None
            payload = {k: v for k, v in payload.items() if not k.startswith('_')}
            payload['expires_at'] = (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat()
            event = Event.create(event_type, user_id=user_id, payload=payload)
            await asyncio.to_thread(context.record_outreach, user_id, key)
            self._pending[event.event_id] = (event, settings['last_user_at'], time.monotonic())
            await self.output_bus.publish(event)
            self._cycle_emitted += 1
            self._window_emitted += 1
            self._user_emitted[user_id].append(time.monotonic())
            self.last_reason[user_id] = 'offered'
            return event

    async def acknowledge(self, user_id, event_id):
        async with user_lock(user_id):
            pending = self._pending.get(event_id)
            if not pending:
                return False
            event, turn, offered_at = pending
            if event.user_id != user_id or time.monotonic() - offered_at > 30:
                return False
            settings = await asyncio.to_thread(context.preferences, user_id)
            if not settings['enabled'] or settings['last_user_at'] != turn:
                self._pending.pop(event_id, None)
                return False
            if event.type != EventType.PROACTIVE_REMINDER:
                history = await asyncio.to_thread(get_recent_chat_history, limit=8, user_id=user_id, strict=True)
                memories = await asyncio.to_thread(get_recent_memories, limit=200, user_id=user_id, strict=True)
                evaluation = await asyncio.to_thread(evaluate_progress, user_id)
                topic = context.choose_topic(history, memories, evaluation.get('goals') or [])
                if not topic or topic['message'] != event.payload['message']:
                    self._pending.pop(event_id, None)
                    return False
            await asyncio.to_thread(save_chat_message, 'assistant', event.payload['message'], user_id, strict=True)
            self._pending.pop(event_id, None)
            return True

    @staticmethod
    def _user_ids(reminder_results: Iterable[dict[str, Any]], state_manager: StateManager) -> tuple[str, ...]:
        user_ids = {"default", *state_manager.user_ids()}
        user_ids.update(str(item.get("user_id")) for item in reminder_results if item.get("user_id"))
        return tuple(sorted(user_ids))

    async def _publish_reminders(self, results: list[dict[str, Any]]) -> list[Event]:
        emitted: list[Event] = []
        for result in results:
            user_id = str(result.get("user_id") or "default")
            for reminder in result.get("notifications") or []:
                reminder_id = str(reminder.get("id") or reminder.get("title") or "unknown")
                event = await self._publish(
                    EventType.PROACTIVE_REMINDER,
                    user_id,
                    kind="reminder",
                    key=reminder_id,
                    payload={
                        "kind": "reminder_due",
                        "message": reminder.get("message") or f"Nhắc nhở: {reminder.get('title') or 'việc cần làm'}.",
                        "reminder": reminder,
                        "source": "proactive_scheduler",
                    },
                )
                if event:
                    emitted.append(event)
        return emitted

    async def _publish_context_suggestions(self, user_ids: Iterable[str]) -> list[Event]:
        if self.idle_after_seconds <= 0:
            return []
        emitted = []
        for user_id in user_ids:
            if not self._allowed_for_user(user_id):
                continue
            settings = await asyncio.to_thread(context.preferences, user_id)
            if not settings['enabled'] or settings['awaiting_reply']:
                self.last_reason[user_id] = 'quiet_requested' if not settings['enabled'] else 'awaiting_reply'
                continue
            last = settings['last_user_at']
            if not last or not self.idle_after_seconds <= (context.utcnow() - last).total_seconds() <= 8 * 3600:
                self.last_reason[user_id] = 'no_recent_idle_context'
                continue
            if not self._budget_available() or not self._user_budget_available(user_id):
                continue
            event = await self._publish(EventType.PROACTIVE_SUGGESTION, user_id,
                kind='context', key='', payload={
                    'kind': 'context', 'source': 'proactive_scheduler', '_context_turn': last,
                })
            if event:
                emitted.append(event)
        return emitted

    async def tick(self) -> list[Event]:
        """Run one scan; exposed for tests and a manual API check."""
        async with self._tick_lock:
            if self.state_manager.emergency_stopped:
                return []
            self._pending = {key: value for key, value in self._pending.items() if time.monotonic() - value[2] <= 30}
            self._reset_budget()
            reminder_results = await asyncio.to_thread(poll_due_reminder_notifications_for_all_users)
            reminder_results = list(reminder_results or [])
            emitted = await self._publish_reminders(reminder_results)
            user_ids = set(self._user_ids(reminder_results, self.state_manager)) | {entry[0] for entry in self.presence.sessions.values()}
            emitted.extend(await self._publish_context_suggestions(user_ids))
            if emitted:
                logger.info("[proactive] emitted=%s", len(emitted))
            return emitted
