"""Read-only local Ollama intent check; no DB writes, no web search."""
import asyncio
import json
import sys
from pathlib import Path
from time import perf_counter
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.intent_service import classify_intent

async def main():
    rows = []
    for text, history in [
        ('Hiện tại Đấu trường chân lý đang là mùa bao nhiêu', []),
        ('Bạn thấy mùa này vui không?', []),
        ('Hôm nay mình buồn quá', []),
        ('Còn bản miễn phí thì sao?', [{'role': 'user', 'content': 'Mình đang thử ứng dụng Obsidian.'}]),
        ('Còn mùa hiện tại thì sao?', [{'role': 'user', 'content': 'TFT là gì?'}, {'role': 'assistant', 'content': 'TFT mùa 17.'}]),
        ('Còn cái đó thì sao?', []),
    ]:
        started = perf_counter()
        result = await classify_intent(text, history)
        row = dict(text=text, **asdict(result), elapsed_ms=round((perf_counter()-started)*1000))
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    Path('evaluations/intent-verification.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2)+'\n')

if __name__ == '__main__':
    asyncio.run(main())
