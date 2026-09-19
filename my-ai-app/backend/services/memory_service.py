import re
import os

from core.database import DatabaseUnavailable, get_db_connection

DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "default")


def _ensure_memory_tables(conn):
    if not conn:
        return

    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS core_memories (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(100) NOT NULL DEFAULT 'default',
                memory_type VARCHAR(50) NOT NULL,
                fact TEXT NOT NULL,
                occurrence_count INT DEFAULT 1,
                is_active TINYINT(1) DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(100) NOT NULL DEFAULT 'default',
                username VARCHAR(50) NOT NULL,
                affection_level INT DEFAULT 0,
                mood VARCHAR(50) DEFAULT 'neutral',
                interaction_count INT DEFAULT 0,
                last_interaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_mood_timeline (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(100) NOT NULL DEFAULT 'default',
                username VARCHAR(50) NOT NULL,
                mood VARCHAR(50) DEFAULT 'neutral',
                affection_level INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute("SHOW COLUMNS FROM core_memories LIKE 'occurrence_count'")
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE core_memories ADD COLUMN occurrence_count INT DEFAULT 1")

        cursor.execute("SHOW COLUMNS FROM core_memories LIKE 'is_active'")
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE core_memories ADD COLUMN is_active TINYINT(1) DEFAULT 0")

        cursor.execute("SHOW COLUMNS FROM core_memories LIKE 'user_id'")
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE core_memories ADD COLUMN user_id VARCHAR(100) NOT NULL DEFAULT 'default'")

        cursor.execute("SHOW COLUMNS FROM user_profiles LIKE 'user_id'")
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE user_profiles ADD COLUMN user_id VARCHAR(100) NOT NULL DEFAULT 'default'")

        cursor.execute("SHOW COLUMNS FROM user_profiles LIKE 'mood'")
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE user_profiles ADD COLUMN mood VARCHAR(50) DEFAULT 'neutral'")

        cursor.execute("SHOW COLUMNS FROM user_profiles LIKE 'interaction_count'")
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE user_profiles ADD COLUMN interaction_count INT DEFAULT 0")

        cursor.execute("CREATE TABLE IF NOT EXISTS memory_context_state (user_id VARCHAR(100) PRIMARY KEY, cutoff_chat_id INT NOT NULL DEFAULT 0)")

        # Dọn các memory tạm thời được tạo bởi phiên bản cũ.
        cursor.execute("UPDATE core_memories SET is_active = 0 WHERE memory_type = 'recent_reply'")

        conn.commit()
    finally:
        cursor.close()


def _invalidate_history(cursor, user_id):
    # Keep the transcript visible, but never reintroduce superseded personal facts.
    cursor.execute(
        "INSERT INTO memory_context_state (user_id, cutoff_chat_id) "
        "SELECT %s, COALESCE(MAX(id), 0) FROM chat_history WHERE user_id = %s "
        "ON DUPLICATE KEY UPDATE cutoff_chat_id = VALUES(cutoff_chat_id)",
        (user_id, user_id),
    )


def _subject(memory_type, fact):
    prefixes = {
        "preference": r"^Người dùng (?:không còn thích|không thích|thích)\s+",
        "goal": r"^Người dùng (?:không còn học|không học|đang học)\s+",
    }
    return re.sub(prefixes.get(memory_type, r"^$"), "", fact, flags=re.I).strip().rstrip(".!?").casefold()


def save_memory(memory_type, fact, user_id=DEFAULT_USER_ID, *, strict=False):
    if not memory_type or not fact or not fact.strip():
        return False
    fact = fact.strip()
    conn = get_db_connection()
    if not conn:
        if strict:
            raise DatabaseUnavailable("Không thể lưu bộ nhớ")
        return False
    cursor = None
    try:
        _ensure_memory_tables(conn)
        from services.chat_service import _ensure_table_exists
        _ensure_table_exists(conn)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, fact FROM core_memories WHERE user_id = %s AND memory_type = %s AND is_active = 1 FOR UPDATE", (user_id, memory_type))
        existing = cursor.fetchall() or []
        matching = [row for row in existing if memory_type in {"user_name", "communication_style"} or _subject(memory_type, row["fact"]) == _subject(memory_type, fact)]
        if len(matching) == 1 and matching[0]["fact"].casefold() == fact.casefold():
            conn.commit()
            return True
        for row in matching:
            cursor.execute("UPDATE core_memories SET is_active = 0 WHERE id = %s AND user_id = %s", (row["id"], user_id))
        if matching or memory_type == "user_name" or fact.startswith("Người dùng không"):
            _invalidate_history(cursor, user_id)
        cursor.execute("INSERT INTO core_memories (user_id, memory_type, fact, occurrence_count, is_active) VALUES (%s, %s, %s, 1, 1)", (user_id, memory_type, fact))
        if memory_type == "user_name":
            cursor.execute("UPDATE user_profiles SET username = %s WHERE user_id = %s", (fact.removeprefix("Tên người dùng là "), user_id))
        conn.commit()
        return True
    except Exception as exc:
        conn.rollback()
        if strict:
            raise DatabaseUnavailable("Không thể lưu bộ nhớ") from exc
        return False
    finally:
        if cursor is not None:
            cursor.close()
        conn.close()


def get_recent_memories(limit=5, user_id=DEFAULT_USER_ID, *, strict=False):
    if limit <= 0:
        return []

    conn = get_db_connection()
    memories = []
    if conn:
        cursor = None
        try:
            _ensure_memory_tables(conn)
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT id, user_id, memory_type, fact FROM core_memories WHERE user_id = %s AND is_active = 1 ORDER BY id DESC LIMIT %s",
                (user_id, limit),
            )
            rows = cursor.fetchall()
            memories = [
                {"id": row["id"], "user_id": row["user_id"], "memory_type": row["memory_type"], "fact": row["fact"]}
                for row in rows
            ]
        except Exception as e:
            if strict:
                raise DatabaseUnavailable("Không thể đọc bộ nhớ") from e
            print(f"Lỗi đọc memory: {e}")
        finally:
            if conn.is_connected():
                if cursor is not None:
                    cursor.close()
                conn.close()
    if not conn and strict:
        raise DatabaseUnavailable("Không thể đọc bộ nhớ")
    return memories


def get_user_profile(user_id=DEFAULT_USER_ID):
    conn = get_db_connection()
    if not conn:
        return None

    cursor = None
    try:
        _ensure_memory_tables(conn)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT user_id, username, affection_level, mood, interaction_count, last_interaction FROM user_profiles WHERE user_id = %s ORDER BY id DESC LIMIT 1",
            (user_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "user_id": row["user_id"],
            "username": row["username"],
            "affection_level": int(row["affection_level"] or 0),
            "mood": row["mood"] or "neutral",
            "interaction_count": int(row["interaction_count"] or 0),
            "last_interaction": row["last_interaction"],
        }
    except Exception as e:
        print(f"Lỗi đọc user_profile: {e}")
        return None
    finally:
        if conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def save_user_profile(username, user_id=DEFAULT_USER_ID, mood="neutral", affection_delta=0, *, strict=False):
    if not username:
        return

    conn = get_db_connection()
    if conn:
        cursor = None
        try:
            _ensure_memory_tables(conn)
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, affection_level, mood, interaction_count FROM user_profiles WHERE user_id = %s AND username = %s ORDER BY id DESC LIMIT 1", (user_id, username))
            existing = cursor.fetchone()
            if existing:
                next_affection = int(existing["affection_level"] or 0) + int(affection_delta or 0)
                next_interactions = int(existing["interaction_count"] or 0) + 1
                final_mood = mood or existing["mood"] or "neutral"
                cursor.execute(
                    "UPDATE user_profiles SET affection_level = %s, mood = %s, interaction_count = %s, last_interaction = CURRENT_TIMESTAMP WHERE user_id = %s AND username = %s",
                    (next_affection, final_mood, next_interactions, user_id, username),
                )
                cursor.execute(
                    "INSERT INTO user_mood_timeline (user_id, username, mood, affection_level) VALUES (%s, %s, %s, %s)",
                    (user_id, username, final_mood, next_affection),
                )
            else:
                final_affection = int(affection_delta or 0)
                final_mood = mood or "neutral"
                cursor.execute(
                    "INSERT INTO user_profiles (user_id, username, affection_level, mood, interaction_count) VALUES (%s, %s, %s, %s, %s)",
                    (user_id, username, final_affection, final_mood, 1),
                )
                cursor.execute(
                    "INSERT INTO user_mood_timeline (user_id, username, mood, affection_level) VALUES (%s, %s, %s, %s)",
                    (user_id, username, final_mood, final_affection),
                )
            conn.commit()
        except Exception as e:
            if strict:
                raise DatabaseUnavailable("Không thể lưu hồ sơ") from e
            print(f"Lỗi lưu user_profile: {e}")
        finally:
            if conn.is_connected():
                if cursor is not None:
                    cursor.close()
                conn.close()

    if not conn and strict:
        raise DatabaseUnavailable("Không thể lưu hồ sơ")


def get_relationship_tone(affection_level=0):
    level = int(affection_level or 0)
    if level <= 0:
        return "mới gặp, nên nói lịch sự và giữ khoảng cách"
    if level <= 3:
        return "người quen, nên nói ôn hòa và thân thiện"
    if level <= 6:
        return "đã quen, nên nói gần gũi hơn nhưng vẫn tự nhiên"
    if level <= 9:
        return "thân quen, nên nói ấm áp, cởi mở và gần gũi"
    return "rất thân quen, nên nói như bạn thân, ấm áp và tự nhiên"


def get_user_mood_timeline(user_id=DEFAULT_USER_ID, limit=10):
    conn = get_db_connection()
    if not conn:
        return []

    cursor = None
    try:
        _ensure_memory_tables(conn)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT user_id, username, mood, affection_level, created_at FROM user_mood_timeline WHERE user_id = %s ORDER BY id DESC LIMIT %s",
            (user_id, limit),
        )
        rows = cursor.fetchall()
        return [
            {
                "user_id": row["user_id"],
                "username": row["username"],
                "mood": row["mood"],
                "affection_level": int(row["affection_level"] or 0),
                "created_at": row["created_at"],
            }
            for row in rows
        ]
    except Exception as e:
        print(f"Lỗi đọc mood timeline: {e}")
        return []
    finally:
        if conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def _extract_name(message):
    match = re.search(
        r"^(?:(?:tôi|mình|tớ)\s+)?(?:tên\s+(?:(?:của\s+)?(?:tôi|mình|tớ)\s+)?là|gọi\s+(?:tôi|mình|tớ)\s+là)\s+([^.!?;,\n]+)",
        message.strip(), re.IGNORECASE,
    )
    if match:
        name = match.group(1).strip()
        if 0 < len(name) <= 50 and name.casefold() not in {"bạn", "cậu", "anh", "chị", "em", "tớ", "mình", "tôi"}:
            return name
    return None


