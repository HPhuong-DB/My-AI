import unittest
import json
from unittest.mock import AsyncMock, patch
from services.dialogue_context_service import build_dialogue_context
from services.dialogue_policy_service import grounded_reply
from services import llm_service


class DialoguePolicyTests(unittest.TestCase):
    def reply(self, message, memories=(), history=(), profile=None):
        return grounded_reply(build_dialogue_context(message, list(history), list(memories), profile))

    def test_unavailable_current_sources_never_repeat_assistant_guess(self):
        result = self.reply('Hiện tại TFT mùa bao nhiêu?\n\n[TRA CỨU THỜI GIAN THỰC - KHÔNG CÓ NGUỒN]\nKhông có nguồn.', history=[{'role': 'assistant', 'content': 'Hiện tại mùa 17.'}])
        self.assertEqual(result[1], 'unverified_realtime')
        self.assertNotIn('17', result[0])

    def test_current_name_and_study_come_from_records(self):
        result = self.reply('Mình tên gì và đang học gì?', [{'memory_type': 'goal', 'fact': 'Người dùng đang học Rust'}], profile={'username': 'Hà'})
        self.assertIn('Hà', result[0])
        self.assertIn('Rust', result[0])

    def test_stopping_a_subject_does_not_invent_a_new_subject(self):
        result = self.reply('Mình đang học gì nhỉ?', [{'memory_type': 'goal', 'fact': 'Người dùng không còn học Rust'}])
        self.assertIn('không còn học Rust', result[0])
        self.assertIn('chưa biết', result[0])

    def test_assistant_claim_does_not_create_a_memory(self):
        result = self.reply('Bạn còn nhớ tên con mèo của mình không?', history=[{'role': 'assistant', 'content': 'Mèo của bạn tên Mimi.'}])
        self.assertNotIn('Mimi', result[0])
        self.assertIn('chưa có', result[0])

    def test_real_user_statement_stays_available_for_model_recall(self):
        result = self.reply('Bạn còn nhớ tên con mèo của mình không?', history=[{'role': 'user', 'content': 'Con mèo của mình tên Đốm.'}])
        self.assertIsNone(result)

    def test_compound_creative_or_advice_requests_are_not_short_circuited(self):
        self.assertIsNone(self.reply('Mình tên gì? Viết thơ về tên mình.', profile={'username': 'Hà'}))
        self.assertIsNone(self.reply('Mình học gì để làm game?'))

    def test_personal_style_applies_to_grounded_answers(self):
        result = self.reply('Mình tên gì?', [{'memory_type': 'communication_style', 'fact': 'Huohuo xưng tớ, gọi người dùng là cậu'}], profile={'username': 'Hà'})
        self.assertEqual(result[0], 'Cậu tên là Hà.')

    def test_pronoun_style_does_not_rewrite_words_inside_facts(self):
        facts = [
            {'memory_type': 'communication_style', 'fact': 'Huohuo xưng tớ, gọi người dùng là cậu'},
            {'memory_type': 'goal', 'fact': 'Người dùng đang học cách làm bạn với bản thân'},
        ]
        self.assertEqual(self.reply('Tớ đang học gì?', facts)[0], 'Cậu đang học cách làm bạn với bản thân.')
        result = self.reply('Bạn tớ tên gì, còn tớ tên gì?', facts,
                            history=[{'role': 'user', 'content': 'Bạn tớ tên là Khánh.'}], profile={'username': 'Hà'})
        self.assertEqual(result[0], 'Người bạn được cậu nhắc đến tên Khánh; còn cậu tên Hà.')

    def test_missing_photo_is_not_described(self):
        result = self.reply('Bạn thấy gì trong ảnh mình vừa gửi?')
        self.assertEqual(result[1], 'missing_input')
        self.assertIn('chưa nhận được ảnh', result[0])

    def test_unrelated_factual_question_is_left_to_model(self):
        self.assertIsNone(self.reply('Thời tiết ở Atlantis thế nào?'))

    def test_identity_variants_keep_name_but_leave_compound_requests_to_model(self):
        for message in ['Bạn là ai vậy?', 'Cậu tên gì nhỉ?', 'Bạn tên là gì?']:
            self.assertIn('Huohuo', self.reply(message)[0])
        self.assertIsNone(self.reply('Bạn là ai? Viết một bài thơ.'))

    def test_correction_acknowledgment_requires_persisted_fact(self):
        message = 'Mình không còn thích cà phê nữa.'
        self.assertIsNone(self.reply(message))
        fact = [{'memory_type': 'preference', 'fact': 'Người dùng không còn thích cà phê'}]
        self.assertIn('bạn không còn thích cà phê', self.reply(message, fact)[0])
        self.assertIsNone(self.reply('Mai nói: "Mình không còn thích cà phê nữa."', fact))

    def test_two_person_names_use_user_statements_not_assistant_identity(self):
        history = [
            {'role': 'user', 'content': 'Mình tên là Hà. Bạn mình tên là Khánh.'},
            {'role': 'assistant', 'content': 'Mình tên Huohuo. Bạn của bạn tên Minh.'},
        ]
        result = self.reply('Bạn mình tên gì, còn mình tên gì?', history=history, profile={'username': 'Hà'})
        self.assertIn('Khánh', result[0])
        self.assertIn('Hà', result[0])
        self.assertNotIn('Huohuo', result[0])
        self.assertNotIn('Minh', result[0])
        self.assertIsNone(self.reply('Bạn mình tên gì, còn mình tên gì?', history=history[1:], profile={'username': 'Hà'}))

    def test_tool_and_search_evidence_are_left_to_model(self):
        self.assertIsNone(self.reply('Mình tên gì?\n\nKết quả thực thi công cụ nội bộ:\n{}'))
        self.assertIsNone(self.reply('Mình tên gì?\n\n[TRA CỨU WEB]\nabc'))


class DialogueStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_grounded_recall_stream_does_not_report_fake_model_latency(self):
        prompt = build_dialogue_context('Mình tên gì?', [], [], {'username': 'Hà'})
        with patch.object(llm_service, '_prepare_prompt', new=AsyncMock(return_value=(prompt, '', 'fast'))), patch.object(llm_service, '_stream_ollama') as model:
            chunks = [chunk async for chunk in llm_service.stream_huohuo_response('Mình tên gì?', 'alice')]
        model.assert_not_called()
        self.assertTrue(chunks[-1].done)
        self.assertEqual(json.loads(chunks[-1].content)['reply_vi'], 'Bạn tên là Hà.')
        self.assertEqual(chunks[-1].metrics.generation_path, 'grounded_memory')
        self.assertIsNone(chunks[-1].metrics.first_token_ms)
        self.assertEqual(chunks[-1].metrics.total_llm_ms, 0)

    async def test_greeting_stream_skips_model_and_preserves_pronouns(self):
        for text in ('Hi', 'Hello!', 'Chào Huohuo', 'Xin chào bạn nhé 👋'):
            memories = [{'memory_type': 'communication_style', 'fact': 'Huohuo xưng tớ, gọi người dùng là cậu'}]
            prompt = build_dialogue_context(text, [], memories, None)
            with patch.object(llm_service, '_prepare_prompt', AsyncMock(return_value=(prompt, '', 'fast'))), patch.object(llm_service, '_stream_ollama') as model:
                chunks = [chunk async for chunk in llm_service.stream_huohuo_response(text, 'alice')]
            model.assert_not_called()
            self.assertEqual(chunks[-1].metrics.generation_path, 'greeting')
            self.assertEqual(chunks[-1].metrics.total_llm_ms, 0)
            self.assertIn('cậu', json.loads(chunks[-1].content)['reply_vi'])

    async def test_greeting_does_not_swallow_question_or_repeat_last_reply(self):
        for text in ('Chào bạn, hôm nay TFT mùa bao nhiêu?', 'Hello, mình đang buồn', 'Hãy nói hello', 'Chào bạn. Kể chuyện đi'):
            self.assertIsNone(grounded_reply(build_dialogue_context(text, [], [], None)))
        prompt = build_dialogue_context('hi', [{'role': 'user', 'content': 'hello'}, {'role': 'assistant', 'content': 'Chào bạn. Mình nghe nè.'}], [], None)
        self.assertNotEqual(grounded_reply(prompt)[0], 'Chào bạn. Mình nghe nè.')

    async def test_three_greetings_vary_without_questions_and_respect_each_pronoun_pair(self):
        for speaker, listener in [('mình', 'bạn'), ('tớ', 'cậu'), ('em', 'anh'), ('tôi', 'chị')]:
            memories = [{'memory_type': 'communication_style', 'fact': f'Huohuo xưng {speaker}, gọi người dùng là {listener}'}]
            history, replies = [], []
            for greeting in ('hi', 'hello', 'chào Huohuo'):
                reply, path = grounded_reply(build_dialogue_context(greeting, history, memories, None))
                self.assertEqual(path, 'greeting')
                self.assertIn(listener, reply)
                self.assertNotIn('?', reply)
                self.assertNotIn('ma', reply.split())
                self.assertNotIn(reply, replies)
                history.extend([{'role': 'user', 'content': greeting}, {'role': 'assistant', 'content': reply}])
                replies.append(reply)
            self.assertLessEqual(sum('Ừm' in reply for reply in replies), 1)

    async def test_identity_is_huohuo_and_honest_about_ai(self):
        reply, path = grounded_reply(build_dialogue_context('Bạn là ai?', [], [], None))
        self.assertEqual(path, 'identity')
        self.assertIn('Huohuo', reply)
        self.assertIn('AI', reply)
        self.assertNotIn('Neuro', reply)
