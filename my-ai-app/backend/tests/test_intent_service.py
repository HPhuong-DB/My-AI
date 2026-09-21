import unittest
from unittest.mock import AsyncMock, patch
from services import intent_service as intent
from api import chat


class IntentTests(unittest.IsolatedAsyncioTestCase):
    async def test_clear_intents_do_not_need_model(self):
        cases = [
            ('Hiện tại Đấu trường chân lý đang là mùa bao nhiêu', 'information', 'web'),
            ('Mùa 17 chơi vui thật', 'social', 'conversation'),
            ('Bạn thấy mùa này vui không?', 'opinion', 'conversation'),
            ('Hôm nay mình buồn quá', 'emotional_support', 'conversation'),
            ('Bạn còn nhớ mình thích gì không?', 'personal_memory', 'memory'),
            ('Nhắc mình học lúc 8 giờ', 'action', 'conversation'),
            ('Tìm giúp mình tài liệu Rust', 'information', 'web'),
            ('Tại sao bầu trời xanh?', 'information', 'conversation'),
        ]
        with patch.object(intent, 'model_intent', AsyncMock()) as model:
            for text, kind, source in cases:
                result = await intent.classify_intent(text)
                self.assertEqual((result.kind, result.source), (kind, source), text)
            model.assert_not_awaited()

    async def test_ordinary_chat_skips_second_model_and_history_lookup(self):
        with patch.object(intent, 'model_intent', AsyncMock()) as model, patch.object(chat.memory_orchestrator, 'recall_history') as history:
            self.assertEqual(await chat._intent_context('Bạn kể gì vui đi', 'alice'), 'Bạn kể gì vui đi')
            self.assertEqual(await chat._intent_context('Ừm, thú vị đấy', 'alice'), 'Ừm, thú vị đấy')
            model.assert_not_awaited()
            history.assert_not_called()

    async def test_followup_uses_user_topic_not_assistant_season_claim(self):
        history = [{'role': 'user', 'content': 'TFT là gì?'}, {'role': 'assistant', 'content': 'Hiện tại TFT mùa 17.'}]
        with patch.object(intent, 'model_intent', AsyncMock(return_value=None)):
            result = await intent.classify_intent('Còn mùa hiện tại thì sao?', history)
        self.assertEqual(result.source, 'web')
        self.assertIn('TFT', result.query)
        self.assertNotIn('17', result.query)

    async def test_named_product_followup_uses_history_without_model(self):
        data = dict(kind='information', source='web', fresh=True, topic_index=0, confidence=.9)
        history = [{'role': 'user', 'content': 'Mình đang thử ứng dụng Obsidian.'}]
        with patch.object(intent, 'model_intent', AsyncMock(return_value=data)) as model:
            result = await intent.classify_intent('Còn bản miễn phí thì sao?', history)
            model.assert_not_awaited()
        self.assertEqual(result.method, 'context_fallback')
        self.assertIn('Obsidian', result.query)

    async def test_invalid_low_confidence_or_assistant_reference_cannot_search(self):
        history = [{'role': 'user', 'content': 'Mình đang nghĩ về chuyện này.'}, {'role': 'assistant', 'content': 'Secret guess'}]
        for changes in ({'confidence': .2}, {'fresh': 'true'}, {'topic_index': 1}, {'kind': 'action'}, {'source': 'execute'}, {'topic_index': -1}):
            data = dict(kind='information', source='web', fresh=True, topic_index=4, confidence=.9)
            data.update(changes)
            with patch.object(intent, 'model_intent', AsyncMock(return_value=data)):
                result = await intent.classify_intent('Còn bản đó thì sao?', history)
            self.assertEqual(result.kind, 'clarification')
            self.assertNotEqual(result.source, 'web')

    async def test_timeout_does_not_invent_missing_context(self):
        with patch.object(intent, 'model_intent', AsyncMock(side_effect=TimeoutError)):
            result = await intent.classify_intent('Còn cái đó thì sao?')
        self.assertEqual(result.kind, 'clarification')

    async def test_chat_reads_scoped_history_and_removes_current_duplicate(self):
        text = 'Còn mùa hiện tại thì sao?'
        history = [{'role': 'user', 'content': 'TFT là gì?'}, {'role': 'user', 'content': text}]
        with patch.object(chat.memory_orchestrator, 'recall_history', return_value=history) as read, patch.object(intent, 'model_intent', AsyncMock(return_value=None)), patch.object(chat, '_realtime_context', AsyncMock(return_value='grounded')) as search:
            self.assertEqual(await chat._intent_context(text, 'alice'), 'grounded')
        read.assert_called_once_with('alice', limit=11, strict=True)
        self.assertIn('TFT', search.call_args.kwargs['search_query'])

    async def test_followup_can_reference_topic_five_exchanges_earlier(self):
        history = [{'role': 'user', 'content': 'Mình đang thử ứng dụng Obsidian.'}]
        for number in range(4):
            history.extend([
                {'role': 'assistant', 'content': f'Đã rõ {number}.'},
                {'role': 'user', 'content': f'Mình còn nghĩ thêm {number}.'},
            ])
        with patch.object(intent, 'model_intent', AsyncMock(return_value=dict(
            kind='information', source='web', fresh=True, topic_index=0, confidence=.9,
        ))):
            result = await intent.classify_intent('Còn bản miễn phí thì sao?', history)
        self.assertEqual(result.source, 'web')
        self.assertIn('Obsidian', result.query)

    async def test_personal_and_social_do_not_call_search(self):
        with patch.object(chat, '_realtime_context', AsyncMock()) as search:
            for text in ('Bạn còn nhớ mình thích gì không?', 'Hôm nay mình buồn quá', 'Bạn thấy mùa này vui không?'):
                self.assertEqual(await chat._intent_context(text, 'alice'), text)
            search.assert_not_awaited()

    async def test_product_followup_fallback_searches_only_named_subject(self):
        with patch.object(intent, 'model_intent', AsyncMock(side_effect=TimeoutError)):
            result = await intent.classify_intent('Còn bản miễn phí thì sao?', [{'role': 'user', 'content': 'Mình đang thử ứng dụng Obsidian.'}])
        self.assertEqual(result.source, 'web')
        self.assertTrue(result.query.startswith('Obsidian'))

    async def test_model_transport_has_bounded_parameters_and_integer_keep_alive(self):
        import httpx
        from services import llm_service
        response = httpx.Response(200, request=httpx.Request('POST', 'http://local/api/chat'), json={'message': {'content': '{"kind": "social"}'}})
        with patch.object(llm_service, 'LLM_PROVIDER', 'ollama'), patch('httpx.AsyncClient') as factory:
            client = factory.return_value.__aenter__.return_value
            client.post = AsyncMock(return_value=response)
            await intent.model_intent('test', [])
            payload = client.post.call_args.kwargs['json']
            self.assertEqual(payload['keep_alive'], llm_service._keep_alive_value())
            self.assertFalse(payload['stream'])
            self.assertFalse(payload['think'])
            self.assertEqual(payload['options']['temperature'], 0)

    async def test_greeting_variants_skip_classifier_and_history(self):
        with patch.object(intent, 'model_intent', AsyncMock()) as model, patch.object(chat.memory_orchestrator, 'recall_history') as history:
            for text in ('hi', 'Hello!', 'Chào Huohuo', 'Xin chào bạn nhé 👋', 'chào cậu', 'hey'):
                self.assertEqual(await chat._intent_context(text, 'alice'), text)
            model.assert_not_awaited()
            history.assert_not_called()

    async def test_currency_request_variants_force_search_without_model(self):
        cases = [
            'huohuo cho biết tỷ lệ usd vnd hôm nay được không',
            'Huohuo cho mình biết tỷ giá USD/VND hôm nay được không?',
            'ty le usd vnd hom nay', 'USDVND hôm nay',
            '100 USD đổi sang VND bằng bao nhiêu', 'EUR/VND',
        ]
        with patch.object(intent, 'model_intent', AsyncMock()) as model:
            for text in cases:
                result = await intent.classify_intent(text)
                self.assertEqual((result.source, result.fresh), ('web', True), text)
            model.assert_not_awaited()
        self.assertFalse((await intent.classify_intent('Tỷ giá USD VND năm 2020')).fresh)
        self.assertNotEqual(intent.rule_intent('Mình thích thiết kế tờ USD và VND').source, 'web')

    async def test_screenshot_sentence_reaches_search_adapter(self):
        text = 'huohuo cho biết tỷ lệ usd vnd hôm nay được không'
        with patch.object(chat, 'search_web', AsyncMock(return_value={'ok': True, 'results': [{'title': 'Tỷ giá', 'url': 'https://example.com/rates', 'snippet': 'Nguồn tỷ giá thử nghiệm'}]})) as search, patch.object(intent, 'model_intent', AsyncMock()) as model:
            result = await chat._intent_context(text, 'alice')
        search.assert_awaited_once()
        self.assertIn('tỷ giá', search.call_args.args[0])
        self.assertIn('usd vnd', search.call_args.args[0])
        self.assertIn('TRA CỨU THỜI GIAN THỰC', result)
        model.assert_not_awaited()
