import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from api import chat
from core.database import DatabaseUnavailable
from main import app
from services import health_service
from services.llm_service import LLMMetrics, LLMStreamChunk


class HealthTests(unittest.IsolatedAsyncioTestCase):
    async def probe(self, status, body):
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(status, json=body)))
        with patch.object(health_service.llm, "LLM_PROVIDER", "ollama"), patch.object(health_service.httpx, "AsyncClient", return_value=client):
            return await health_service.check_llm()

    async def test_running_server_without_selected_model_is_not_ready(self):
        result = await self.probe(404, {"error": "model not found"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "model_not_found")

    async def test_selected_model_metadata_is_ready(self):
        self.assertTrue((await self.probe(200, {"model_info": {"architecture": "gemma3"}}))["ok"])

    async def test_unconfigured_gemini_is_not_ready(self):
        with patch.object(health_service.llm, "LLM_PROVIDER", "gemini"), patch.object(health_service.llm, "client", None):
            result = await health_service.check_llm()
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "not_configured")

    async def test_health_failure_returns_503(self):
        with patch.object(health_service, "check_db_connection", return_value=True), patch.object(health_service, "check_llm", new=AsyncMock(return_value={"ok": False})):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/health")
            self.assertEqual(response.status_code, 503)
            self.assertFalse(response.json()["checks"]["llm"])


class ChatReliabilityTests(unittest.IsolatedAsyncioTestCase):
    async def stream(self, chunks, persist=None):
        async def generate(*args, **kwargs):
            for chunk in chunks:
                yield chunk
        persist = persist or AsyncMock()
        with patch.object(chat, "_prepare_chat", new=AsyncMock()), patch.object(chat, "_read_due_reminders", new=AsyncMock(return_value=[])), patch.object(chat, "stream_huohuo_response", generate), patch.object(chat, "_persist_response", persist):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/chat/stream", json={"text": "Chào bạn"})
        return response.text, persist

    async def test_complete_means_reply_was_persisted(self):
        raw = json.dumps({"reply_vi": "Xin chào", "motion": "", "expression": ""})
        body, persisted = await self.stream([LLMStreamChunk(raw, done=True, metrics=LLMMetrics())])
        self.assertIn("event: complete", body)
        persisted.assert_awaited_once()

    async def test_fallback_is_error_and_not_saved_as_assistant_reply(self):
        body, persisted = await self.stream([LLMStreamChunk('{"reply_vi":"fallback"}', done=True, metrics=LLMMetrics(fallback_used=True))])
        self.assertIn("event: error", body)
        self.assertNotIn("event: complete", body)
        persisted.assert_not_awaited()

    async def test_invalid_json_is_not_success(self):
        body, persisted = await self.stream([LLMStreamChunk('{"reply_vi":"unfinished', done=True)])
        self.assertIn("event: error", body)
        persisted.assert_not_awaited()

    async def test_empty_json_is_not_success(self):
        body, persisted = await self.stream([LLMStreamChunk('{}', done=True)])
        self.assertIn("event: error", body)
        persisted.assert_not_awaited()

    async def test_eof_without_model_completion_is_an_error(self):
        body, persisted = await self.stream([LLMStreamChunk('{"reply_vi":"partial"}')])
        self.assertIn("event: error", body)
        self.assertNotIn("event: complete", body)
        persisted.assert_not_awaited()

    async def test_database_write_failure_is_visible(self):
        body, _ = await self.stream([LLMStreamChunk('{"reply_vi":"Xin chào"}', done=True)], AsyncMock(side_effect=DatabaseUnavailable()))
        self.assertIn("MySQL", body)
        self.assertNotIn("event: complete", body)

    async def test_memory_changes_are_committed_before_user_history(self):
        order = []
        with patch.object(chat, "observe_message", side_effect=lambda *a: order.append("boundary")), patch.object(chat, "save_memory_from_conversation", side_effect=lambda *a, **kw: order.append("memory")), patch.object(chat, "save_chat_message", side_effect=lambda *a, **kw: order.append("history")), patch.object(chat, "trigger_due_reminder_notification", return_value={}):
            from schemas.message import ChatRequest
            task = await chat._prepare_chat(ChatRequest(text="Mình không còn thích trà"))
            await task
        self.assertEqual(order, ["boundary", "memory", "history"])


if __name__ == "__main__":
    unittest.main()
