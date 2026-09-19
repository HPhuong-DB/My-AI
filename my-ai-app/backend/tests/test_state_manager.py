import unittest

from agent import AgentActivity, Event, EventType, StateManager


class StateManagerTests(unittest.TestCase):
    def test_states_are_isolated_by_user(self):
        manager = StateManager()
        manager.record_interaction("user-1")

        self.assertEqual(manager.get_state("user-1").interaction_count, 1)
        self.assertEqual(manager.get_state("user-2").interaction_count, 0)

    def test_update_clamps_energy_and_returns_snapshot(self):
        manager = StateManager()
        state = manager.update("user-1", energy=2, mood="happy", metadata={"topic": "music"})
        state.metadata["topic"] = "changed-outside"

        self.assertEqual(state.energy, 1.0)
        self.assertEqual(manager.get_state("user-1").energy, 1.0)
        self.assertEqual(manager.get_state("user-1").metadata["topic"], "music")

    def test_record_interaction_updates_activity_and_timestamp(self):
        manager = StateManager()
        state = manager.record_interaction("user-1", mood="sad")

        self.assertEqual(state.activity, AgentActivity.LISTENING)
        self.assertEqual(state.mood, "sad")
        self.assertIsNotNone(state.last_interaction)
        self.assertEqual(state.interaction_count, 1)

    def test_apply_event_changes_runtime_state(self):
        manager = StateManager()
        reminder_state = manager.apply_event(Event.create(EventType.REMINDER_DUE, user_id="user-1"))
        speaking_state = manager.set_speaking(True, "user-1")
        idle_state = manager.apply_event(Event.create(EventType.IDLE_TIMEOUT, user_id="user-1"))

        self.assertEqual(reminder_state.activity, AgentActivity.WORKING)
        self.assertTrue(speaking_state.is_speaking)
        self.assertEqual(idle_state.activity, AgentActivity.IDLE)
        self.assertFalse(idle_state.is_speaking)

    def test_autonomous_mode_can_be_disabled(self):
        manager = StateManager()
        state = manager.update("user-1", autonomous_enabled=False)

        self.assertFalse(state.autonomous_enabled)

    def test_emergency_stop_applies_to_existing_and_new_users(self):
        manager = StateManager()
        manager.get_state("user-1")
        manager.set_emergency_stop(True)

        self.assertTrue(manager.get_state("user-1").emergency_stopped)
        self.assertTrue(manager.get_state("user-2").emergency_stopped)
        manager.set_emergency_stop(False)
        self.assertFalse(manager.get_state("user-1").emergency_stopped)

    def test_invalid_values_are_rejected(self):
        manager = StateManager()
        with self.assertRaises(ValueError):
            manager.get_state(" ")
        with self.assertRaises(ValueError):
            manager.record_action("", "user-1")


if __name__ == "__main__":
    unittest.main()
