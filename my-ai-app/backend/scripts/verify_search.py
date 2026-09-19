"""Read-only real SearXNG routing check. No user DB/history or LLM calls."""
import asyncio
import json
import sys
from pathlib import Path
from time import perf_counter
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.chat import _intent_context

async def main():
    rows = []
    for query in ('huohuo cho biết tỷ lệ usd vnd hôm nay được không', 'Hiện tại Đấu trường chân lý đang là mùa bao nhiêu'):
        started = perf_counter()
        result = await _intent_context(query, 'search-readonly-verification')
        metadata = getattr(result, 'search', None)
        assert metadata is not None, 'Expected search route'
        row = {'query': query, 'elapsed_ms': round((perf_counter()-started)*1000), 'search': metadata, 'context': str(result)}
        rows.append(row)
        print(json.dumps({key: value for key, value in row.items() if key != 'context'}, ensure_ascii=False), flush=True)
    Path('evaluations/search-verification.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2)+'\n')

if __name__ == '__main__':
    asyncio.run(main())
