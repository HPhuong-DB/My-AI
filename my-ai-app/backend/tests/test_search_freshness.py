import unittest
from unittest.mock import AsyncMock, patch
import httpx
from api import chat
from services import web_search_service as search


class SearchFreshnessTests(unittest.IsolatedAsyncioTestCase):
    def test_current_season_question_triggers_search(self):
        for question in ('Hiện tại Đấu trường chân lý đang là mùa bao nhiêu', 'TFT bây giờ mùa nào?', 'hien tai dau truong chan ly mua bao nhieu', 'Phiên bản hiện tại là gì?'):
            self.assertTrue(chat.requires_realtime_search(question), question)
        for text in ('Hôm nay mình sửa được lỗi code rồi!', 'Hiện tại mình hơi buồn', 'Mình thích eurobeat'):
            self.assertFalse(chat.requires_realtime_search(text), text)

    async def test_current_query_passes_recency_and_preserves_source_date(self):
        with patch.object(chat, 'search_web', AsyncMock(return_value={'ok': True, 'results': [{'title': 'TFT', 'url': 'https://example.com/tft', 'snippet': 'Season', 'published_at': '2026-09-10'}]})) as call:
            result = await chat._realtime_context('Hiện tại TFT mùa bao nhiêu?')
        self.assertEqual(call.call_args.kwargs['time_range'], 'month')
        self.assertIn('tính đến', call.call_args.args[0])
        self.assertIn('2026-09-10', result)
        self.assertIn('https://example.com/tft', result)
        self.assertIn('không bảo đảm', result)

    async def test_adapter_passes_time_range_and_keeps_publication_date(self):
        response = httpx.Response(200, request=httpx.Request('GET', 'http://local/search'), json={'results': [{'url': 'https://example.com', 'publishedDate': '2020-01-01', 'content': 'Old result'}]})
        with patch.dict('os.environ', {'WEB_SEARCH_PROVIDER': 'searxng'}), patch.object(search.httpx, 'AsyncClient') as factory:
            client = factory.return_value.__aenter__.return_value
            client.get = AsyncMock(return_value=response)
            result = await search.search_web('TFT', time_range='month')
            self.assertEqual(client.get.call_args.kwargs['params']['time_range'], 'month')
        self.assertEqual(result['results'][0]['published_at'], '2020-01-01')
        self.assertIn('retrieved_at', result)

    async def test_failed_search_marks_no_evidence(self):
        with patch.object(chat, 'search_web', AsyncMock(return_value={'ok': False, 'results': []})):
            result = await chat._realtime_context('Hiện tại TFT mùa bao nhiêu?')
        self.assertIn('KHÔNG CÓ NGUỒN', result)
