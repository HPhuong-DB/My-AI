import os

from core.database import DatabaseUnavailable, get_db_connection


DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "default")


def _ensure_table_exists(conn):
    if not conn:
        return
    from core.migrations import ensure_schema

    ensure_schema(conn)


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
            message_id = getattr(cursor, "lastrowid", None)
            conn.commit()
            return message_id or True
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
                condition = (
                    " AND id > COALESCE((SELECT cutoff_chat_id FROM memory_context_state WHERE user_id = %s), 0)"
                    " AND NOT EXISTS (SELECT 1 FROM memory_context_exclusions excluded "
                    "WHERE excluded.user_id = chat_history.user_id AND excluded.chat_id = chat_history.id)"
                )
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
