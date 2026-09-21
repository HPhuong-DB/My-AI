import unittest
from unittest.mock import patch

from services import tool_service
from services.llm_service import resolve_response_mode


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.closed = False

    def cursor(self, **kwargs):
        return self._cursor

    def commit(self):
        self.committed = True

    def is_connected(self):
        return not self.closed

    def close(self):
        self.closed = True


class FakeCursor:
    def __init__(self, fetchone_result=None, fetchall_result=None, rowcount=0):
        self.fetchone_result = fetchone_result
        self.fetchall_result = fetchall_result or []
        self.rowcount = rowcount
        self.executed = []

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        return self.fetchone_result

    def fetchall(self):
        return self.fetchall_result

    def close(self):
        pass


class ToolServiceTests(unittest.TestCase):
    def test_tool_registry_contains_core_personal_tools(self):
        tool_names = {tool["name"] for tool in tool_service.TOOL_REGISTRY}
        self.assertIn("set_reminder", tool_names)
        self.assertIn("create_task", tool_names)
        self.assertIn("list_tasks", tool_names)
        self.assertIn("create_note", tool_names)
        self.assertIn("list_notes", tool_names)
        self.assertIn("archive_note", tool_names)

    @patch.object(tool_service, "_ensure_tool_tables")
    @patch.object(tool_service, "get_db_connection")
    def test_create_reminder_for_user(self, get_connection, ensure_tables):
        cursor = FakeCursor()
        connection = FakeConnection(cursor)
        get_connection.return_value = connection

        result = tool_service.create_reminder(
            user_id="user-1",
            title="Học Python",
            scheduled_for="2026-08-30 08:00:00",
            note="Ôn bài 30 phút",
        )

        self.assertTrue(result)
        self.assertTrue(connection.committed)
        self.assertEqual(cursor.executed[-1][1], ("user-1", "Học Python", "2026-08-30 08:00:00", "Ôn bài 30 phút", False))
        ensure_tables.assert_called_once_with(connection)

    @patch.object(tool_service, "_ensure_tool_tables")
    @patch.object(tool_service, "get_db_connection")
    def test_list_tasks_is_scoped_to_user(self, get_connection, ensure_tables):
        rows = [{"id": 1, "user_id": "user-1", "title": "Viết báo cáo", "done": False}]
        cursor = FakeCursor(fetchall_result=rows)
        connection = FakeConnection(cursor)
        get_connection.return_value = connection

        result = tool_service.list_tasks(user_id="user-1")

        self.assertEqual(result, rows)
        self.assertEqual(cursor.executed[0][1], ("user-1",))
        ensure_tables.assert_called_once_with(connection)

    @patch.object(tool_service, "_ensure_tool_tables")
    @patch.object(tool_service, "get_db_connection")
    def test_get_due_reminders_and_complete_reminder(self, get_connection, ensure_tables):
        rows = [{"id": 10, "user_id": "user-1", "title": "Học Python", "scheduled_for": "2026-08-29 08:00:00", "note": "", "done": False}]
        cursor = FakeCursor(fetchall_result=rows, rowcount=1)
        connection = FakeConnection(cursor)
        get_connection.return_value = connection

        due = tool_service.get_due_reminders(user_id="user-1")
        self.assertEqual(due, rows)

        result = tool_service.complete_reminder(reminder_id=10, user_id="user-1")
        self.assertTrue(result)
        self.assertEqual(cursor.executed[-1][1], (10, "user-1"))
        self.assertEqual(ensure_tables.call_count, 2)

    @patch.object(tool_service, "get_due_reminders")
    def test_trigger_due_reminder_notification_returns_summary(self, get_due_reminders_mock):
        get_due_reminders_mock.return_value = [
            {"id": 7, "user_id": "user-1", "title": "Nộp báo cáo", "scheduled_for": "2026-08-29 09:00:00", "note": "Gửi file cho manager", "done": False}
        ]

        summary = tool_service.trigger_due_reminder_notification(user_id="user-1")

        self.assertEqual(summary["user_id"], "user-1")
        self.assertEqual(summary["count"], 1)
        self.assertEqual(summary["reminders"][0]["title"], "Nộp báo cáo")
        self.assertIn("message", summary["reminders"][0])

    @patch.object(tool_service, "deliver_due_reminder_notifications")
    @patch.object(tool_service, "_ensure_tool_tables")
    @patch.object(tool_service, "get_db_connection")
    def test_poll_due_reminder_notifications_for_all_users(self, get_connection, ensure_tables, deliver_mock):
        cursor = FakeCursor(fetchall_result=[{"user_id": "user-1"}, {"user_id": "user-2"}])
        connection = FakeConnection(cursor)
        get_connection.return_value = connection
        deliver_mock.side_effect = [
            {"user_id": "user-1", "count": 1, "notifications": [{"title": "Nộp báo cáo"}]},
            {"user_id": "user-2", "count": 0, "notifications": []},
        ]

        result = tool_service.poll_due_reminder_notifications_for_all_users()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["user_id"], "user-1")
        self.assertEqual(result[0]["count"], 1)
        self.assertEqual(result[1]["user_id"], "user-2")
        ensure_tables.assert_called_once_with(connection)

    @patch.object(tool_service, "_ensure_tool_tables")
    @patch.object(tool_service, "get_db_connection")
    def test_complete_reminder_with_feedback_returns_confirmation(self, get_connection, ensure_tables):
        cursor = FakeCursor(rowcount=1)
        connection = FakeConnection(cursor)
        get_connection.return_value = connection

        result = tool_service.complete_reminder_with_feedback(
            reminder_id=12,
            user_id="user-1",
            completion_message="Mình đã xong rồi, cảm thấy nhẹ hơn nhiều.",
            emotion="relieved",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["emotion"], "relieved")
        self.assertIn("Mình đã xong rồi", result["message"])
        self.assertEqual(cursor.executed[-1][1], (12, "user-1"))

    @patch.object(tool_service, "get_relationship_tone")
    @patch.object(tool_service, "get_user_profile")
    @patch.object(tool_service, "_ensure_tool_tables")
    @patch.object(tool_service, "get_db_connection")
    def test_complete_reminder_with_feedback_uses_user_mood_and_tone(
        self, get_connection, ensure_tables, get_user_profile, get_relationship_tone
    ):
        cursor = FakeCursor(rowcount=1)
        connection = FakeConnection(cursor)
        get_connection.return_value = connection
        get_user_profile.return_value = {"user_id": "user-1", "username": "An", "affection_level": 8, "mood": "happy"}
        get_relationship_tone.return_value = "thân quen, nên nói ấm áp, cởi mở và gần gũi"

        result = tool_service.complete_reminder_with_feedback(
            reminder_id=15,
            user_id="user-1",
            completion_message="",
            emotion="happy",
        )

        self.assertTrue(result["ok"])
        self.assertIn("vui", result["message"].lower())
        self.assertIn("An", result["message"])
        self.assertIn("thân", result["message"].lower())

    def test_resolve_response_mode_prefers_fast_for_short_messages(self):
        self.assertEqual(resolve_response_mode("Mình mệt rồi"), "fast")

    def test_resolve_response_mode_uses_deep_for_complex_questions(self):
        self.assertEqual(
            resolve_response_mode("Mình muốn phân tích xem nên ưu tiên việc nào trước khi sắp xếp lịch làm việc và kế hoạch học tập của mình"),
            "deep",
        )


if __name__ == "__main__":
    unittest.main()
