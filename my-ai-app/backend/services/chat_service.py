import os

from core.database import DatabaseUnavailable, get_db_connection


DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "default")


def _ensure_table_exists(conn):
    if not conn:
        return

    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(100) NOT NULL DEFAULT 'default',
                role VARCHAR(50) NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute("SHOW COLUMNS FROM chat_history LIKE 'user_id'")
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE chat_history ADD COLUMN user_id VARCHAR(100) NOT NULL DEFAULT 'default'")
        conn.commit()
    finally:
        cursor.close()


# --- LƯU TIN NHẮN MỚI VÀO DATABASE ---
def save_chat_message(role, content, user_id=DEFAULT_USER_ID, *, strict=False):
    if not role or content is None:
        return

    conn = get_db_connection()
    if conn:
        cursor = None
        try:
            _ensure_table_exists(conn)
            cursor = conn.cursor()
            sql = "INSERT INTO chat_history (user_id, role, content) VALUES (%s, %s, %s)"
            cursor.execute(sql, (user_id, str(role), str(content)))
            conn.commit()
            return True
        except Exception as e:
            if strict:
                raise DatabaseUnavailable("Không thể lưu lịch sử") from e
            print(f"Lỗi lưu chat vào DB: {e}")
        finally:
            if conn.is_connected():
                if cursor is not None:
                    cursor.close()
                conn.close()

    if strict:
        raise DatabaseUnavailable("Không thể lưu lịch sử")
    return False


# --- LẤY 15 TIN NHẤN GẦN NHẤT LÀM NGỮ CẢNH ---
def get_recent_chat_history(limit=15, user_id=DEFAULT_USER_ID, *, for_context=True, strict=False):
    conn = get_db_connection()
    history = []
    if conn:
        cursor = None
        try:
            _ensure_table_exists(conn)
            cursor = conn.cursor(dictionary=True)
            condition = ""
            if for_context:
                cursor.execute("CREATE TABLE IF NOT EXISTS memory_context_state (user_id VARCHAR(100) PRIMARY KEY, cutoff_chat_id INT NOT NULL DEFAULT 0)")
                condition = " AND id > COALESCE((SELECT cutoff_chat_id FROM memory_context_state WHERE user_id = %s), 0)"
            sql = "SELECT role, content FROM chat_history WHERE user_id = %s" + condition + " ORDER BY id DESC LIMIT %s"
            cursor.execute(sql, (user_id, user_id, limit) if for_context else (user_id, limit))
            rows = cursor.fetchall()

            for row in reversed(rows):
                history.append({"role": row['role'], "content": row['content']})
        except Exception as e:
            if strict:
                raise DatabaseUnavailable("Không thể đọc lịch sử") from e
            print(f"Lỗi đọc chat history từ DB: {e}")
        finally:
            if conn.is_connected():
                if cursor is not None:
                    cursor.close()
                conn.close()
    if not conn and strict:
        raise DatabaseUnavailable("Không thể đọc lịch sử")
    return history
