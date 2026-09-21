"""Research pipeline: search, read public sources, summarize and save knowledge."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import httpx

from core.database import get_db_connection
from services.llm_service import summarize_research_sources
from services.memory_metadata import clamp_score, expiry_from_env, normalize_expiry
from services.web_search_service import search_web

DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "default")
MAX_SOURCE_CHARS = int(os.getenv("RESEARCH_MAX_SOURCE_CHARS", "16000"))
MAX_RESEARCH_SOURCES = int(os.getenv("RESEARCH_MAX_SOURCES", "3"))


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style", "noscript", "svg", "nav", "footer"}:
            self._ignored += 1

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "noscript", "svg", "nav", "footer"} and self._ignored:
            self._ignored -= 1

    def handle_data(self, data):
        if not self._ignored:
            value = " ".join(data.split())
            if value:
                self.parts.append(value)


def _safe_public_url(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    hostname = parsed.hostname.lower()
    if hostname in {"localhost", "localhost.localdomain"}:
        return False
    try:
        address = ipaddress.ip_address(hostname)
        return not (address.is_private or address.is_loopback or address.is_link_local)
    except ValueError:
        return True


async def _read_source(item: dict[str, Any]) -> dict[str, Any]:
    url = str(item.get("url") or "")
    result = {"title": item.get("title") or "", "url": url, "snippet": item.get("snippet") or "", "content": "", "ok": False}
    if not _safe_public_url(url):
        result["error"] = "unsafe_url"
        return result
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8, connect=3), follow_redirects=True, headers={"User-Agent": "HuohuoResearch/1.0"}) as client:
            response = await client.get(url)
            response.raise_for_status()
        parser = _TextExtractor()
        parser.feed(response.text)
        content = " ".join(parser.parts)
        result["content"] = content[:MAX_SOURCE_CHARS]
        result["ok"] = bool(result["content"])
    except Exception as exc:
        result["error"] = type(exc).__name__
    return result


def _ensure_knowledge_table(conn):
    if not conn:
        return
    from core.migrations import ensure_schema

    ensure_schema(conn)


def save_knowledge(
    user_id: str,
    query: str,
    title: str,
    summary: str,
    key_points: list[str],
    sources: list[dict[str, Any]],
    *,
    confidence: float = 0.75,
    importance: float = 0.60,
    source_type: str = "research",
    source_ref: str | None = None,
    expires_at: Any = None,
) -> dict[str, Any] | None:
    confidence = clamp_score(confidence, 0.75)
    importance = clamp_score(importance, 0.60)
    source_type = str(source_type or "research")[:50]
    source_ref = str(source_ref or query)[:255] or None
    expires_at = normalize_expiry(expires_at) if expires_at is not None else expiry_from_env("KNOWLEDGE_TTL_DAYS", 30)
    conn = get_db_connection()
    if not conn:
        return None
    cursor = None
    try:
        _ensure_knowledge_table(conn)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "INSERT INTO personal_knowledge "
            "(user_id, query_text, title, summary, key_points, sources, confidence, importance, source_type, source_ref, expires_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                user_id, query[:500], title[:255], summary,
                json.dumps(key_points, ensure_ascii=False), json.dumps(sources, ensure_ascii=False),
                confidence, importance, source_type, source_ref, expires_at,
            ),
        )
        knowledge_id = cursor.lastrowid
        conn.commit()
        return {
            "id": knowledge_id, "user_id": user_id, "query": query, "title": title,
            "summary": summary, "key_points": key_points, "sources": sources,
            "confidence": confidence, "importance": importance, "source_type": source_type,
            "source_ref": source_ref, "expires_at": expires_at,
        }
    except Exception as exc:
        print(f"Lỗi lưu knowledge: {exc}")
        return None
    finally:
        if conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def list_knowledge(user_id: str = DEFAULT_USER_ID, limit: int = 20) -> list[dict[str, Any]]:
    conn = get_db_connection()
    if not conn:
        return []
    cursor = None
    try:
        _ensure_knowledge_table(conn)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, user_id, query_text, title, summary, key_points, sources, confidence, importance, "
            "source_type, source_ref, expires_at, created_at, updated_at FROM personal_knowledge "
            "WHERE user_id = %s AND forgotten_at IS NULL "
            "AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP) "
            "ORDER BY updated_at DESC LIMIT %s",
            (user_id, max(1, min(int(limit), 50))),
        )
        rows = []
        for row in cursor.fetchall() or []:
            item = dict(row)
            for field in ("key_points", "sources"):
                try:
                    item[field] = json.loads(item.get(field) or "[]")
                except json.JSONDecodeError:
                    item[field] = []
            rows.append(item)
        return rows
    finally:
        if conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


async def run_research(query: str, user_id: str = DEFAULT_USER_ID, max_sources: int = MAX_RESEARCH_SOURCES, save: bool = True) -> dict[str, Any]:
    query = str(query or "").strip()
    if not query:
        return {"ok": False, "error": "query_required", "sources": []}
    search_result = await search_web(query, max_sources)
    if not search_result.get("ok"):
        return {"ok": False, "query": query, "error": search_result.get("error", "search_failed"), "sources": []}
    results = search_result.get("results", []) if search_result.get("ok") else []
    source_items = await asyncio.gather(*[_read_source(item) for item in results[:MAX_RESEARCH_SOURCES]])
    usable = [item for item in source_items if item.get("ok") or item.get("snippet")]
    if not usable:
        return {"ok": False, "query": query, "error": "no_sources", "sources": []}
    summary = await summarize_research_sources(query, usable)
    response = {"ok": True, "query": query, "summary": summary, "sources": [{key: item.get(key, "") for key in ("title", "url", "snippet", "ok")} for item in usable]}
    if save:
        from services.memory_orchestrator import memory_orchestrator

        saved = await asyncio.to_thread(
            memory_orchestrator.remember_knowledge,
            user_id,
            query,
            summary.get("title", query),
            summary.get("summary", ""),
            summary.get("key_points", []),
            response["sources"],
            confidence=min(0.95, 0.65 + 0.08 * len(usable)),
            importance=0.65,
            source_type="research",
            source_ref=query,
        )
        response["knowledge"] = saved
    return response
