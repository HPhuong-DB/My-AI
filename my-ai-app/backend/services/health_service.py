"""Bounded, read-only probes; no token generation or model downloads."""
import asyncio

import httpx

from core.database import check_db_connection
from services import llm_service as llm


async def check_llm() -> dict:
    model = llm.OLLAMA_MODEL if llm.LLM_PROVIDER == "ollama" else llm.MODEL_NAME
    result = {"ok": False, "provider": llm.LLM_PROVIDER, "model": model}
    try:
        async with asyncio.timeout(5):
            if llm.LLM_PROVIDER == "ollama":
                async with httpx.AsyncClient(timeout=4) as client:
                    response = await client.post(f"{llm.OLLAMA_URL}/api/show", json={"model": model})
                if response.status_code == 404:
                    return {**result, "error": "model_not_found"}
                response.raise_for_status()
                if not isinstance(response.json(), dict) or not response.json().get("model_info"):
                    return {**result, "error": "invalid_response"}
            elif llm.LLM_PROVIDER == "gemini":
                if llm.client is None:
                    return {**result, "error": "not_configured"}
                await llm.client.aio.models.get(model=model)
            else:
                return {**result, "error": "unsupported_provider"}
        return {**result, "ok": True, "probe": "model_metadata"}
    except (TimeoutError, httpx.TimeoutException):
        return {**result, "error": "timeout"}
    except Exception:
        return {**result, "error": "unavailable"}


async def check_health() -> dict:
    async def database():
        try:
            return await asyncio.wait_for(asyncio.to_thread(check_db_connection), 6)
        except Exception:
            return False

    db_ok, model = await asyncio.gather(database(), check_llm())
    return {
        "status": "ok" if db_ok and model["ok"] else "degraded",
        "checks": {"database": db_ok, "llm": model["ok"]},
        "llm": model,
    }
