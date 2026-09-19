import unittest
from datetime import datetime, timezone

from api.websocket import _event_message
from agent import Event


class WebSocketMessageTests(unittest.TestCase):
    def test_event_is_serialized_for_frontend(self):
        event = Event(
            type="assistant_response",
            user_id="user-1",
            payload={"reply_vi": "Xin chào"},
            created_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
            event_id="event-1",
        )

        message = _event_message(event)

        self.assertEqual(message["type"], "assistant_response")
        self.assertEqual(message["user_id"], "user-1")
        self.assertEqual(message["created_at"], "2026-09-05T00:00:00+00:00")
        self.assertEqual(message["payload"]["reply_vi"], "Xin chào")


if __name__ == "__main__":
    unittest.main()
