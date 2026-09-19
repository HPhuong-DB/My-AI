"""Freshness is separate from retrieval time. Unknown dates are never called current."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from services.dialogue_context_service import normalize


class SearchContext(str):
    def __new__(cls, text, metadata):
        result = super().__new__(cls, text)
        result.search = metadata
        return result


def search_window(query):
    text = normalize(query)
    return 'day' if any(word in text for word in ('ty gia', 'ty le', 'thoi tiet', 'gia vang', 'gia xang', 'hom nay')) else 'month'


def dated_results(results, window, now=None):
    now = now or datetime.now(timezone.utc)
    kept, excluded = [], 0
    for source in results:
        value = source.get('published_at')
        date = None
        if isinstance(value, str):
            try:
                date = datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                try:
                    date = parsedate_to_datetime(value)
                except (ValueError, TypeError, OverflowError):
                    pass
        if date and date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        if window and date and not -86400 <= (now-date).total_seconds() <= (86400 if window == 'day' else 31*86400):
            excluded += 1
            continue
        kept.append({**source, 'date_status': 'dated' if date else 'unknown'})
    return kept, excluded
