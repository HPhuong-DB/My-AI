"""Explicit integration check against the configured local DB and model.

Run from backend: venv/bin/python scripts/verify_local.py
Only creates and removes data for a new verification user; never uses default.
"""
import asyncio
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from core.database import get_db_connection
from main import app
from services.chat_service import get_recent_chat_history
from services.llm_service import _build_context_data
from api import chat


async def main():
    if "--debug" in sys.argv:
        original = chat._require_valid_result
        def inspect_result(result, **kwargs):
            try:
                original(result, **kwargs)
            except Exception:
                print("verification model output:", repr(result.response_text), result.metrics.as_dict(), flush=True)
                raise
        chat._require_valid_result = inspect_result
    user_id = "verify-" + uuid.uuid4().hex
    query = {"user_id": user_id}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local", timeout=120) as client:
        health = await client.get("/health")
        print("health:", json.dumps(health.json(), ensure_ascii=False), flush=True)
        assert health.status_code == 200, "Database and selected model must be available"

        async def send(text):
            response = await client.post("/api/chat/stream", json={"user_id": user_id, "text": text})
            events = {}
            for block in response.text.split("\n\n"):
                lines = block.splitlines()
                if len(lines) >= 2:
                    events[lines[0].removeprefix("event: ")] = json.loads(lines[1].removeprefix("data: "))
            assert "error" not in events, events.get("error")
            assert "complete" in events, "Missing complete event"
            print("chat:", events["complete"]["reply_vi"], flush=True)
            return events["complete"]["reply_vi"]

        async def memories():
            response = await client.get("/api/memories", params=query)
            assert response.status_code == 200, response.text
            return response.json()["memories"]

        try:
            await send("Mình tên là An. Mình thích trà. Mình học Python.")
            facts = await memories()
            assert {m["memory_type"] for m in facts} >= {"user_name", "preference", "goal"}
            # A new HTTP client represents reopening the UI; persisted history is fetched anew.
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local") as reopened:
                history = (await reopened.get("/api/chat/history", params=query)).json()["messages"]
            assert [m["role"] for m in history] == ["user", "assistant"], history
            print("reopened history: user + assistant persisted", flush=True)

            await send("Mình không còn thích trà nữa.")
            facts = await memories()
            assert "Người dùng thích trà" not in [m["fact"] for m in facts]
            assert "Người dùng không còn thích trà" in [m["fact"] for m in facts]

            name = next(m for m in facts if m["memory_type"] == "user_name")
            edited = await client.patch(f"/api/memories/{name['id']}", params=query, json={"fact": "Tên người dùng là Bình"})
            assert edited.status_code == 200, edited.text
            assert (await client.get("/api/profile", params=query)).json()["profile"]["username"] == "Bình"
            prompt, _ = await asyncio.to_thread(_build_context_data, "Mình tên gì?", user_id, "fast")
            assert "Tên người dùng là Bình" in prompt and "Tên người dùng là An" not in prompt
            recalled = await send("Mình tên gì và đang học gì?")
            assert "Bình" in recalled and "Python" in recalled, recalled

            removed = await client.delete(f"/api/memories/{name['id']}", params=query)
            assert removed.status_code == 200, removed.text
            prompt, profile = await asyncio.to_thread(_build_context_data, "Mình tên gì?", user_id, "fast")
            assert "Bình" not in prompt and profile["username"] == "Bạn", prompt
            assert get_recent_chat_history(user_id=user_id) == []
            assert len(get_recent_chat_history(user_id=user_id, for_context=False)) == 6
            forgotten = await send("Bạn có biết tên mình không?")
            assert "Bình" not in forgotten and ("chưa" in forgotten.casefold() or "không biết" in forgotten.casefold() or "không nhớ" in forgotten.casefold()), forgotten
            assert not any(m["memory_type"] == "user_name" for m in await memories())
            print("PASS: streaming, reload, negative preference, edit/delete name, context isolation", flush=True)
        finally:
            conn = get_db_connection()
            if conn:
                cursor = conn.cursor()
                for table in ("core_memories", "user_profiles", "user_mood_timeline", "chat_history", "memory_context_state", "proactive_preferences"):
                    cursor.execute(f"DELETE FROM {table} WHERE user_id = %s", (user_id,))
                conn.commit()
                cursor.close()
                conn.close()
                print("verification data removed", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
