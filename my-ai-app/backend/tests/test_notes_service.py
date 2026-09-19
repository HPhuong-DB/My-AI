import unittest
from unittest.mock import patch

from services import notes_service
from services import tool_service


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor
        self.committed = False
        self.closed = False

    def cursor(self, **kwargs):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def is_connected(self):
        return not self.closed

    def close(self):
        self.closed = True


class FakeCursor:
    def __init__(self, fetchone_results=None, fetchall_result=None, rowcount=1, lastrowid=1):
        self.fetchone_results = list(fetchone_results or [])
        self.fetchall_result = fetchall_result or []
        self.rowcount = rowcount
        self.lastrowid = lastrowid
        self.executed = []

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        return self.fetchone_results.pop(0) if self.fetchone_results else None

    def fetchall(self):
        return self.fetchall_result

    def close(self):
        pass


class NotesServiceTests(unittest.TestCase):
    @patch.object(tool_service, "create_note")
    def test_notes_tool_dispatch_keeps_server_user_scope(self, create_note_mock):
        create_note_mock.return_value = {"id": 1, "user_id": "user-1", "title": "A", "content": "B"}

        result = tool_service.execute_registered_tool(
            "create_note",
            {"title": "A", "content": "B", "user_id": "attacker"},
            user_id="user-1",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(create_note_mock.call_args.kwargs["user_id"], "user-1")

    @patch.object(notes_service, "_ensure_notes_table")
    @patch.object(notes_service, "get_db_connection")
    def test_create_note_is_scoped_and_normalizes_tags(self, get_connection, ensure_table):
        row = {
            "id": 9,
            "user_id": "user-1",
            "title": "Ý tưởng",
            "content": "Viết tool notes",
            "tags": '["project", "ai"]',
            "is_archived": 0,
        }
        cursor = FakeCursor(fetchone_results=[row], lastrowid=9)
        connection = FakeConnection(cursor)
        get_connection.return_value = connection

        result = notes_service.create_note(
            user_id="user-1",
            title=" Ý tưởng ",
            content=" Viết tool notes ",
            tags=["Project", "ai", "project"],
        )

        self.assertEqual(result["tags"], ["project", "ai"])
        self.assertEqual(cursor.executed[1][1], (9, "user-1"))
        self.assertTrue(connection.committed)
        ensure_table.assert_called_once_with(connection)

    @patch.object(notes_service, "_ensure_notes_table")
    @patch.object(notes_service, "get_db_connection")
    def test_list_notes_filters_by_user_and_search(self, get_connection, ensure_table):
        rows = [{"id": 2, "user_id": "user-1", "title": "Python", "content": "async", "tags": "[]", "is_archived": 0}]
        cursor = FakeCursor(fetchall_result=rows)
        connection = FakeConnection(cursor)
        get_connection.return_value = connection

        result = notes_service.list_notes(user_id="user-1", search="python", limit=10)

        self.assertEqual(result[0]["title"], "Python")
        self.assertEqual(cursor.executed[-1][1], ("user-1", "%python%", "%python%", "%python%", 10))
        ensure_table.assert_called_once_with(connection)

    @patch.object(notes_service, "_ensure_notes_table")
    @patch.object(notes_service, "get_db_connection")
    def test_update_and_archive_note_require_same_user(self, get_connection, ensure_table):
        row = {
            "id": 4,
            "user_id": "user-1",
            "title": "Mới",
            "content": "Nội dung mới",
            "tags": "[\"updated\"]",
            "is_archived": 0,
        }
        cursor = FakeCursor(fetchone_results=[row], rowcount=1)
        connection = FakeConnection(cursor)
        get_connection.return_value = connection

        updated = notes_service.update_note(4, user_id="user-1", title="Mới", tags=["updated"])
        archived = notes_service.archive_note(4, user_id="user-1")

        self.assertEqual(updated["title"], "Mới")
        self.assertTrue(archived)
        self.assertEqual(cursor.executed[-1][1], (4, "user-1"))
        self.assertEqual(ensure_table.call_count, 2)

    def test_note_validation_rejects_empty_content(self):
        with self.assertRaises(ValueError):
            notes_service.create_note(title="Tiêu đề", content="")


if __name__ == "__main__":
    unittest.main()
