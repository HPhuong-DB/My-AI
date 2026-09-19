import json
from datetime import datetime
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from api import chat
from agent.tooling import ToolDefinition
from schemas.message import ChatRequest
from services import file_tool_service, web_search_service
from services.llm_service import LLMResult, LLMMetrics
from services.tool_service import tool_executor, tool_registry


class Phase4IntegrationTests(unittest.IsolatedAsyncioTestCase):
    def test_visible_reply_removes_web_links(self):
        reply = chat._clean_visible_reply(
            "Theo [Investing](https://example.com/rate), 1 USD khoảng 25.907 VND."
        )
        self.assertEqual(reply, "Theo Investing, 1 USD khoảng 25.907 VND.")

    def test_realtime_markers_are_detected(self):
        self.assertTrue(chat.requires_realtime_search("1 USD bằng bao nhiêu tiền Việt hiện tại?"))
        self.assertTrue(chat.requires_realtime_search("Thời tiết hôm nay ở Hà Nội"))
        self.assertFalse(chat.requires_realtime_search("Bạn kể mình nghe một câu chuyện đi"))
        self.assertFalse(chat.requires_realtime_search("Hôm nay mình sửa được lỗi code rồi!"))

    async def test_realtime_context_requires_web_sources(self):
        with patch.object(
            chat,
            "search_web",
            new=AsyncMock(return_value={
                "ok": True,
                "results": [{"title": "Tỷ giá hôm nay", "url": "https://example.com/rate", "snippet": "1 USD = ..."}],
            }),
        ) as search_mock:
            context = await chat._realtime_context("1 USD bằng bao nhiêu tiền Việt hiện tại?")

        search_mock.assert_awaited_once()
        self.assertIn("TRA CỨU THỜI GIAN THỰC", context)
        self.assertIn("https://example.com/rate", context)

    def test_standard_registry_contains_phase4_tools(self):
        names = {definition.name for definition in tool_registry.definitions()}
        expected = {
            "create_note", "list_notes", "get_note", "update_note", "archive_note",
            "create_task", "list_tasks", "set_reminder", "read_file", "write_file", "web_search",
        }
        self.assertTrue(expected <= names)
        self.assertIn("self_learn", names)
        self.assertTrue(tool_registry.get("write_file").requires_confirmation)

    def test_tool_api_paths_are_exposed_in_openapi(self):
        from main import app

        paths = app.openapi()["paths"]
        self.assertIn("/api/tools/execute", paths)
        self.assertIn("/api/tools/audit", paths)
        self.assertIn("/api/tools/notes", paths)
        self.assertIn("/api/self-learning/learn", paths)
        self.assertIn("/api/mood/summary", paths)
        self.assertIn("/api/relationship", paths)
        self.assertIn("/api/personality", paths)

    async def test_llm_tool_call_is_executed_then_summarized(self):
        initial = LLMResult(
            response_text=json.dumps({
                "reply_vi": "",
                "motion": "",
                "expression": "",
                "tool_calls": [{"name": "create_note", "arguments": {"title": "A", "content": "B"}}],
            }),
            metrics=LLMMetrics(total_llm_ms=10),
        )
        final = LLMResult(
            response_text=json.dumps({"reply_vi": "Đã lưu rồi.", "motion": "", "expression": "", "tool_calls": []}),
            metrics=LLMMetrics(total_llm_ms=20),
        )
        request = ChatRequest(text="Lưu giúp mình A: B", user_id="user-1")

        with patch.object(chat, "execute_tool_call", new=AsyncMock(return_value={"ok": True, "note": {"id": 1, "created_at": datetime(2026, 9, 10)}})) as execute_mock:
            with patch.object(chat, "generate_huohuo_result", new=AsyncMock(return_value=final)) as generate_mock:
                result = await chat._resolve_tool_calls(request, initial)

        self.assertEqual(result.response_text, final.response_text)
        execute_mock.assert_awaited_once()
        generate_mock.assert_awaited_once()
        self.assertIn("id", generate_mock.await_args.args[0])

    async def test_empty_web_query_does_not_make_network_request(self):
        result = await web_search_service.search_web("")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "query_required")

    def test_file_tool_is_sandboxed_per_user(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(file_tool_service, "FILE_ROOT", file_tool_service.Path(directory)):
                written = file_tool_service.write_file("user-1", "notes/a.md", "hello")
                read = file_tool_service.read_file("user-1", "notes/a.md")
                self.assertTrue(written["ok"])
                self.assertEqual(read["content"], "hello")
                with self.assertRaises(ValueError):
                    file_tool_service.read_file("user-1", "../secret.md")


if __name__ == "__main__":
    unittest.main()