def _extract_preference(message):
    match = re.match(r"(?:tôi|mình|tớ)\s+(?:rất\s+)?thích\s+([^.!?;\n]+)[.!]?\s*$", message.strip(), re.I)
    return match.group(1).strip() if match else None


def _extract_goal(message):
    match = re.match(r"(?:tôi|mình|tớ)\s+(?:đang\s+)?học\s+([^.!?;\n]+)[.!]?\s*$", message.strip(), re.I)
    return match.group(1).strip() if match else None


def infer_relationship_state(message):
    if not message:
        return "neutral", 0

    text = message.lower().strip()
    positive_hits = 0
    negative_hits = 0

    positive_patterns = [
        "cảm ơn", "rất thích", "thích", "yêu", "vui", "hạnh phúc", "đáng yêu",
        "hay quá", "tốt", "đẹp", "tuyệt", "mình thích", "great", "love", "thank you"
    ]
    negative_patterns = [
        "buồn", "mệt", "stress", "căng thẳng", "lo lắng", "không ổn", "sợ",
        "chán", "đau", "nản", "tức", "giận", "khổ", "sad", "angry", "worried"
    ]

    for pattern in positive_patterns:
        if pattern in text:
            positive_hits += 1

    for pattern in negative_patterns:
        if pattern in text:
            negative_hits += 1

    if positive_hits > negative_hits:
        mood = "happy"
        affection_delta = max(1, positive_hits)
    elif negative_hits > positive_hits:
        if any(keyword in text for keyword in ["buồn", "sad", "mệt", "không ổn", "đau", "nản"]):
            mood = "sad"
        else:
            mood = "stressed"
        affection_delta = -max(1, negative_hits)
    else:
        mood = "neutral"
        affection_delta = 0

    return mood, affection_delta


