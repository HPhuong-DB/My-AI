import json
import unittest
from unittest.mock import patch

from services import conversation_memory_service as service


class FakeCursor:
    def __init__(self, *, session_rows=None, cutoff=0, excluded=None, active_session=None, source_chat_id=11):
        self.session_rows = session_rows or []
        self.cutoff = cutoff
        self.excluded = excluded or []
        self.active_session = active_session
        self.source_chat_id = source_chat_id
        self.executed = []
        self.current_one = None
        self.current_all = []
        self.lastrowid = 5

    def execute(self, query, params=None):
        self.executed.append((query, params))
        if "SELECT cutoff_chat_id" in query:
            self.current_one = {"cutoff_chat_id": self.cutoff}
        elif "SELECT chat_id FROM memory_context_exclusions" in query:
            self.current_all = [{"chat_id": value} for value in self.excluded]
        elif "SELECT id FROM chat_history" in query:
            self.current_one = {"id": self.source_chat_id}
        elif "TIMESTAMPDIFF" in query:
            self.current_one = self.active_session
        elif "FROM conversation_sessions WHERE user_id" in query and "TIMESTAMPDIFF" not in query:
            self.current_all = self.session_rows

    def fetchone(self):
        return self.current_one

    def fetchall(self):
        return self.current_all

    def close(self):
        pass


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0
        self.rolled_back = False
        self.closed = False

    def cursor(self, **kwargs):
        return self._cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rolled_back = True

    def is_connected(self):
        return not self.closed

    def close(self):
        self.closed = True


class ConversationMemoryServiceTests(unittest.TestCase):
    def test_summary_is_bounded_and_keeps_roles_and_source_ids(self):
        summary = None
        for index in range(12):
            summary = service.update_session_summary(
                summary,
                f"Mình đang học Rust phần {index}",
                f"Huohuo trả lời phần {index}",
                index + 1,
            )

        self.assertEqual(len(summary["user_points"]), 8)
        self.assertEqual(len(summary["assistant_points"]), 6)
        self.assertEqual(summary["user_points"][-1]["chat_id"], 12)
        self.assertIn("rust", summary["topics"])

    def test_episode_extraction_accepts_user_events_and_rejects_unsafe_shapes(self):
        achievement = service.extract_episode("Hôm nay mình đã thi đậu bằng lái")
        decision = service.extract_episode("Mình quyết định sẽ bắt đầu học Rust")

        self.assertEqual(achievement["event_type"], "achievement")
        self.assertEqual(decision["event_type"], "decision")
        self.assertIsNone(service.extract_episode("Bạn mình vừa thi đậu"))
        self.assertIsNone(service.extract_episode("Mình nghe bạn mình vừa thi đậu"))
        self.assertIsNone(service.extract_episode("Mình có thi đậu không?"))
        self.assertIsNone(service.extract_episode('Ví dụ: “Mình vừa thi đậu”'))

    def test_completed_turn_creates_session_and_user_grounded_episode(self):
        cursor = FakeCursor(source_chat_id=11)
        connection = FakeConnection(cursor)
        with patch.object(service, "get_db_connection", return_value=connection):
            result = service.record_completed_turn(
                "alice",
                "Hôm nay mình đã thi đậu",
                "Chúc mừng bạn!",
                12,
                strict=True,
            )

        self.assertEqual(result["session_id"], 5)
        self.assertEqual(result["source_chat_id"], 11)
        episode_inserts = [item for item in cursor.executed if "INSERT IGNORE INTO episodic_memories" in item[0]]
        self.assertEqual(episode_inserts[0][1][0:3], ("alice", 5, 11))
        self.assertTrue(connection.commits)

    def test_idle_gap_closes_previous_session_before_creating_another(self):
        cursor = FakeCursor(
            source_chat_id=21,
            active_session={
                "id": 3,
                "summary": json.dumps(service._decode_summary(None)),
                "turn_count": 1,
                "idle_seconds": 1901,
            },
        )
        connection = FakeConnection(cursor)
        with patch.object(service, "get_db_connection", return_value=connection), patch.dict(
            service.os.environ, {"SESSION_IDLE_SECONDS": "1800"}
        ):
            result = service.record_completed_turn(
                "alice",
                "Mình vừa hoàn thành bài tập",
                "Tốt lắm!",
                22,
                strict=True,
            )

        self.assertEqual(result["session_id"], 5)
        self.assertTrue(any("SET ended_at = last_activity_at" in sql for sql, _ in cursor.executed))
        self.assertTrue(any("INSERT INTO conversation_sessions" in sql for sql, _ in cursor.executed))

    def test_session_recall_filters_points_before_memory_cutoff(self):
        summary = {
            "topics": ["tra", "rust"],
            "user_points": [
                {"chat_id": 4, "text": "Mình thích trà"},
                {"chat_id": 12, "text": "Mình đang học Rust"},
            ],
            "assistant_points": [
                {"chat_id": 4, "text": "Trà rất ngon"},
                {"chat_id": 12, "text": "Hãy học ownership"},
            ],
        }
        cursor = FakeCursor(
            cutoff=10,
            session_rows=[{
                "id": 3,
                "user_id": "alice",
                "summary": json.dumps(summary, ensure_ascii=False),
                "turn_count": 2,
                "started_at": None,
                "last_activity_at": None,
                "ended_at": None,
            }],
        )
        connection = FakeConnection(cursor)
        with patch.object(service, "get_db_connection", return_value=connection):
            result = service.list_session_summaries("alice", 10, strict=True)

        self.assertEqual([item["chat_id"] for item in result[0]["user_points"]], [12])
        self.assertEqual(result[0]["topics"], ["hoc", "rust"])
        self.assertNotIn("trà", json.dumps(result, ensure_ascii=False))

    def test_session_recall_excludes_only_targeted_source_turn(self):
        summary = {
            "topics": ["tra", "rust"],
            "user_points": [
                {"chat_id": 4, "text": "Mình thích trà"},
                {"chat_id": 12, "text": "Mình đang học Rust"},
            ],
            "assistant_points": [
                {"chat_id": 4, "text": "Trà rất ngon"},
                {"chat_id": 12, "text": "Hãy học ownership"},
            ],
        }
        cursor = FakeCursor(
            excluded=[4],
            session_rows=[{
                "id": 3,
                "user_id": "alice",
                "summary": json.dumps(summary, ensure_ascii=False),
                "turn_count": 2,
                "started_at": None,
                "last_activity_at": None,
                "ended_at": None,
            }],
        )
        connection = FakeConnection(cursor)
        with patch.object(service, "get_db_connection", return_value=connection):
            result = service.list_session_summaries("alice", 10, strict=True)

        self.assertEqual([item["chat_id"] for item in result[0]["user_points"]], [12])
        self.assertEqual([item["chat_id"] for item in result[0]["assistant_points"]], [12])


if __name__ == "__main__":
    unittest.main()
