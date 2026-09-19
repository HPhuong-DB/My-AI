import unittest
import asyncio
import json
from time import perf_counter
from unittest.mock import AsyncMock, patch

import httpx

from api.chat import _reply_prefix
from services import llm_service
from services.llm_service import LLMMetrics, _ollama_options, resolve_response_mode


class LLMPerformanceTests(unittest.TestCase):
    def test_fast_and_deep_generation_limits_are_separate(self):
        fast = _ollama_options("fast")
        deep = _ollama_options("deep")

        self.assertLess(fast["num_predict"], deep["num_predict"])
        self.assertEqual(fast["num_ctx"], deep["num_ctx"])

    def test_fast_limit_can_be_lowered_and_prompt_keeps_safety_contract(self):
        with patch.object(llm_service, "OLLAMA_NUM_PREDICT_FAST", 64):
            self.assertEqual(_ollama_options("fast")["num_predict"], 64)
        prompt = llm_service._build_system_prompt(None, "fast")
        self.assertLess(len(prompt), len(llm_service._build_system_prompt(None, "deep")))
        self.assertIn("communication_style", prompt)
        self.assertIn("tool_calls", prompt)

    def test_fast_context_budget_keeps_deep_budget_available(self):
        with patch.object(llm_service, "get_recent_chat_history", return_value=[]), \
             patch.object(llm_service, "get_recent_memories", return_value=[]), \
             patch.object(llm_service, "get_user_profile", return_value={}), \
             patch.object(llm_service, "build_dialogue_context", return_value="") as build:
            llm_service._build_context_data("hello", "alice", "fast")
            self.assertEqual(build.call_args.kwargs["max_chars"], llm_service.LLM_MAX_CONTEXT_CHARS_FAST)
            llm_service._build_context_data("hello", "alice", "deep")
            self.assertEqual(build.call_args.kwargs["max_chars"], llm_service.LLM_MAX_CONTEXT_CHARS)

    def test_partial_json_reply_can_be_read_while_streaming(self):
        self.assertEqual(_reply_prefix('{"reply_vi":"Xin chào'), "Xin chào")
        self.assertEqual(_reply_prefix('{"reply_vi":"Xin chào","motion"'), "Xin chào")

    def test_response_mode_keeps_short_messages_fast(self):
        self.assertEqual(resolve_response_mode("Chào bạn"), "fast")
        self.assertEqual(resolve_response_mode("Hãy phân tích kế hoạch này"), "deep")

    def test_metrics_are_serializable(self):
        metrics = LLMMetrics(
            first_token_ms=125.4,
            total_llm_ms=843.2,
            output_tokens=12,
            tokens_per_second=14.23,
        )
        self.assertEqual(metrics.as_dict()["output_tokens"], 12)
        self.assertEqual(metrics.as_dict()["first_token_ms"], 125.4)


class OllamaTimeoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_still_yields_content_and_final_metrics(self):
        async def response(request):
            self.assertFalse(json.loads(request.content)["think"])
            return httpx.Response(200, text=(
                '{"message":{"content":"hello"},"done":false}\n'
                '{"done":true,"eval_count":1,"eval_duration":1000000000}\n'
            ))

        client_class = httpx.AsyncClient
        transport = httpx.MockTransport(response)
        with patch.object(llm_service.httpx, "AsyncClient", side_effect=lambda **kwargs: client_class(transport=transport, **kwargs)):
            chunks = [chunk async for chunk in llm_service._stream_ollama("hello", "", "fast", perf_counter())]

        self.assertEqual(chunks[0].content, "hello")
        self.assertTrue(chunks[-1].done)
        self.assertFalse(chunks[-1].metrics.timed_out)

    async def test_total_timeout_includes_waiting_for_response_headers(self):
        async def slow_headers(request):
            await asyncio.sleep(0.05)
            return httpx.Response(200, text='{"done":true}\n')

        client_class = httpx.AsyncClient
        transport = httpx.MockTransport(slow_headers)
        with patch.object(llm_service.httpx, "AsyncClient", side_effect=lambda **kwargs: client_class(transport=transport, **kwargs)), \
             patch.object(llm_service, "OLLAMA_FIRST_TOKEN_TIMEOUT_SECONDS", 1), \
             patch.object(llm_service, "OLLAMA_TOTAL_TIMEOUT_SECONDS", 0.02):
            with self.assertRaises(TimeoutError):
                async for _ in llm_service._stream_ollama("hello", "", "fast", perf_counter()):
                    pass

    async def test_http_read_timeout_is_reported_as_timeout_fallback(self):
        async def fail_stream(*args):
            raise httpx.ReadTimeout("Ollama response headers timed out")
            yield

        with patch.object(llm_service, "_prepare_prompt", AsyncMock(return_value=("hello", "", "fast"))), \
             patch.object(llm_service, "grounded_reply", return_value=None), \
             patch.object(llm_service, "_stream_ollama", fail_stream), \
             patch.object(llm_service, "LLM_PROVIDER", "ollama"):
            chunks = [chunk async for chunk in llm_service.stream_huohuo_response("hello")]

        self.assertTrue(chunks[-1].done)
        self.assertTrue(chunks[-1].metrics.timed_out)
        self.assertTrue(chunks[-1].metrics.fallback_used)


if __name__ == "__main__":
    unittest.main()
