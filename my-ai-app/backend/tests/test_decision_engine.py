import unittest
from datetime import datetime, timedelta, timezone

from agent import AgentAction, AgentActivity, DecisionEngine, Event, EventType, StateManager


class DecisionEngineTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
        self.engine = DecisionEngine(idle_after_seconds=60, idle_cooldown_seconds=120, action_cooldown_seconds=10)
        self.manager = StateManager()

    def event(self, event_type, payload=None):
        return Event.create(event_type, user_id="user-1", payload=payload)

    def test_user_message_always_gets_response_even_when_autonomous_mode_is_off(self):
        state = self.manager.update("user-1", autonomous_enabled=False)
        decision = self.engine.decide(self.event(EventType.USER_MESSAGE, {"response_mode": "deep"}), state, now=self.now)

        self.assertTrue(decision.should_respond)
        self.assertEqual(decision.action, AgentAction.RESPOND)
        self.assertEqual(decision.response_mode, "deep")

    def test_emergency_stop_blocks_even_manual_event_processing(self):
        state = self.manager.update("user-1")
        state.emergency_stopped = True
        decision = self.engine.decide(self.event(EventType.USER_MESSAGE), state, now=self.now)

        self.assertFalse(decision.should_respond)
        self.assertEqual(decision.reason, "emergency_stop_enabled")

    def test_due_reminder_is_notified_unless_action_is_in_cooldown(self):
        state = self.manager.get_state("user-1")
        state.last_action_at = self.now - timedelta(seconds=5)
        blocked = self.engine.decide(self.event(EventType.REMINDER_DUE), state, now=self.now)
        allowed = self.engine.decide(self.event(EventType.REMINDER_DUE), state, now=self.now + timedelta(seconds=11))

        self.assertFalse(blocked.should_respond)
        self.assertTrue(allowed.should_respond)
        self.assertEqual(allowed.action, AgentAction.NOTIFY)

    def test_idle_requires_threshold_and_cooldown(self):
        state = self.manager.get_state("user-1")
        state.last_interaction = self.now
        too_soon = self.engine.decide(self.event(EventType.IDLE_TIMEOUT), state, now=self.now + timedelta(seconds=30))
        ready = self.engine.decide(self.event(EventType.IDLE_TIMEOUT), state, now=self.now + timedelta(seconds=61))

        self.assertFalse(too_soon.should_respond)
        self.assertTrue(ready.should_respond)
        self.assertEqual(ready.action, AgentAction.IDLE_PROMPT)

    def test_speaking_agent_does_not_start_idle_prompt(self):
        state = self.manager.get_state("user-1")
        state.last_interaction = self.now - timedelta(seconds=120)
        state = self.manager.update("user-1", activity=AgentActivity.SPEAKING)
        decision = self.engine.decide(self.event(EventType.IDLE_TIMEOUT), state, now=self.now + timedelta(seconds=120))

        self.assertFalse(decision.should_respond)
        self.assertEqual(decision.reason, "agent_is_already_speaking")

    def test_unknown_event_is_ignored_and_research_uses_deep_mode(self):
        unknown = self.engine.decide(self.event(EventType.TIMER_TICK), self.manager.get_state("user-1"), now=self.now)
        research = self.engine.decide(self.event(EventType.RESEARCH_COMPLETED), self.manager.get_state("user-1"), now=self.now)

        self.assertFalse(unknown.should_respond)
        self.assertTrue(research.should_respond)
        self.assertEqual(research.response_mode, "deep")


if __name__ == "__main__":
    unittest.main()
