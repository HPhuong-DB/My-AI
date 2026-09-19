import unittest

from agent import ContextManager, Event, EventType, StateManager


class ContextManagerTests(unittest.TestCase):
    def test_builds_context_from_perception_and_state(self):
        state_manager = StateManager()
        context_manager = ContextManager()
        event = Event.create(
            EventType.PERCEPTION_INPUT,
            user_id="user-1",
            payload={
                "source": "screen",
                "content_type": "screenshot",
                "content": "Đang đọc tài liệu Python",
            },
        )
        state = state_manager.apply_event(event)
        context = context_manager.observe(event, state)

        self.assertEqual(context.activity, "thinking")
        self.assertEqual(context.attention, "focused")
        self.assertEqual(context.last_input_source, "screen")
        self.assertEqual(context.current_topic, "Đang đọc tài liệu Python")
        self.assertEqual(context.recent_events[0]["content_type"], "screenshot")

    def test_context_history_is_bounded_and_preview_is_truncated(self):
        state_manager = StateManager()
        context_manager = ContextManager(max_recent_events=2, max_preview_chars=5)
        for text in ("first", "second", "third"):
            event = Event.create(EventType.USER_MESSAGE, user_id="user-1", payload={"text": text + "-long"})
            context_manager.observe(event, state_manager.apply_event(event))

        context = context_manager.get("user-1")
        self.assertIsNotNone(context)
        self.assertEqual(len(context.recent_events), 2)
        self.assertEqual(context.current_topic, "third")

    def test_clear_removes_context(self):
        state_manager = StateManager()
        context_manager = ContextManager()
        event = Event.create(EventType.USER_MESSAGE, user_id="user-1", payload={"text": "hello"})
        context_manager.observe(event, state_manager.apply_event(event))

        context_manager.clear("user-1")

        self.assertIsNone(context_manager.get("user-1"))


if __name__ == "__main__":
    unittest.main()
