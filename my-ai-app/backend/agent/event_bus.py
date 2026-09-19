"""Small async pub/sub bus for the autonomous agent."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import AsyncIterator, Callable
from uuid import uuid4

from agent.events import Event


class EventBusClosed(RuntimeError):
    """Raised when code tries to use a closed event bus."""


@dataclass
class EventSubscription(AsyncIterator[Event]):
    """A consumer queue registered with an :class:`EventBus`."""

    _queue: asyncio.Queue[Event | None]
    _unsubscribe: Callable[[str], None]
    subscription_id: str

    def __aiter__(self) -> "EventSubscription":
        return self

    async def __anext__(self) -> Event:
        event = await self._queue.get()
        if event is None:
            raise StopAsyncIteration
        return event

    async def get(self) -> Event:
        event = await self._queue.get()
        if event is None:
            raise EventBusClosed("Event subscription đã được đóng")
        return event

    def close(self) -> None:
        self._unsubscribe(self.subscription_id)


class EventBus:
    """Async event bus with one queue for the agent and broadcast subscribers.

    The central queue is consumed by the Agent Loop. Additional subscribers
    receive a copy, which is useful for WebSocket/API consumers and logging.
    """

    def __init__(self, *, max_queue_size: int = 1000) -> None:
        if max_queue_size <= 0:
            raise ValueError("max_queue_size phải lớn hơn 0")
        self._queue: asyncio.Queue[Event | None] = asyncio.Queue(maxsize=max_queue_size)
        self._subscriber_queues: dict[str, asyncio.Queue[Event | None]] = {}
        self._max_queue_size = max_queue_size
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    async def publish(self, event: Event) -> None:
        """Publish an event to the agent queue and all active subscribers."""
        if self._closed:
            raise EventBusClosed("Event bus đã được đóng")
        await self._queue.put(event)
        for subscriber_queue in tuple(self._subscriber_queues.values()):
            await subscriber_queue.put(event)

    async def get(self) -> Event:
        """Wait for the next event intended for the Agent Loop."""
        event = await self._queue.get()
        if event is None:
            raise EventBusClosed("Event bus đã được đóng")
        return event

    def subscribe(self) -> EventSubscription:
        """Create a broadcast subscription for another consumer."""
        if self._closed:
            raise EventBusClosed("Không thể subscribe vào event bus đã đóng")
        subscription_id = uuid4().hex
        queue: asyncio.Queue[Event | None] = asyncio.Queue(maxsize=self._max_queue_size)
        self._subscriber_queues[subscription_id] = queue
        return EventSubscription(queue, self._unsubscribe, subscription_id)

    def _unsubscribe(self, subscription_id: str) -> None:
        queue = self._subscriber_queues.pop(subscription_id, None)
        if queue is not None and not queue.full():
            queue.put_nowait(None)

    def close(self) -> None:
        """Stop consumers waiting on the bus and release subscriptions."""
        if self._closed:
            return
        self._closed = True
        if not self._queue.full():
            self._queue.put_nowait(None)
        for subscription_id in tuple(self._subscriber_queues):
            self._unsubscribe(subscription_id)
