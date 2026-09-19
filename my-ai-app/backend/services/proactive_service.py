"""Persistent conversational boundaries and grounded proactive topics (no LLM calls)."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import re

from core.database import DatabaseUnavailable, get_db_connection
from services.dialogue_context_service import normalize, tokens


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@contextmanager
def connection():
    conn = get_db_connection()
    if not conn:
        raise DatabaseUnavailable('Không đọc được tùy chọn chủ động')
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('''CREATE TABLE IF NOT EXISTS proactive_preferences (
            user_id VARCHAR(100) PRIMARY KEY,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            resume_on_message BOOLEAN NOT NULL DEFAULT FALSE,
            quiet_until DATETIME(6) NULL,
            awaiting_reply BOOLEAN NOT NULL DEFAULT FALSE,
            last_topic VARCHAR(160) NULL,
            last_sent_at DATETIME(6) NULL,
            last_user_at DATETIME(6) NULL
        )''')
        yield conn, cursor
    except Exception as exc:
        conn.rollback()
        if isinstance(exc, DatabaseUnavailable):
            raise
        raise DatabaseUnavailable('Không lưu được tùy chọn chủ động') from exc
    finally:
        cursor.close()
        conn.close()


def preferences(user_id):
    with connection() as (_, cursor):
        cursor.execute('SELECT * FROM proactive_preferences WHERE user_id = %s', (user_id,))
        row = cursor.fetchone() or dict(user_id=user_id, enabled=True, resume_on_message=False,
                                       quiet_until=None, awaiting_reply=False, last_topic=None,
                                       last_sent_at=None, last_user_at=None)
    row['enabled'] = bool(row['enabled']) or bool(row['quiet_until'] and row['quiet_until'] <= utcnow())
    row['awaiting_reply'] = bool(row['awaiting_reply'])
    row['resume_on_message'] = bool(row['resume_on_message'])
    return row


def set_enabled(user_id, enabled):
    with connection() as (conn, cursor):
        cursor.execute('''INSERT INTO proactive_preferences (user_id, enabled) VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE enabled=VALUES(enabled), resume_on_message=FALSE,
            quiet_until=NULL''', (user_id, enabled))
        conn.commit()
    return preferences(user_id)


def direct_text(text):
    return re.sub(r'''```[\s\S]*?```|`[^`]*`|“[^”]*”|"[^"]*"|'[^']*' ''', ' ', text, flags=re.X)


def boundary_request(text):
    """Return enabled/resume-on-next-message/duration for direct requests only."""
    for sentence in re.split(r'[.!;\n]+', direct_text(text)):
        value = normalize(sentence).strip(' ,?')
        if re.match(r'^(?:tu gio |bay gio )?(?:(?:ban|cau|huohuo) )?(?:hay )?(?:chu dong (?:bat chuyen|noi chuyen)|bat chuyen lai|noi chuyen tiep|cu bat chuyen)', value):
            return True, False, None
        if re.match(r'^(?:(?:ban|cau|huohuo) )?(?:hay )?(?:im lang|dung (?:lam phien|bat chuyen|hoi them|chu dong)|chi (?:nghe|lang nghe))', value) or re.match(r'^(?:minh|toi|to) (?:muon|can) (?:yen lang|im lang|tap trung|ban chi nghe)', value):
            duration = re.search(r'\b(\d{1,3}) (phut|gio)\b', value)
            seconds = min(86400, int(duration[1]) * (60 if duration[2] == 'phut' else 3600)) if duration else None
            return False, False, seconds
        if re.match(r'^(?:minh|toi|to) chi muon (?:ke|chia se)', value):
            return False, False, None
        if re.match(r'^(?:minh|toi|to) (?:(?:phai |se )?di (?:ngu|lam|roi)|ban(?: roi)?$|dang (?:tap trung|lam viec))', value):
            return False, True, None
    return None


def observe_message(user_id, text):
    request = boundary_request(text)
    with connection() as (conn, cursor):
        cursor.execute('INSERT IGNORE INTO proactive_preferences (user_id) VALUES (%s)', (user_id,))
        cursor.execute('''UPDATE proactive_preferences SET
            enabled=IF(resume_on_message, TRUE, enabled), resume_on_message=FALSE,
            awaiting_reply=FALSE, last_user_at=%s WHERE user_id=%s''', (utcnow(), user_id))
        if request:
            enabled, resume, seconds = request
            until = utcnow() + timedelta(seconds=seconds) if seconds is not None else None
            cursor.execute('UPDATE proactive_preferences SET enabled=%s, resume_on_message=%s, quiet_until=%s WHERE user_id=%s', (enabled, resume, until, user_id))
        conn.commit()


def record_outreach(user_id, topic):
    with connection() as (conn, cursor):
        cursor.execute('''INSERT INTO proactive_preferences (user_id, awaiting_reply, last_topic, last_sent_at)
            VALUES (%s, TRUE, %s, %s) ON DUPLICATE KEY UPDATE
            awaiting_reply=TRUE, last_topic=VALUES(last_topic), last_sent_at=VALUES(last_sent_at)''', (user_id, topic, utcnow()))
        conn.commit()


def choose_topic(history, memories, goals=()):
    """Use active personal facts connected to recent USER turns; otherwise be silent."""
    recent = ' '.join(direct_text(item['content']) for item in history if item['role'] == 'user')[-2500:]
    subjects = tokens(recent) - {'hoc', 'thich', 'ten', 'hom', 'nay', 'noi', 'chuyen'}
    if not subjects:
        return None
    speaker, listener = 'mình', 'bạn'
    for item in memories:
        if item.get('memory_type') == 'communication_style':
            match = re.fullmatch(r'Huohuo xưng (tớ|mình|tôi|em|anh|chị), gọi người dùng là (cậu|bạn|anh|chị|em)', item['fact'])
            if match:
                speaker, listener = match.groups()
    negative = [re.sub(r'^Người dùng không (?:còn )?(?:thích|học) ', '', item['fact']) for item in memories if item['fact'].startswith('Người dùng không')]
    for goal in goals:
        title = str(goal.get('title', ''))
        if goal.get('status') not in {'at_risk', 'stalled', 'overdue'} or not 0 < len(title) <= 100:
            continue
        if not (tokens(title) & subjects) or any(tokens(fact) and tokens(fact) <= tokens(title) for fact in negative):
            continue
        return {'kind': 'progress', 'key': f"goal:{goal.get('goal_id')}:{goal['status']}",
                'message': f'Về mục tiêu {title} vừa nhắc, {listener} có muốn cùng {speaker} chọn một bước nhỏ để làm tiếp không?'}
    for item in memories:
        fact = item['fact']
        match = re.fullmatch(r'Người dùng (thích|đang học) (.{1,100})', fact)
        if not match or item.get('memory_type') not in {'preference', 'goal'}:
            continue
        verb, subject = match.groups()
        if not (tokens(subject) & subjects) or any(normalize(subject) == normalize(fact) for fact in negative):
            continue
        key = hashlib.sha256(normalize(fact).encode()).hexdigest()[:24]
        message = (f'{listener.capitalize()} từng nói thích {subject}. Hôm nay có điều gì về chuyện đó muốn kể {speaker} nghe không?'
                   if verb == 'thích' else f'Về việc học {subject}, {listener} có muốn cùng {speaker} thử một câu hỏi nhỏ không?')
        return {'kind': 'context', 'key': f'memory:{key}', 'message': message}
    return None
