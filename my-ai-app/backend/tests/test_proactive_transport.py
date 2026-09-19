import unittest
from threading import Event
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient
from agent.event_bus import EventBus
from agent.presence import Presence
from api import websocket, proactive


class ProactiveTransportTests(unittest.TestCase):
    def test_websocket_presence_is_scoped_validated_and_removed_on_disconnect(self):
        app = FastAPI()
        app.include_router(websocket.router)
        presence = Presence()
        finished = Event()
        async def transport(scope, receive, send):
            try:
                await app(scope, receive, send)
            finally:
                finished.set()
        with patch.object(websocket, 'output_bus', EventBus()), patch.object(websocket, 'proactive_scheduler') as scheduler:
            scheduler.presence = presence
            scheduler.acknowledge = AsyncMock(return_value=True)
            with TestClient(transport).websocket_connect('/ws?user_id=alice') as ws:
                self.assertEqual(ws.receive_json()['user_id'], 'alice')
                ws.send_json(dict(type='presence', user_id='bob', visible=True, busy=False, typing=False, reading=False, local_hour=12))
                ws.send_text('ping')
                self.assertEqual(ws.receive_json()['type'], 'pong')
                self.assertIsNone(presence.reason('alice'))
                self.assertEqual(presence.reason('bob'), 'not_present')
                ws.send_json(dict(type='presence', visible='true'))
                ws.send_json([])
                ws.send_text('ping')
                ws.receive_json()
                self.assertEqual(presence.reason('alice'), 'not_present')
                ws.send_json(dict(type='proactive_seen', event_id='test-event'))
                self.assertTrue(ws.receive_json()['accepted'])
                scheduler.acknowledge.assert_awaited_once_with('alice', 'test-event')
                ws.close()
                self.assertTrue(finished.wait(2), 'WebSocket handler did not finish cleanup')
            self.assertEqual(presence.sessions, {})

    def test_preference_api_uses_utc_and_strict_boolean(self):
        app = FastAPI()
        app.include_router(proactive.router)
        with patch.object(proactive.proactive_service, 'preferences', return_value={'enabled': False, 'quiet_until': datetime(2026, 9, 11, 9)}), TestClient(app) as client:
            result = client.get('/proactive/preferences?user_id=alice')
            parsed = datetime.fromisoformat(result.json()['quiet_until'].replace('Z', '+00:00'))
            self.assertEqual(parsed.tzinfo, timezone.utc)
            self.assertEqual(client.patch('/proactive/preferences', json={'enabled': 'false'}).status_code, 422)
            self.assertEqual(client.get('/proactive/preferences?user_id=').status_code, 422)