def save_memory_from_conversation(user_message, assistant_reply, user_id=DEFAULT_USER_ID, *, strict=False):
    if not user_message:
        return
    user_text = user_message.strip()
    mood, affection_delta = infer_relationship_state(user_text)
    # Only direct statements, never questions or quoted/conditional examples.
    direct_text = re.sub(r'''```[\s\S]*?```|`[^`]*`|“[^”]*”|「[^」]*」|"[^"]*"|'[^']*' ''', ' ', user_text, flags=re.X)
    for statement in re.split(r"[.;!\n]+", direct_text):
        statement = statement.strip()
        if not statement or "?" in statement:
            continue
        addressed = re.match(r"(?:(?:từ giờ|bạn|cậu|huohuo)\s+)*gọi\s+(?:mình|tôi|tớ)\s+(?:là\s+)?(cậu|bạn|anh|chị|em)\b", statement, re.I)
        self_pronoun = re.search(r"xưng\s+(?:là\s+)?(tớ|mình|tôi|em|anh|chị)\b", statement, re.I)
        if not addressed and re.match(r"(?:(?:từ giờ|bạn|cậu|huohuo)\s+)*xưng\s+(?:là\s+)?(?:tớ|mình|tôi|em|anh|chị)\s*(?:,|và)\s*gọi\b", statement, re.I):
            addressed = re.search(r"gọi\s+(?:mình|tôi|tớ)\s+(?:là\s+)?(cậu|bạn|anh|chị|em)\b", statement, re.I)
        if addressed and self_pronoun:
            save_memory("communication_style", f"Huohuo xưng {self_pronoun.group(1).lower()}, gọi người dùng là {addressed.group(1).lower()}", user_id, strict=strict)
            continue
        name = _extract_name(statement)
        if name:
            save_memory("user_name", f"Tên người dùng là {name}", user_id, strict=strict)
        preference = _extract_preference(statement)
        goal = _extract_goal(statement)
        if preference:
            save_memory("preference", f"Người dùng thích {preference}", user_id, strict=strict)
        if goal:
            save_memory("goal", f"Người dùng đang học {goal}", user_id, strict=strict)
        negative = re.fullmatch(r"(?:tôi|mình|tớ)\s+không\s+(?:còn\s+)?(thích|học)\s+(.+?)(?:\s+nữa)?", statement, re.I)
        if negative:
            verb, subject = negative.groups()
            kind = "preference" if verb.lower() == "thích" else "goal"
            save_memory(kind, f"Người dùng không còn {verb.lower()} {subject}", user_id, strict=strict)
    existing = get_user_profile(user_id=user_id)
    names = [m for m in get_recent_memories(100, user_id) if m["memory_type"] == "user_name"]
    profile_name = names[0]["fact"].removeprefix("Tên người dùng là ") if names else (existing or {}).get("username") or "Bạn"
    save_user_profile(profile_name, user_id, mood=mood, affection_delta=affection_delta, strict=strict)


