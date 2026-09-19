import asyncio
import unittest
from datetime import datetime, timezone

from agent import AgentAction, AgentLoop, DecisionEngine, Event, EventBus, EventType, StateManager


class AgentLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_loop_processes_event_and_calls_executor(self):
        bus = EventBus()
        manager = StateManager()
        engine = DecisionEngine()
        decisions = []
        received = asyncio.Event()

        async def executor(decision, event, state):
            decisions.append((decision, event, state))
            received.set()

        loop = AgentLoop(bus, manager, engine, on_decision=executor)
        loop.start()
        await bus.publish(Event.create(EventType.USER_MESSAGE, user_id="user-1", payload={"text": "Chào"}))
        await asyncio.wait_for(received.wait(), timeout=1)

        await loop.stop()
        decision, event, state = decisions[0]
        self.assertEqual(decision.action, AgentAction.RESPOND)
        self.assertEqual(event.user_id, "user-1")
        self.assertEqual(state.last_action, AgentAction.RESPOND)
        self.assertEqual(manager.get_state("user-1").interaction_count, 1)

    async def test_ignored_event_is_not_sent_to_executor(self):
        bus = EventBus()
        manager = StateManager()
        manager.update("user-1", autonomous_enabled=False)
        decisions = []
        loop = AgentLoop(bus, manager, DecisionEngine(), on_decision=lambda *args: decisions.append(args))

        decision = await loop.process_event(
            Event.create(EventType.IDLE_TIMEOUT, user_id="user-1")
        )

        self.assertFalse(decision.should_respond)
        self.assertEqual(decisions, [])

    async def test_stop_cancels_waiting_loop(self):
        loop = AgentLoop(EventBus(), StateManager(), DecisionEngine())
        task = loop.start()
        await asyncio.sleep(0)

        await loop.stop()

        self.assertFalse(loop.running)
        self.assertTrue(task.cancelled())


if __name__ == "__main__":
    unittest.main()
