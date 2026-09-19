import unittest
from unittest.mock import AsyncMock, patch

from services import research_service


class ResearchServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_public_url_guard(self):
        self.assertTrue(research_service._safe_public_url("https://example.com/article"))
        self.assertFalse(research_service._safe_public_url("http://127.0.0.1:8000/private"))
        self.assertFalse(research_service._safe_public_url("file:///etc/passwd"))

    def test_html_extractor_removes_script_and_navigation(self):
        parser = research_service._TextExtractor()
        parser.feed("<nav>menu</nav><main>Hello <b>world</b></main><script>secret()</script>")
        self.assertEqual(" ".join(parser.parts), "Hello world")

    async def test_research_pipeline_searches_reads_summarizes_and_saves(self):
        with patch.object(research_service, "search_web", new=AsyncMock(return_value={"ok": True, "results": [{"title": "Source", "url": "https://example.com", "snippet": "Short"}]})):
            with patch.object(research_service, "_read_source", new=AsyncMock(return_value={"title": "Source", "url": "https://example.com", "snippet": "Short", "content": "Long source", "ok": True})):
                with patch.object(research_service, "summarize_research_sources", new=AsyncMock(return_value={"title": "Topic", "summary": "Summary", "key_points": ["Point"]})):
                    with patch.object(research_service, "save_knowledge", return_value={"id": 1}) as save_mock:
                        result = await research_service.run_research("Topic", "user-1")

        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["title"], "Topic")
        self.assertEqual(result["knowledge"]["id"], 1)
        save_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
