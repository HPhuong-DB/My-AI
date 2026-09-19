import unittest
from agent.presence import Presence
from services.proactive_service import boundary_request, choose_topic


class ProactiveContextTests(unittest.TestCase):
    def test_direct_quiet_resume_and_away_requests(self):
        self.assertEqual(boundary_request('Mình muốn yên lặng một lát, đừng hỏi thêm nhé.'), (False, False, None))
        self.assertEqual(boundary_request('Tớ chỉ muốn kể thôi, chưa muốn chỉnh sửa.'), (False, False, None))
        self.assertEqual(boundary_request('Đừng làm phiền trong 10 phút.'), (False, False, 600))
        self.assertEqual(boundary_request('Mình đi ngủ đây.'), (False, True, None))
        self.assertEqual(boundary_request('Bạn chủ động bắt chuyện lại nhé.'), (True, False, None))

    def test_quotes_third_parties_and_emotion_negation_do_not_mute(self):
        for text in ['Mai nói: "Đừng làm phiền mình."', 'Nếu mình muốn yên lặng thì sao?', 'Mình không buồn nữa.', 'Bạn mình muốn yên lặng.', 'Giải thích từ im lặng.']:
            self.assertIsNone(boundary_request(text), text)

    def test_no_unrelated_memory_or_assistant_claim_becomes_a_topic(self):
        memories = [{'memory_type': 'preference', 'fact': 'Người dùng thích vẽ tranh'}]
        self.assertIsNone(choose_topic([{'role': 'user', 'content': 'Mình đang học Rust.'}], memories))
        self.assertIsNone(choose_topic([{'role': 'assistant', 'content': 'Bạn thích vẽ tranh.'}], memories))
        self.assertIsNone(choose_topic([{'role': 'user', 'content': 'Mai nói: "Mình thích vẽ tranh."'}], memories))

    def test_negative_facts_prevent_a_stale_goal_prompt(self):
        memories = [{'memory_type': 'goal', 'fact': 'Người dùng không còn học Rust'}]
        goals = [{'goal_id': 4, 'title': 'Học Rust', 'status': 'stalled'}]
        self.assertIsNone(choose_topic([{'role': 'user', 'content': 'Mình không còn học Rust.'}], memories, goals))

    def test_style_applies_without_changing_the_memory_subject(self):
        topic = choose_topic([{'role': 'user', 'content': 'Tớ học cách làm bạn với bản thân.'}], [
            {'memory_type': 'communication_style', 'fact': 'Huohuo xưng tớ, gọi người dùng là cậu'},
            {'memory_type': 'goal', 'fact': 'Người dùng đang học cách làm bạn với bản thân'},
        ])
        self.assertIn('cậu có muốn cùng tớ', topic['message'])
        self.assertIn('làm bạn với bản thân', topic['message'])

    def test_presence_expires_and_is_separate_per_connection_and_user(self):
        now = [0]
        presence = Presence(now=lambda: now[0])
        ready = dict(visible=True, busy=False, typing=False, reading=False, local_hour=12)
        presence.update('a', 'alice', ready)
        self.assertIsNone(presence.reason('alice'))
        self.assertEqual(presence.reason('bob'), 'not_present')
        presence.update('b', 'alice', {**ready, 'typing': True})
        self.assertEqual(presence.reason('alice'), 'user_busy')
        presence.remove('b')
        self.assertIsNone(presence.reason('alice'))
        now[0] = 46
        self.assertEqual(presence.reason('alice'), 'not_present')

    def test_invalid_presence_is_not_available(self):
        presence = Presence()
        self.assertFalse(presence.update('a', 'alice', {'visible': 'true'}))
        self.assertEqual(presence.reason('alice'), 'not_present')