def _mutate_memory(memory_id, user_id, fact=None):
    conn = get_db_connection()
    if not conn:
        raise DatabaseUnavailable("Không thể thay đổi bộ nhớ")
    cursor = None
    try:
        _ensure_memory_tables(conn)
        from services.chat_service import _ensure_table_exists
        _ensure_table_exists(conn)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, memory_type, fact FROM core_memories WHERE id = %s AND user_id = %s AND is_active = 1 FOR UPDATE", (memory_id, user_id))
        memory = cursor.fetchone()
        if not memory:
            conn.rollback()
            return False
        if fact is not None:
            fact = fact.strip()
            if not fact or len(fact) > 2000:
                raise ValueError("Thông tin phải có từ 1 đến 2000 ký tự")
            if memory["memory_type"] == "user_name":
                name = fact.removeprefix("Tên người dùng là ").strip()
                if not name or len(name) > 50:
                    raise ValueError("Tên phải có từ 1 đến 50 ký tự")
                fact = f"Tên người dùng là {name}"
            # Editing into an existing subject must not leave contradictory active facts.
            cursor.execute("SELECT id, fact FROM core_memories WHERE user_id = %s AND memory_type = %s AND is_active = 1 FOR UPDATE", (user_id, memory["memory_type"]))
            for other in cursor.fetchall() or []:
                if other["id"] != memory_id and _subject(memory["memory_type"], other["fact"]) == _subject(memory["memory_type"], fact):
                    cursor.execute("UPDATE core_memories SET is_active = 0 WHERE id = %s AND user_id = %s", (other["id"], user_id))
            cursor.execute("UPDATE core_memories SET fact = %s WHERE id = %s AND user_id = %s", (fact, memory_id, user_id))
        else:
            cursor.execute("DELETE FROM core_memories WHERE id = %s AND user_id = %s", (memory_id, user_id))
        if memory["memory_type"] == "user_name":
            cursor.execute("UPDATE core_memories SET is_active = 0 WHERE user_id = %s AND memory_type = 'user_name' AND id <> %s", (user_id, memory_id))
            cursor.execute("UPDATE user_profiles SET username = %s WHERE user_id = %s", (fact.removeprefix("Tên người dùng là ") if fact else "Bạn", user_id))
            cursor.execute("UPDATE user_mood_timeline SET username = %s WHERE user_id = %s", (fact.removeprefix("Tên người dùng là ") if fact else "Bạn", user_id))
        _invalidate_history(cursor, user_id)
        conn.commit()
        return True
    except ValueError:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise DatabaseUnavailable("Không thể thay đổi bộ nhớ") from exc
    finally:
        if cursor is not None:
            cursor.close()
        conn.close()


def delete_memory(memory_id, user_id=DEFAULT_USER_ID):
    return _mutate_memory(memory_id, user_id)


def update_memory(memory_id, fact, user_id=DEFAULT_USER_ID):
    return _mutate_memory(memory_id, user_id, fact)
