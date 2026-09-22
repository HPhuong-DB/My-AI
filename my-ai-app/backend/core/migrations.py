"""Versioned, idempotent MySQL schema migrations for the whole backend."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from threading import Lock
from typing import Any, Callable

from core.database import DatabaseUnavailable, get_db_connection


MigrationAction = Callable[[Any], None]


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    action: MigrationAction
    signature: str

    @property
    def checksum(self) -> str:
        payload = f"{self.version}:{self.name}:{self.signature}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


CREATE_TABLES = (
    """CREATE TABLE IF NOT EXISTS chat_history (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id VARCHAR(100) NOT NULL DEFAULT 'default',
        role VARCHAR(50) NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS core_memories (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id VARCHAR(100) NOT NULL DEFAULT 'default',
        memory_type VARCHAR(50) NOT NULL,
        fact TEXT NOT NULL,
        occurrence_count INT DEFAULT 1,
        is_active TINYINT(1) DEFAULT 0,
        confidence DECIMAL(3,2) NOT NULL DEFAULT 0.90,
        importance DECIMAL(3,2) NOT NULL DEFAULT 0.70,
        source_type VARCHAR(50) NOT NULL DEFAULT 'conversation',
        source_ref VARCHAR(255) NULL,
        expires_at DATETIME NULL,
        last_confirmed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        forgotten_at DATETIME NULL,
        forget_reason VARCHAR(50) NULL,
        superseded_by_id INT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS user_profiles (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id VARCHAR(100) NOT NULL DEFAULT 'default',
        username VARCHAR(50) NOT NULL,
        affection_level INT DEFAULT 0,
        mood VARCHAR(50) DEFAULT 'neutral',
        interaction_count INT DEFAULT 0,
        last_interaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS user_mood_timeline (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id VARCHAR(100) NOT NULL DEFAULT 'default',
        username VARCHAR(50) NOT NULL,
        mood VARCHAR(50) DEFAULT 'neutral',
        affection_level INT DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS memory_context_state (
        user_id VARCHAR(100) PRIMARY KEY,
        cutoff_chat_id INT NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS memory_context_exclusions (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        user_id VARCHAR(100) NOT NULL,
        chat_id BIGINT NOT NULL,
        source_ref VARCHAR(255) NOT NULL,
        reason VARCHAR(50) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_memory_context_exclusion (user_id, chat_id, source_ref),
        INDEX idx_memory_context_exclusion_chat (user_id, chat_id)
    )""",
    """CREATE TABLE IF NOT EXISTS personal_knowledge (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id VARCHAR(100) NOT NULL DEFAULT 'default',
        query_text VARCHAR(500) NOT NULL,
        title VARCHAR(255) NOT NULL,
        summary TEXT NOT NULL,
        key_points TEXT,
        sources TEXT,
        confidence DECIMAL(3,2) NOT NULL DEFAULT 0.75,
        importance DECIMAL(3,2) NOT NULL DEFAULT 0.60,
        source_type VARCHAR(50) NOT NULL DEFAULT 'research',
        source_ref VARCHAR(255) NULL,
        expires_at DATETIME NULL,
        forgotten_at DATETIME NULL,
        forget_reason VARCHAR(50) NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_knowledge_user (user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS agent_experiences (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id VARCHAR(100) NOT NULL DEFAULT 'default',
        title VARCHAR(255) NOT NULL,
        lesson TEXT NOT NULL,
        context TEXT,
        source_type VARCHAR(50) DEFAULT 'goal',
        source_id INT NULL,
        source_ref VARCHAR(255) NULL,
        confidence DECIMAL(3,2) NOT NULL DEFAULT 0.80,
        importance DECIMAL(3,2) NOT NULL DEFAULT 0.75,
        expires_at DATETIME NULL,
        forgotten_at DATETIME NULL,
        forget_reason VARCHAR(50) NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_experiences_user (user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS conversation_sessions (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        user_id VARCHAR(100) NOT NULL DEFAULT 'default',
        start_chat_id BIGINT NOT NULL,
        summary TEXT NOT NULL,
        turn_count INT NOT NULL DEFAULT 0,
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_activity_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        ended_at TIMESTAMP NULL DEFAULT NULL,
        confidence DECIMAL(3,2) NOT NULL DEFAULT 1.00,
        importance DECIMAL(3,2) NOT NULL DEFAULT 0.50,
        source_type VARCHAR(50) NOT NULL DEFAULT 'chat_session',
        source_ref VARCHAR(255) NULL,
        expires_at DATETIME NULL,
        forgotten_at DATETIME NULL,
        forget_reason VARCHAR(50) NULL,
        INDEX idx_conversation_sessions_user_activity (user_id, last_activity_at)
    )""",
    """CREATE TABLE IF NOT EXISTS episodic_memories (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        user_id VARCHAR(100) NOT NULL DEFAULT 'default',
        session_id BIGINT NOT NULL,
        source_chat_id BIGINT NOT NULL,
        event_type VARCHAR(50) NOT NULL,
        title VARCHAR(255) NOT NULL,
        description TEXT NOT NULL,
        salience DECIMAL(3,2) NOT NULL DEFAULT 0.50,
        source_role VARCHAR(20) NOT NULL DEFAULT 'user',
        source_fingerprint CHAR(64) NOT NULL,
        confidence DECIMAL(3,2) NOT NULL DEFAULT 0.90,
        importance DECIMAL(3,2) NOT NULL DEFAULT 0.70,
        source_type VARCHAR(50) NOT NULL DEFAULT 'chat_episode',
        source_ref VARCHAR(255) NULL,
        expires_at DATETIME NULL,
        forgotten_at DATETIME NULL,
        forget_reason VARCHAR(50) NULL,
        occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_episode_session_source (session_id, source_fingerprint),
        INDEX idx_episodes_user_time (user_id, occurred_at),
        INDEX idx_episodes_source_chat (user_id, source_chat_id)
    )""",
    """CREATE TABLE IF NOT EXISTS personal_tasks (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id VARCHAR(100) NOT NULL DEFAULT 'default',
        title VARCHAR(255) NOT NULL,
        description TEXT,
        done TINYINT(1) DEFAULT 0,
        status VARCHAR(30) DEFAULT 'todo',
        progress INT DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS personal_reminders (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id VARCHAR(100) NOT NULL DEFAULT 'default',
        title VARCHAR(255) NOT NULL,
        scheduled_for DATETIME NOT NULL,
        note TEXT,
        done TINYINT(1) DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS proactive_preferences (
        user_id VARCHAR(100) PRIMARY KEY,
        enabled BOOLEAN NOT NULL DEFAULT TRUE,
        resume_on_message BOOLEAN NOT NULL DEFAULT FALSE,
        quiet_until DATETIME(6) NULL,
        awaiting_reply BOOLEAN NOT NULL DEFAULT FALSE,
        last_topic VARCHAR(160) NULL,
        last_sent_at DATETIME(6) NULL,
        last_user_at DATETIME(6) NULL
    )""",
    """CREATE TABLE IF NOT EXISTS personal_goals (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id VARCHAR(100) NOT NULL DEFAULT 'default',
        title VARCHAR(255) NOT NULL,
        description TEXT,
        status VARCHAR(30) NOT NULL DEFAULT 'active',
        priority INT NOT NULL DEFAULT 3,
        progress INT NOT NULL DEFAULT 0,
        target_date DATE NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_goals_user_status (user_id, status)
    )""",
    """CREATE TABLE IF NOT EXISTS goal_steps (
        id INT AUTO_INCREMENT PRIMARY KEY,
        goal_id INT NOT NULL,
        user_id VARCHAR(100) NOT NULL DEFAULT 'default',
        title VARCHAR(255) NOT NULL,
        description TEXT,
        position INT NOT NULL DEFAULT 1,
        status VARCHAR(30) NOT NULL DEFAULT 'todo',
        progress INT NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_goal_steps_owner (goal_id, user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS personal_notes (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id VARCHAR(100) NOT NULL DEFAULT 'default',
        title VARCHAR(255) NOT NULL,
        content TEXT NOT NULL,
        tags TEXT,
        is_archived TINYINT(1) DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_personal_notes_user (user_id),
        INDEX idx_personal_notes_archived (user_id, is_archived)
    )""",
)


LEGACY_COLUMNS = {
    "chat_history": {"user_id": "VARCHAR(100) NOT NULL DEFAULT 'default'"},
    "core_memories": {
        "user_id": "VARCHAR(100) NOT NULL DEFAULT 'default'",
        "occurrence_count": "INT DEFAULT 1",
        "is_active": "TINYINT(1) DEFAULT 0",
        "confidence": "DECIMAL(3,2) NOT NULL DEFAULT 0.90",
        "importance": "DECIMAL(3,2) NOT NULL DEFAULT 0.70",
        "source_type": "VARCHAR(50) NOT NULL DEFAULT 'conversation'",
        "source_ref": "VARCHAR(255) NULL",
        "expires_at": "DATETIME NULL",
        "last_confirmed_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "forgotten_at": "DATETIME NULL",
        "forget_reason": "VARCHAR(50) NULL",
        "superseded_by_id": "INT NULL",
    },
    "user_profiles": {
        "user_id": "VARCHAR(100) NOT NULL DEFAULT 'default'",
        "mood": "VARCHAR(50) DEFAULT 'neutral'",
        "interaction_count": "INT DEFAULT 0",
    },
    "personal_knowledge": {
        "confidence": "DECIMAL(3,2) NOT NULL DEFAULT 0.75",
        "importance": "DECIMAL(3,2) NOT NULL DEFAULT 0.60",
        "source_type": "VARCHAR(50) NOT NULL DEFAULT 'research'",
        "source_ref": "VARCHAR(255) NULL",
        "expires_at": "DATETIME NULL",
        "forgotten_at": "DATETIME NULL",
        "forget_reason": "VARCHAR(50) NULL",
    },
    "agent_experiences": {
        "source_ref": "VARCHAR(255) NULL",
        "confidence": "DECIMAL(3,2) NOT NULL DEFAULT 0.80",
        "importance": "DECIMAL(3,2) NOT NULL DEFAULT 0.75",
        "expires_at": "DATETIME NULL",
        "forgotten_at": "DATETIME NULL",
        "forget_reason": "VARCHAR(50) NULL",
    },
    "conversation_sessions": {
        "confidence": "DECIMAL(3,2) NOT NULL DEFAULT 1.00",
        "importance": "DECIMAL(3,2) NOT NULL DEFAULT 0.50",
        "source_type": "VARCHAR(50) NOT NULL DEFAULT 'chat_session'",
        "source_ref": "VARCHAR(255) NULL",
        "expires_at": "DATETIME NULL",
        "forgotten_at": "DATETIME NULL",
        "forget_reason": "VARCHAR(50) NULL",
    },
    "episodic_memories": {
        "confidence": "DECIMAL(3,2) NOT NULL DEFAULT 0.90",
        "importance": "DECIMAL(3,2) NOT NULL DEFAULT 0.70",
        "source_type": "VARCHAR(50) NOT NULL DEFAULT 'chat_episode'",
        "source_ref": "VARCHAR(255) NULL",
        "expires_at": "DATETIME NULL",
        "forgotten_at": "DATETIME NULL",
        "forget_reason": "VARCHAR(50) NULL",
    },
    "personal_tasks": {
        "status": "VARCHAR(30) DEFAULT 'todo'",
        "progress": "INT DEFAULT 0",
    },
}


INDEXES = {
    "chat_history": {"idx_chat_history_user_id": ("(user_id, id)", False)},
    "core_memories": {"idx_core_memories_user_active": ("(user_id, is_active, id)", False)},
    "user_profiles": {"idx_user_profiles_user": ("(user_id, id)", False)},
    "user_mood_timeline": {"idx_mood_timeline_user": ("(user_id, id)", False)},
    "memory_context_exclusions": {
        "uq_memory_context_exclusion": ("(user_id, chat_id, source_ref)", True),
        "idx_memory_context_exclusion_chat": ("(user_id, chat_id)", False),
    },
    "personal_knowledge": {"idx_knowledge_user": ("(user_id)", False)},
    "agent_experiences": {"idx_experiences_user": ("(user_id)", False)},
    "conversation_sessions": {
        "idx_conversation_sessions_user_activity": ("(user_id, last_activity_at)", False),
    },
    "episodic_memories": {
        "uq_episode_session_source": ("(session_id, source_fingerprint)", True),
        "idx_episodes_user_time": ("(user_id, occurred_at)", False),
        "idx_episodes_source_chat": ("(user_id, source_chat_id)", False),
    },
    "personal_tasks": {"idx_personal_tasks_user_done": ("(user_id, done, id)", False)},
    "personal_reminders": {"idx_personal_reminders_due": ("(done, scheduled_for, user_id)", False)},
    "personal_goals": {"idx_goals_user_status": ("(user_id, status)", False)},
    "goal_steps": {"idx_goal_steps_owner": ("(goal_id, user_id)", False)},
    "personal_notes": {
        "idx_personal_notes_user": ("(user_id)", False),
        "idx_personal_notes_archived": ("(user_id, is_archived)", False),
    },
}


def _create_tables(cursor: Any) -> None:
    for statement in CREATE_TABLES:
        cursor.execute(statement)


def _upgrade_legacy_columns(cursor: Any) -> None:
    for table, columns in LEGACY_COLUMNS.items():
        for column, definition in columns.items():
            cursor.execute(f"SHOW COLUMNS FROM `{table}` LIKE %s", (column,))
            if cursor.fetchone() is None:
                cursor.execute(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {definition}")


def _normalize_legacy_data(cursor: Any) -> None:
    cursor.execute("UPDATE personal_tasks SET status = 'done', progress = 100 WHERE done = 1")
    cursor.execute("UPDATE core_memories SET is_active = 0 WHERE memory_type = 'recent_reply'")


def _add_indexes(cursor: Any) -> None:
    for table, indexes in INDEXES.items():
        for index_name, (columns, unique) in indexes.items():
            cursor.execute(f"SHOW INDEX FROM `{table}` WHERE Key_name = %s", (index_name,))
            if cursor.fetchone() is None:
                qualifier = "UNIQUE " if unique else ""
                cursor.execute(f"CREATE {qualifier}INDEX `{index_name}` ON `{table}` {columns}")


MIGRATIONS = (
    Migration(1, "create_application_tables", _create_tables, "\n".join(CREATE_TABLES)),
    Migration(2, "upgrade_legacy_columns", _upgrade_legacy_columns, repr(LEGACY_COLUMNS)),
    Migration(3, "normalize_legacy_data", _normalize_legacy_data, "tasks_done_v1;recent_reply_v1"),
    Migration(4, "add_query_indexes", _add_indexes, repr(INDEXES)),
)

LATEST_SCHEMA_VERSION = MIGRATIONS[-1].version
_migration_lock = Lock()
_schema_ready = False


def _migration_table(cursor: Any) -> None:
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
            version INT PRIMARY KEY,
            name VARCHAR(160) NOT NULL,
            checksum CHAR(64) NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    )


def _applied_migrations(cursor: Any) -> dict[int, dict[str, Any]]:
    cursor.execute("SELECT version, name, checksum FROM schema_migrations ORDER BY version")
    return {int(row["version"]): dict(row) for row in (cursor.fetchall() or [])}


def ensure_schema(conn: Any, *, force: bool = False) -> dict[str, Any]:
    """Apply pending migrations on an existing connection exactly once per process."""
    global _schema_ready
    if not conn:
        raise DatabaseUnavailable("Không có kết nối để migration schema")
    if _schema_ready and not force:
        return {"ok": True, "version": LATEST_SCHEMA_VERSION, "applied": []}

    with _migration_lock:
        if _schema_ready and not force:
            return {"ok": True, "version": LATEST_SCHEMA_VERSION, "applied": []}
        # SHOW INDEX có thể trả nhiều dòng cho một composite index. Buffered cursor
        # đọc hết result set ngay khi execute, tránh mysql.connector báo
        # "Unread result found" ở câu lệnh migration kế tiếp.
        cursor = conn.cursor(dictionary=True, buffered=True)
        applied_now: list[dict[str, Any]] = []
        current_migration: Migration | None = None
        try:
            _migration_table(cursor)
            conn.commit()
            applied = _applied_migrations(cursor)
            for migration in MIGRATIONS:
                current_migration = migration
                previous = applied.get(migration.version)
                if previous:
                    if previous.get("name") != migration.name or previous.get("checksum") != migration.checksum:
                        raise DatabaseUnavailable(
                            f"Migration {migration.version} đã thay đổi sau khi được áp dụng"
                        )
                    continue
                migration.action(cursor)
                cursor.execute(
                    "INSERT INTO schema_migrations (version, name, checksum) VALUES (%s, %s, %s)",
                    (migration.version, migration.name, migration.checksum),
                )
                conn.commit()
                applied_now.append({"version": migration.version, "name": migration.name})
            _schema_ready = True
            return {"ok": True, "version": LATEST_SCHEMA_VERSION, "applied": applied_now}
        except DatabaseUnavailable:
            conn.rollback()
            raise
        except Exception as exc:
            conn.rollback()
            if current_migration is None:
                step = "khởi tạo bảng schema_migrations"
            else:
                step = f"migration {current_migration.version} ({current_migration.name})"
            raise DatabaseUnavailable(
                f"{step} thất bại: {type(exc).__name__}: {exc}"
            ) from exc
        finally:
            cursor.close()


def run_migrations(*, strict: bool = False) -> dict[str, Any]:
    """Open a connection, apply migrations and return a startup/CLI report."""
    conn = get_db_connection()
    if not conn:
        if strict:
            raise DatabaseUnavailable("Không thể kết nối MySQL để migration")
        return {"ok": False, "code": "database_unavailable", "reason": "database_unavailable", "version": None, "applied": []}
    try:
        return ensure_schema(conn, force=True)
    except DatabaseUnavailable as exc:
        if strict:
            raise
        return {"ok": False, "code": "migration_failed", "reason": str(exc), "version": None, "applied": []}
    finally:
        conn.close()


def _reset_migration_state_for_tests() -> None:
    global _schema_ready
    _schema_ready = False


if __name__ == "__main__":
    try:
        report = run_migrations(strict=True)
    except DatabaseUnavailable as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1) from exc
    print(json.dumps(report, ensure_ascii=False))
