import json
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
import httpx
from fastapi import FastAPI
from api import chat
from services import web_search_service as search
from services.search_context_service import dated_results
from services.dialogue_context_service import build_dialogue_context
from services.dialogue_policy_service import grounded_reply
from services.llm_service import LLMResult, LLMStreamChunk, LLMMetrics


class SearchStabilityTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, responses, **kwargs):
        self.calls = []
        async def handler(request):
            self.calls.append(request)
            value = responses[min(len(self.calls)-1, len(responses)-1)]
            if isinstance(value, Exception):
                raise value
            status, payload = value
            return httpx.Response(status, json=payload)
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch.dict('os.environ', {'WEB_SEARCH_PROVIDER': 'searxng', 'WEB_SEARCH_URL': 'http://local/search'}), patch.object(search.httpx, 'AsyncClient', return_value=client):
            return await search.search_web('TFT', **kwargs)

    async def test_transient_503_retries_once_and_recovers(self):
        result = await self.request([(503, {}), (200, {'results': [{'url': 'https://example.com/a', 'content': 'Evidence'}]})])
        self.assertTrue(result['ok'])
        self.assertEqual(result['attempts'], 2)

    async def test_persistent_timeout_stops_after_two_attempts(self):
        result = await self.request([httpx.ReadTimeout('timeout')])
        self.assertEqual(result['error'], 'timeout')
        self.assertEqual(len(self.calls), 2)

    async def test_403_json_disabled_is_not_retried(self):
        result = await self.request([(403, {})])
        self.assertEqual(result['error'], 'http_403')
        self.assertEqual(len(self.calls), 1)

    async def test_invalid_shapes_do_not_break_chat(self):
        for body in ([], {'results': {}}, {'results': None}):
            self.assertEqual((await self.request([(200, body)]))['error'], 'invalid_response')

    async def test_empty_and_partial_engine_failure_are_distinct(self):
        self.assertEqual((await self.request([(200, {'results': []})]))['status'], 'empty')
        result = await self.request([(200, {'results': [{'url': 'https://example.com', 'content': 'Evidence'}], 'unresponsive_engines': [['engine', 'CAPTCHA']]})])
        self.assertEqual(result['status'], 'degraded')
        self.assertEqual(len(result['results']), 1)

    async def test_deduplicate_and_reject_unusable_results(self):
        items = [{'url': 'javascript:alert(1)', 'content': 'bad'}, {'url': 'https://user:password@example.com', 'content': 'bad'}, {'url': 'https://example.com/empty'}, {'url': 'https://example.com/a#one', 'content': '<b>Evidence</b>'}, {'url': 'https://example.com/a#two', 'content': 'duplicate'}]
        result = await self.request([(200, {'results': items})])
        self.assertEqual(len(result['results']), 1)
        self.assertEqual(result['results'][0]['snippet'], 'Evidence')

    async def test_bad_configuration_and_limit_are_explicit(self):
        self.assertEqual((await search.search_web('x', 'bad'))['error'], 'invalid_max_results')
        with patch.dict('os.environ', {'WEB_SEARCH_PROVIDER': 'typo'}):
            self.assertEqual((await search.search_web('x'))['error'], 'unsupported_provider')

    def test_date_filter_does_not_claim_unknown_date_is_fresh(self):
        now = datetime(2026, 9, 11, 12, tzinfo=timezone.utc)
        sources = [{'published_at': '2020-01-01'}, {'published_at': '2026-09-11'}, {'published_at': None}, {'published_at': 'invalid'}, {'published_at': '2030-01-01'}]
        kept, excluded = dated_results(sources, 'day', now)
        self.assertEqual(excluded, 2)
        self.assertEqual([s['date_status'] for s in kept], ['dated', 'unknown', 'unknown'])
        self.assertEqual(len(dated_results(sources, None, now)[0]), 5)

    async def test_only_old_sources_yield_deterministic_uncertainty(self):
        with patch.object(chat, 'search_web', AsyncMock(return_value={'ok': True, 'results': [{'url': 'https://example.com', 'snippet': '1 USD = old value', 'published_at': '2000-01-01'}]})):
            result = await chat._intent_context('Tỷ giá USD VND hôm nay bao nhiêu?', 'test')
        self.assertEqual(result.search['status'], 'outdated')
        self.assertNotIn('old value', result)
        self.assertEqual(grounded_reply(build_dialogue_context(result, [], [], None))[1], 'unverified_realtime')

    async def test_current_currency_uses_day_and_valid_vietnam_timezone(self):
        with patch.object(chat, 'search_web', AsyncMock(return_value={'ok': True, 'results': []})) as call:
            await chat._intent_context('huohuo cho biết tỷ lệ usd vnd hôm nay được không', 'test')
        self.assertEqual(call.call_args.kwargs['time_range'], 'day')

    def test_lookup_detection_is_shared_and_respects_no_search(self):
        for text in ('Cho mình biết thời tiết hôm nay ở thành phố Hà Nội được không', 'huohuo cho biết tỷ lệ usd vnd hôm nay được không', 'TFT hiện tại mùa bao nhiêu?'):
            self.assertTrue(chat.requires_realtime_search(text))
        for text in ('Đừng tra web, giải thích tỷ giá là gì', 'Mình vừa đọc câu “tra cứu tỷ giá USD VND hôm nay”', 'Hôm nay mình mệt', 'hello'):
            self.assertFalse(chat.requires_realtime_search(text))

    async def test_both_api_paths_return_search_status_and_preserve_no_url_speech(self):
        app = FastAPI()
        app.include_router(chat.router)
        raw = json.dumps({'reply_vi': 'Mình chưa xác minh được số liệu.', 'motion': '', 'expression': ''})
        async def stream(*args, **kwargs):
            yield LLMStreamChunk(raw, done=True, metrics=LLMMetrics())
        with patch.object(chat, '_prepare_chat', AsyncMock()), patch.object(chat, '_persist_response', AsyncMock()), patch.object(chat, '_read_due_reminders', AsyncMock(return_value=[])), patch.object(chat, '_publish_response', AsyncMock()), patch.object(chat, 'search_web', AsyncMock(return_value={'ok': False, 'error': 'timeout', 'results': []})), patch.object(chat, 'generate_huohuo_result', AsyncMock(return_value=LLMResult(raw, LLMMetrics()))), patch.object(chat, 'stream_huohuo_response', stream):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://local') as client:
                body = {'text': 'TFT hiện tại mùa bao nhiêu?', 'user_id': 'test'}
                normal = (await client.post('/chat', json=body)).json()
                streamed = (await client.post('/chat/stream', json=body)).text
        self.assertEqual(normal['search']['status'], 'unavailable')
        self.assertIn('"status": "unavailable"', streamed)
        self.assertIn('routing_ms', normal['timing'])
