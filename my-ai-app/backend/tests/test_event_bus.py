import asyncio
import unittest

from agent.event_bus import EventBus, EventBusClosed
from agent.events import Event, EventType


class EventBusTests(unittest.IsolatedAsyncioTestCase):
    async def test_publish_and_get_from_agent_queue(self):
        bus = EventBus()
        event = Event.create(EventType.USER_MESSAGE, user_id="user-1", payload={"text": "Xin chào"})

        await bus.publish(event)

        received = await bus.get()
        self.assertEqual(received, event)
        self.assertEqual(received.payload["text"], "Xin chào")

    async def test_subscribers_receive_broadcast_without_consuming_agent_event(self):
        bus = EventBus()
        subscription = bus.subscribe()
        event = Event.create(EventType.REMINDER_DUE)

        await bus.publish(event)

        self.assertEqual(await bus.get(), event)
        self.assertEqual(await subscription.get(), event)
        subscription.close()

    async def test_close_wakes_waiting_consumers(self):
        bus = EventBus()
        waiting = asyncio.create_task(bus.get())
        await asyncio.sleep(0)

        bus.close()

        with self.assertRaises(EventBusClosed):
            await waiting
        with self.assertRaises(EventBusClosed):
            await bus.publish(Event.create(EventType.SYSTEM))

    def test_event_rejects_invalid_envelope(self):
        with self.assertRaises(ValueError):
            Event.create("")
        with self.assertRaises(ValueError):
            Event.create(EventType.SYSTEM, user_id=" ")
