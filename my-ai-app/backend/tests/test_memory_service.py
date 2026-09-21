import unittest
from unittest.mock import patch

from services import memory_service


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.closed = False

    def cursor(self, **kwargs):
        return self._cursor

    def rollback(self):
        pass

    def commit(self):
        self.committed = True

    def is_connected(self):
        return not self.closed

    def close(self):
        self.closed = True


class FakeCursor:
    def __init__(self, fetchone_result=None, fetchall_result=None, rowcount=0, lastrowid=None):
        self.fetchone_result = fetchone_result
        self.fetchall_result = fetchall_result or []
        self.rowcount = rowcount
        self.lastrowid = lastrowid
        self.executed = []
        self.closed = False

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        return self.fetchone_result

    def fetchall(self):
        return self.fetchall_result

    def close(self):
        self.closed = True


class MemoryServiceTests(unittest.TestCase):
    def test_extracts_natural_long_term_facts(self):
        self.assertEqual(memory_service._extract_name("Mình tên là An"), "An")
        self.assertEqual(memory_service._extract_name("Gọi tôi là Bình"), "Bình")
        self.assertEqual(memory_service._extract_preference("Tôi rất thích trà"), "trà")
        self.assertEqual(memory_service._extract_goal("Mình học Python"), "Python")

    def test_infers_happy_mood_from_positive_interaction(self):
        mood, affection_delta = memory_service.infer_relationship_state("Mình rất thích cách bạn nói, cảm ơn bạn nhiều")
        self.assertEqual(mood, "happy")
        self.assertGreaterEqual(affection_delta, 1)

    def test_infers_sad_or_stressed_mood_from_negative_interaction(self):
        mood, affection_delta = memory_service.infer_relationship_state("Mình đang mệt và rất buồn vì hôm nay không ổn")
        self.assertIn(mood, ["sad", "stressed"])
        self.assertLessEqual(affection_delta, 0)

    def test_relationship_tone_and_mood_timeline_are_available(self):
        tone = memory_service.get_relationship_tone(8)
        self.assertIn("thân quen", tone.lower())

        timeline = memory_service.get_user_mood_timeline(user_id="user-1")
        self.assertIsInstance(timeline, list)

    @patch.object(memory_service, "_ensure_memory_tables")
    @patch.object(memory_service, "get_db_connection")
    def test_save_long_term_memory_for_user(self, get_connection, ensure_tables):
        cursor = FakeCursor()
        connection = FakeConnection(cursor)
        get_connection.return_value = connection

        memory_service.save_memory("preference", "Người dùng thích trà", user_id="user-1")

        self.assertTrue(connection.committed)
        inserted = [(sql, params) for sql, params in cursor.executed if sql.startswith("INSERT INTO core_memories")]
        self.assertEqual(
            inserted[0][1],
            ("user-1", "preference", "Người dùng thích trà", 0.9, 0.75, "conversation", None, None),
        )
        self.assertIn("is_active", inserted[0][0])
        self.assertIn("confidence", inserted[0][0])
        ensure_tables.assert_called_once_with(connection)

    @patch.object(memory_service, "_ensure_memory_tables")
    @patch.object(memory_service, "get_db_connection")
    def test_repeated_fact_is_consolidated_instead_of_duplicated(self, get_connection, ensure_tables):
        cursor = FakeCursor(fetchall_result=[{"id": 7, "fact": "Người dùng thích trà"}])
        connection = FakeConnection(cursor)
        get_connection.return_value = connection

        self.assertTrue(memory_service.save_memory("preference", "Người dùng thích trà", user_id="user-1"))

        updates = [(sql, params) for sql, params in cursor.executed if "occurrence_count = occurrence_count + 1" in sql]
        inserts = [(sql, params) for sql, params in cursor.executed if sql.startswith("INSERT INTO core_memories")]
        self.assertEqual(updates[0][1], (0.9, 0.75, "conversation", None, None, 7, "user-1"))
        self.assertEqual(inserts, [])
        self.assertTrue(connection.committed)
        ensure_tables.assert_called_once_with(connection)

    @patch.object(memory_service, "_ensure_memory_tables")
    @patch.object(memory_service, "get_db_connection")
    def test_get_memories_is_scoped_to_user(self, get_connection, ensure_tables):
        rows = [
            {
                "id": 7,
                "user_id": "user-1",
                "memory_type": "goal",
                "fact": "Người dùng đang học Python",
            }
        ]
        cursor = FakeCursor(fetchall_result=rows)
        connection = FakeConnection(cursor)
        get_connection.return_value = connection

        result = memory_service.get_recent_memories(limit=10, user_id="user-1")

        self.assertEqual(result, rows)
        self.assertEqual(cursor.executed[0][1], ("user-1", 10))
        self.assertIn("is_active = 1", cursor.executed[0][0])
        self.assertIn("expires_at > CURRENT_TIMESTAMP", cursor.executed[0][0])
        ensure_tables.assert_called_once_with(connection)

    @patch.object(memory_service, "_ensure_memory_tables")
    @patch.object(memory_service, "get_db_connection")
    def test_delete_memory_is_scoped_to_user(self, get_connection, ensure_tables):
        cursor = FakeCursor(fetchone_result={"id": 7, "memory_type": "preference", "fact": "Người dùng thích trà"}, rowcount=1)
        connection = FakeConnection(cursor)
        get_connection.return_value = connection

        result = memory_service.delete_memory(7, user_id="user-1")

        self.assertTrue(result)
        self.assertTrue(connection.committed)
        deleted = [(sql, params) for sql, params in cursor.executed if sql.startswith("DELETE FROM core_memories")]
        self.assertEqual(deleted[0][1], (7, "user-1"))
        self.assertTrue(any("cutoff_chat_id" in sql for sql, _ in cursor.executed))
        ensure_tables.assert_called_once_with(connection)

    @patch.object(memory_service, "_ensure_memory_tables")
    @patch.object(memory_service, "get_db_connection")
    def test_save_user_profile_tracks_relationship_state(self, get_connection, ensure_tables):
        cursor = FakeCursor(fetchone_result=None)
        connection = FakeConnection(cursor)
        get_connection.return_value = connection

        memory_service.save_user_profile("An", user_id="user-1", mood="happy", affection_delta=2)

        self.assertTrue(connection.committed)
        self.assertEqual(
            cursor.executed[1][1],
            ("user-1", "An", 2, "happy", 1),
        )
        ensure_tables.assert_called_once_with(connection)


if __name__ == "__main__":
    unittest.main()
