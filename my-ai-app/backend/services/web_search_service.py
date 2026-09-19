"""Validated search results with a bounded retry budget; no silent provider switch."""
from __future__ import annotations
import asyncio
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit
import httpx


def normalize_results(items, limit):
    results, seen = [], set()
    for item in items:
        if not isinstance(item, dict):
            continue
        url = item.get('url')
        if not isinstance(url, str):
            continue
        try:
            parsed = urlsplit(url.strip())
            if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
                continue
            url = urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ''))
        except ValueError:
            continue
        if url in seen:
            continue
        snippet = item.get('content') or item.get('snippet') or ''
        if not isinstance(snippet, str) or not snippet.strip():
            continue
        seen.add(url)
        clean = lambda text: re.sub(r'\s+', ' ', re.sub(r'<[^>]*>', ' ', str(text))).strip()
        date = item.get('publishedDate') or item.get('pubdate')
        results.append({'title': clean(item.get('title') or '')[:200], 'url': url,
                        'snippet': clean(snippet)[:700], 'published_at': date if isinstance(date, str) else None})
        if len(results) >= limit:
            break
    return results


async def search_web(query: str, max_results: int = 5, *, time_range: str | None = None) -> dict:
    query = str(query or '').strip()[:1000]
    base = {'query': query, 'results': [], 'requested_time_range': time_range,
            'retrieved_at': datetime.now(timezone.utc).isoformat(), 'attempts': 0}
    def failure(error):
        return {**base, 'ok': False, 'error': error}
    if not query:
        return failure('query_required')
    try:
        limit = max(1, min(int(max_results), 8))
    except (TypeError, ValueError, OverflowError):
        return failure('invalid_max_results')
    if time_range not in {None, 'day', 'week', 'month', 'year'}:
        return failure('invalid_time_range')
    provider = os.getenv('WEB_SEARCH_PROVIDER').strip().lower()
    if provider != 'searxng':
        return failure('unsupported_provider')
    endpoint = os.getenv('WEB_SEARCH_URL')
    params = {'q': query, 'format': 'json'}
    if time_range:
        params['time_range'] = time_range
    try:
        async with asyncio.timeout(10):
            async with httpx.AsyncClient(timeout=httpx.Timeout(8, connect=3), follow_redirects=True) as client:
                for attempt in range(2):
                    base['attempts'] = attempt + 1
                    try:
                        response = await client.get(endpoint, params=params)
                        response.raise_for_status()
                        break
                    except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                        if attempt or (status is not None and status not in {429, 502, 503, 504}):
                            raise
                        await asyncio.sleep(.15)
                if len(response.content) > 2_000_000:
                    return failure('response_too_large')
                payload = response.json()
        if not isinstance(payload, dict):
            return failure('invalid_response')
        items = payload.get('results')
        if not isinstance(items, list):
            return failure('invalid_response')
        results = normalize_results(items, limit)
        degraded = bool(payload.get('unresponsive_engines'))
        return {**base, 'ok': True, 'results': results, 'status': 'degraded' if degraded else ('ok' if results else 'empty'), 'provider': 'searxng'}
    except (TimeoutError, httpx.TimeoutException):
        return failure('timeout')
    except httpx.HTTPStatusError as exc:
        return failure(f'http_{exc.response.status_code}')
    except httpx.TransportError:
        return failure('connection_error')
    except (ValueError, TypeError):
        return failure('invalid_response')