"""Grounded answers for narrow factual intents; open conversation stays generative.

These checks use retrieved facts and explicit user statements, never assistant
claims as evidence. They do not attempt unrestricted semantic understanding.
"""
import json
import re

from services.dialogue_context_service import DialoguePrompt, asks_user_name, normalize, tokens, is_simple_greeting


def grounded_reply(prompt: str) -> tuple[str, str] | None:
    if not isinstance(prompt, DialoguePrompt):
        return None
    message = prompt.messages[-1]['content']
    if '\n\n[THIẾU CHỦ ĐỀ THAM CHIẾU]\n' in message:
        return ('Bạn đang nói đến chủ đề hoặc sản phẩm nào vậy?', 'clarify_intent')
    if '\n\n[TRA CỨU THỜI GIAN THỰC - KHÔNG CÓ NGUỒN]\n' in message:
        return ('Mình chưa lấy được nguồn web để xác minh thông tin hiện tại, nên chưa thể khẳng định câu trả lời.', 'unverified_realtime')
    # Tool summaries and external research have their own evidence path.
    if '\n\nKết quả thực thi công cụ nội bộ' in message or '\n\n[TRA CỨU' in message:
        return None
    query = normalize(message).strip(' .!?')
    data = json.loads(prompt.evidence)
    facts = data['ky_uc_lien_quan']
    by_type = lambda kind: [item['noi_dung'] for item in facts if item['loai'] == kind]

    def answer(text, path='grounded_memory', **values):
        speaker, listener = 'mình', 'bạn'
        for style in by_type('communication_style'):
            match = re.fullmatch(r'Huohuo xưng (tớ|mình|tôi|em|anh|chị), gọi người dùng là (cậu|bạn|anh|chị|em)', style)
            if match:
                speaker, listener = match.groups()
                break
        # Substitute only template pronouns, never words inside names or memories.
        return text.format(speaker=speaker, Speaker=speaker.capitalize(),
                           listener=listener, Listener=listener.capitalize(), **values), path

    if is_simple_greeting(message):
        choices = [
            'Chào {listener}. {Speaker} nghe nè.',
            'Ừm, chào {listener}. Cứ nói tự nhiên nhé.',
            'Chào {listener}! Không cần nghĩ lời mở đầu đâu.',
        ]
        recent = set()
        for item in prompt.messages[:-1]:
            if item['role'] == 'assistant':
                try:
                    recent.add(json.loads(item['content'])['reply_vi'])
                except (ValueError, KeyError, TypeError):
                    recent.add(item['content'])
        for template in choices:
            result = answer(template, 'greeting')
            if result[0] not in recent:
                return result
        return answer(choices[0], 'greeting')

    if re.fullmatch(r'(?:ban|cau|huohuo) (?:la ai|ten (?:la )?gi)(?: (?:vay|nhi|the))?', query):
        return answer('{Speaker} là Huohuo, AI đồng hành của {listener}. Hơi nhát một chút, nhưng vẫn có chính kiến nhé.', 'identity')
    if re.search(r'anh.*(?:vua gui|dinh kem)|(?:vua gui|dinh kem).*anh', query) and re.search(r'thay|nhin|mo ta|trong anh', query):
        return answer('{Speaker} chưa nhận được ảnh trong lượt chat này. {Listener} gửi ảnh vào phần nhận xét ảnh nhé.', 'missing_input')

    question = '?' in message or bool(re.search(r'\b(?:gi|nao|co nho|con nho)\b', query))
    # Acknowledge only a complete, direct correction that is already persisted.
    # Never reinterpret quoted speech or a compound request as a user's own fact.
    correction = re.fullmatch(r'(?:mình|tôi|tớ)\s+không\s+(?:còn\s+)?(thích|học)\s+([^.!?;\n]+?)(?:\s+nữa)?[.!]?', message.strip(), re.I)
    if correction:
        verb, subject = correction.groups()
        expected = normalize(f'Người dùng không còn {verb} {subject}')
        if any(normalize(item['noi_dung']) == expected for item in facts):
            return answer('{Speaker} nhớ rồi, {listener} không còn {verb} {subject} nữa.', verb=verb.lower(), subject=subject)
    if re.search(r'\b(viet|giai thich|so sanh|ke chuyen|lam tho|dich|goi y|nen|de lam|can hoc|huong dan)\b', query):
        return None
    # Multi-person questions need native dialogue roles, not the user's profile alone.
    third_party = bool(re.search(r'ban (?:cua )?(?:minh|toi|to)\b|ban than|meo|cho|me |bo |anh trai|chi gai', query))
    if question and asks_user_name(query) and third_party:
        # Resolve the narrow two-name question only from explicit USER statements.
        # Quoted speech is excluded, and the assistant can never name the friend.
        clauses = re.split(r',?\s+(?:con|va)\s+', query)
        own_name = r'(?:minh|toi|to) ten (?:la )?gi'
        friend_name = r'ban (?:cua )?(?:minh|toi|to) ten (?:la )?gi'
        if len(clauses) == 2 and any(re.fullmatch(own_name, part) for part in clauses) and any(re.fullmatch(friend_name, part) for part in clauses):
            friend = None
            for item in prompt.messages[:-1]:
                if item['role'] != 'user':
                    continue
                direct = re.sub(r'''```[\s\S]*?```|`[^`]*`|“[^”]*”|"[^"]*"|'[^']*' ''', ' ', item['content'], flags=re.X)
                for statement in re.split(r'[.!;\n]+', direct):
                    match = re.fullmatch(r'Bạn\s+(?:của\s+)?(?:mình|tôi|tớ)\s+tên\s+(?:là\s+)?([^?]+)', statement.strip(), re.I)
                    if match:
                        friend = match.group(1).strip()
            name = data.get('ten_nguoi_dung')
            if friend and name:
                return answer('Người bạn được {listener} nhắc đến tên {friend}; còn {listener} tên {name}.', friend=friend, name=name)
            return None
    if question and asks_user_name(query) and not third_party:
        name = data.get('ten_nguoi_dung')
        reply = '{Listener} tên là {name}.' if name else '{Speaker} chưa có tên của {listener} trong bộ nhớ hiện tại.'
        values = {'name': name}
        if 'hoc' in query:
            active = [fact.removeprefix('Người dùng đang học ') for fact in by_type('goal') if fact.startswith('Người dùng đang học ')]
            values['subjects'] = ', '.join(active)
            reply += ' {Listener} đang học {subjects}.' if active else ' {Speaker} chưa biết {listener} đang học môn gì.'
        return answer(reply, **values)

    if question and re.search(r'(?:minh|toi|to) (?:dang )?hoc (?:gi|mon nao)', query):
        goals = by_type('goal')
        active = [fact.removeprefix('Người dùng đang học ') for fact in goals if fact.startswith('Người dùng đang học ')]
        stopped = [fact.removeprefix('Người dùng không còn học ') for fact in goals if fact.startswith('Người dùng không còn học ')]
        if active:
            return answer('{Listener} đang học {subjects}.', subjects=', '.join(active))
        if stopped:
            return answer('{Listener} đã nói không còn học {subjects}; {speaker} chưa biết {listener} đang học môn nào khác.', subjects=', '.join(stopped))
        return answer('{Speaker} chưa có thông tin {listener} đang học môn gì.')

    if question and re.search(r'(?:minh|toi|to) (?:con )?thich', query):
        preferences = by_type('preference')
        positive = [fact for fact in preferences if fact.startswith('Người dùng thích ')]
        if not positive and re.search(r'mon an|so thich|thich (?:gi|mon nao)', query):
            return answer('{Speaker} chưa có thông tin chắc chắn về sở thích đó của {listener}.')
        for fact in preferences:
            if fact.startswith('Người dùng không còn thích '):
                subject = fact.removeprefix('Người dùng không còn thích ')
                if normalize(subject) in query:
                    return answer('{Listener} đã nói không còn thích {subject}.', subject=subject)

    if question and re.search(r'co nho|con nho|da ke|tung ke|hom qua.*ke', query):
        subject_tokens = tokens(query) - set('hom qua ke noi tung biet ten con'.split())
        explicit_history = [item['content'] for item in prompt.messages[:-1] if item['role'] == 'user' and '?' not in item['content']]
        available = [item['noi_dung'] for item in facts] + explicit_history
        if not any(subject_tokens & tokens(item) for item in available):
            return answer('Trong phần ký ức {speaker} còn giữ chưa có thông tin đó. {Listener} nhắc lại cho {speaker} nhé?')
    return None
