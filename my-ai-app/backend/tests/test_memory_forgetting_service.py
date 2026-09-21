import unittest
from unittest.mock import patch

from services import memory_forgetting_service as service
from test_memory_service import FakeConnection, FakeCursor


class MemoryForgettingServiceTests(unittest.TestCase):
    def test_expired_sweep_is_user_scoped_and_auditable(self):
        cursor = FakeCursor(rowcount=1)
        connection = FakeConnection(cursor)
        with patch.object(service, "get_db_connection", return_value=connection), patch.object(
            service, "ensure_schema"
        ) as ensure_schema:
            result = service.forget_expired_memories("alice", strict=True)

        self.assertTrue(result["ok"])
        self.assertEqual(result["total"], 5)
        updates = [(sql, params) for sql, params in cursor.executed if sql.startswith("UPDATE")]
        self.assertEqual(len(updates), 5)
        self.assertTrue(all(params == ("alice",) for _, params in updates))
        self.assertTrue(all("forgotten_at IS NULL" in sql and "forget_reason = 'expired'" in sql for sql, _ in updates))
        self.assertIn("is_active = 0", updates[0][0])
        ensure_schema.assert_called_once_with(connection)


if __name__ == "__main__":
    unittest.main()
