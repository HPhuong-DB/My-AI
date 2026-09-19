"""Local MySQL integration check; only mutates a disposable user, no LLM calls."""
import asyncio
from datetime import timedelta
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from fastapi import FastAPI
from api.proactive import router
from agent.event_bus import EventBus
from agent.proactive_scheduler import ProactiveScheduler
from agent.state_manager import StateManager
from services import proactive_service as context
from services.memory_service import save_memory
from services.chat_service import get_recent_chat_history, save_chat_message


async def main():
    user = 'verify-proactive-' + uuid.uuid4().hex
    app = FastAPI()
    app.include_router(router, prefix='/api')
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://local') as client:
            url = '/api/proactive/preferences'
            query = {'user_id': user}
            assert (await client.get(url, params=query)).json()['enabled']
            assert (await client.patch(url, params=query, json={'enabled': 'false'})).status_code == 422
            assert not (await client.patch(url, params=query, json={'enabled': False})).json()['enabled']
            context.observe_message(user, 'Mình đang học Rust.')
            assert not context.preferences(user)['enabled']
            context.observe_message(user, 'Bạn chủ động bắt chuyện lại nhé.')
            assert context.preferences(user)['enabled']
            context.observe_message(user, 'Mình đi ngủ.')
            assert context.preferences(user)['resume_on_message']
            context.observe_message(user, 'Mình quay lại rồi.')
            assert context.preferences(user)['enabled']
            context.observe_message(user, 'Mình muốn yên lặng 10 phút.')
            settings = (await client.get(url, params=query)).json()
            assert not settings['enabled'] and settings['quiet_until'].endswith(('+00:00', 'Z')), settings
            with context.connection() as (conn, cursor):
                cursor.execute('UPDATE proactive_preferences SET quiet_until=%s WHERE user_id=%s', (context.utcnow()-timedelta(seconds=1), user))
                conn.commit()
            assert (await client.get(url, params=query)).json()['enabled']
            context.set_enabled(user, True)
            print('PASS: API validation, persistent quiet/resume, away/return, timed quiet UTC/expiry', flush=True)

        save_memory('goal', 'Người dùng đang học Rust', user, strict=True)
        save_chat_message('user', 'Mình đang học Rust.', user, strict=True)
        with context.connection() as (conn, cursor):
            cursor.execute('UPDATE proactive_preferences SET last_user_at=%s WHERE user_id=%s', (context.utcnow()-timedelta(minutes=10), user))
            conn.commit()
        scheduler = ProactiveScheduler(EventBus(), StateManager())
        scheduler.presence.update('verification-tab', user, dict(visible=True, busy=False, typing=False, reading=False, local_hour=12))
        events = await scheduler.tick()
        assert len(events) == 1 and events[0].user_id == user and 'Rust' in events[0].payload['message'], events
        assert [item['role'] for item in get_recent_chat_history(user_id=user, strict=True)] == ['user']
        assert await scheduler.acknowledge(user, events[0].event_id)
        assert not await scheduler.acknowledge(user, events[0].event_id)
        history = get_recent_chat_history(user_id=user, strict=True)
        assert history[-1]['content'] == events[0].payload['message'] and history[-1]['role'] == 'assistant'
        assert await scheduler.tick() == []
        print('PASS: real scoped memory/history, contextual offer, display ACK persisted once, no unanswered repeat', flush=True)
    finally:
        with context.connection() as (conn, cursor):
            for table in ('core_memories', 'chat_history', 'proactive_preferences'):
                cursor.execute(f'DELETE FROM {table} WHERE user_id=%s', (user,))
            conn.commit()
        print('Disposable verification data removed.', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
