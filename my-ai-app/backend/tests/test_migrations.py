import unittest
from unittest.mock import patch

from core.database import DatabaseUnavailable
from core import migrations


class FakeMigrationCursor:
    def __init__(self, applied=None, *, schema_objects_exist=True):
        self.applied = dict(applied or {})
        self.executed = []
        self.current_one = None
        self.current_all = []
        self.schema_objects_exist = schema_objects_exist

    def execute(self, query, params=None):
        compact = " ".join(str(query).split())
        self.executed.append((compact, params))
        if compact.startswith("SELECT version, name, checksum FROM schema_migrations"):
            self.current_all = [
                {"version": version, "name": item["name"], "checksum": item["checksum"]}
                for version, item in sorted(self.applied.items())
            ]
        elif compact.startswith("INSERT INTO schema_migrations"):
            version, name, checksum = params
            self.applied[int(version)] = {"name": name, "checksum": checksum}
        elif compact.startswith("SHOW COLUMNS") or compact.startswith("SHOW INDEX"):
            self.current_one = {"exists": True} if self.schema_objects_exist else None

    def fetchone(self):
        result = self.current_one
        self.current_one = None
        return result

    def fetchall(self):
        result = self.current_all
        self.current_all = []
        return result

    def close(self):
        pass


class FakeMigrationConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.cursor_options = None
        self.commits = 0
        self.rollbacks = 0

    def cursor(self, **kwargs):
        self.cursor_options = kwargs
        return self._cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class MigrationTests(unittest.TestCase):
    def setUp(self):
        migrations._reset_migration_state_for_tests()

    def tearDown(self):
        migrations._reset_migration_state_for_tests()

    def test_pending_migrations_are_versioned_and_applied_in_order(self):
        cursor = FakeMigrationCursor()
        connection = FakeMigrationConnection(cursor)

        report = migrations.ensure_schema(connection, force=True)

        self.assertTrue(report["ok"])
        self.assertEqual(report["version"], migrations.LATEST_SCHEMA_VERSION)
        self.assertEqual([item["version"] for item in report["applied"]], [1, 2, 3, 4])
        self.assertEqual(connection.cursor_options, {"dictionary": True, "buffered": True})
        inserts = [params for sql, params in cursor.executed if sql.startswith("INSERT INTO schema_migrations")]
        self.assertEqual([params[0] for params in inserts], [1, 2, 3, 4])
        self.assertGreaterEqual(connection.commits, 5)

    def test_applied_migrations_are_not_run_again(self):
        cursor = FakeMigrationCursor()
        connection = FakeMigrationConnection(cursor)
        migrations.ensure_schema(connection, force=True)
        first_create_count = sum(sql.startswith("CREATE TABLE IF NOT EXISTS chat_history") for sql, _ in cursor.executed)

        report = migrations.ensure_schema(connection, force=True)

        second_create_count = sum(sql.startswith("CREATE TABLE IF NOT EXISTS chat_history") for sql, _ in cursor.executed)
        self.assertEqual(report["applied"], [])
        self.assertEqual(first_create_count, second_create_count)

    def test_checksum_drift_stops_startup_migration(self):
        cursor = FakeMigrationCursor({1: {"name": "create_application_tables", "checksum": "wrong"}})
        connection = FakeMigrationConnection(cursor)

        with self.assertRaises(DatabaseUnavailable):
            migrations.ensure_schema(connection, force=True)

        self.assertEqual(connection.rollbacks, 1)

    def test_legacy_schema_gets_missing_columns_and_indexes(self):
        cursor = FakeMigrationCursor(schema_objects_exist=False)
        connection = FakeMigrationConnection(cursor)

        migrations.ensure_schema(connection, force=True)

        sql = [statement for statement, _ in cursor.executed]
        self.assertTrue(any("ALTER TABLE `core_memories` ADD COLUMN `confidence`" in item for item in sql))
        self.assertTrue(any("CREATE INDEX `idx_chat_history_user_id`" in item for item in sql))
        self.assertTrue(any("CREATE UNIQUE INDEX `uq_episode_session_source`" in item for item in sql))

    @patch.object(migrations, "get_db_connection", return_value=None)
    def test_unavailable_database_returns_deferred_startup_report(self, _connection):
        report = migrations.run_migrations()

        self.assertFalse(report["ok"])
        self.assertEqual(report["code"], "database_unavailable")


if __name__ == "__main__":
    unittest.main()
