import unittest
from datetime import timedelta
from unittest.mock import patch

from agent.event_bus import EventBus
from agent.events import EventType
from agent.proactive_scheduler import ProactiveScheduler
from agent.state_manager import StateManager
from services import proactive_service as context


class ProactiveSchedulerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.rows = {}
        self.output_bus = EventBus()
        self.states = StateManager()
        self.scheduler = ProactiveScheduler(self.output_bus, self.states, user_cooldown_seconds=0)
        self.scheduler.presence.update('tab', 'default', dict(visible=True, busy=False, typing=False, reading=False, local_hour=12))
        def prefs(user):
            return dict(self.rows.setdefault(user, dict(enabled=True, awaiting_reply=False,
                last_user_at=context.utcnow()-timedelta(minutes=10), last_sent_at=None, last_topic=None)))
        def record(user, key):
            prefs(user)
            self.rows[user].update(awaiting_reply=True, last_topic=key, last_sent_at=context.utcnow())
        self.preferences = self.enterContext(patch('agent.proactive_scheduler.context.preferences', side_effect=prefs))
        self.record = self.enterContext(patch('agent.proactive_scheduler.context.record_outreach', side_effect=record))
        self.poll = self.enterContext(patch('agent.proactive_scheduler.poll_due_reminder_notifications_for_all_users', return_value=[]))
        self.progress = self.enterContext(patch('agent.proactive_scheduler.evaluate_progress', return_value={'goals': []}))
        self.recall = self.enterContext(patch(
            'agent.proactive_scheduler.memory_orchestrator.recall_proactive_evidence',
            return_value=(
                [{'role': 'user', 'content': 'Mình đang học Rust.'}],
                [{'memory_type': 'goal', 'fact': 'Người dùng đang học Rust'}],
            ),
        ))
        self.save = self.enterContext(patch('agent.proactive_scheduler.memory_orchestrator.record_assistant_message'))
        self.maintain = self.enterContext(patch(
            'agent.proactive_scheduler.memory_orchestrator.maintain',
            return_value={'ok': True, 'forgotten': {}, 'total': 0},
        ))
        prefs('default')

    async def test_context_offer_then_wait_for_user_instead_of_repeated_checkins(self):
        first = await self.scheduler.tick()
        self.assertEqual(len(first), 1)
        self.assertIn('Rust', first[0].payload['message'])
        self.assertEqual(await self.scheduler.tick(), [])
        self.save.assert_not_called()  # Not shown by a client yet.
        self.assertTrue(await self.scheduler.acknowledge('default', first[0].event_id))
        self.save.assert_called_once_with('default', first[0].payload['message'])
        self.assertFalse(await self.scheduler.acknowledge('default', first[0].event_id))

    async def test_memory_maintenance_runs_once_per_sweep_window(self):
        await self.scheduler.tick()
        await self.scheduler.tick()

        self.maintain.assert_called_once_with()

    async def test_absent_hidden_busy_reading_typing_and_night_are_silent(self):
        for update in [dict(visible=False), dict(busy=True), dict(reading=True), dict(typing=True), dict(local_hour=23)]:
            data = dict(visible=True, busy=False, typing=False, reading=False, local_hour=12)
            data.update(update)
            self.scheduler.presence.update('tab', 'default', data)
            self.assertEqual(await self.scheduler.tick(), [])
        self.scheduler.presence.remove('tab')
        self.assertEqual(await self.scheduler.tick(), [])
        self.recall.assert_not_called()

    async def test_quiet_request_overrides_due_reminders_and_progress(self):
        self.rows['default']['enabled'] = False
        self.poll.return_value = [{'user_id': 'default', 'notifications': [{'id': 7, 'message': 'Đến hạn.'}]}]
        self.assertEqual(await self.scheduler.tick(), [])
        self.record.assert_not_called()

    async def test_no_relevant_or_deleted_memory_means_silence(self):
        self.recall.return_value = ([{'role': 'user', 'content': 'Mình đang học Rust.'}], [])
        self.assertEqual(await self.scheduler.tick(), [])
        self.assertEqual(self.scheduler.last_reason['default'], 'no_relevant_topic')

    async def test_recent_reply_and_old_session_do_not_trigger_idle(self):
        for age in [10, 9 * 3600]:
            self.rows['default']['last_user_at'] = context.utcnow() - timedelta(seconds=age)
            self.assertEqual(await self.scheduler.tick(), [])
        self.recall.assert_not_called()

    async def test_same_topic_is_not_repeated_after_a_short_answer(self):
        first = await self.scheduler.tick()
        self.assertEqual(len(first), 1)
        self.rows['default']['awaiting_reply'] = False
        self.rows['default']['last_sent_at'] -= timedelta(minutes=20)
        self.assertEqual(await self.scheduler.tick(), [])
        self.assertEqual(self.scheduler.last_reason['default'], 'topic_already_used')

    async def test_due_reminder_has_priority_and_does_not_create_fake_user_turn(self):
        self.poll.return_value = [{'user_id': 'default', 'notifications': [{'id': 7, 'message': 'Đến hạn.'}]}]
        events = await self.scheduler.tick()
        self.assertEqual([event.type for event in events], [EventType.PROACTIVE_REMINDER])
        self.assertEqual(await self.scheduler.tick(), [])
        self.save.assert_not_called()

    async def test_global_and_user_emergency_stops(self):
        self.states.set_emergency_stop(True)
        self.assertEqual(await self.scheduler.tick(), [])
        self.poll.assert_not_called()
        self.states.set_emergency_stop(False)
        self.states.update('default', autonomous_enabled=False)
        self.assertEqual(await self.scheduler.tick(), [])

    async def test_budget_prevents_multiple_due_reminders(self):
        self.scheduler.max_events_per_cycle = 1
        self.poll.return_value = [{'user_id': 'default', 'notifications': [{'id': i, 'message': 'Đến hạn.'} for i in (1, 2)]}]
        self.assertEqual(len(await self.scheduler.tick()), 1)
        self.assertEqual(self.record.call_count, 1)

    async def test_persisted_cooldown_survives_new_scheduler_instance(self):
        self.rows['default'].update(last_sent_at=context.utcnow(), awaiting_reply=False)
        self.scheduler.user_cooldown_seconds = 900
        self.assertEqual(await self.scheduler.tick(), [])

    async def test_cross_user_ack_and_ack_after_new_user_message_are_rejected(self):
        event = (await self.scheduler.tick())[0]
        self.assertFalse(await self.scheduler.acknowledge('other-user', event.event_id))
        self.rows['default']['last_user_at'] = context.utcnow()
        self.assertFalse(await self.scheduler.acknowledge('default', event.event_id))
        self.save.assert_not_called()

    async def test_context_and_memory_reads_are_strict_and_user_scoped(self):
        await self.scheduler.tick()
        self.recall.assert_called_once_with('default', history_limit=8, memory_limit=200)

    async def test_expired_offer_cannot_enter_history(self):
        event = (await self.scheduler.tick())[0]
        old, turn, at = self.scheduler._pending[event.event_id]
        self.scheduler._pending[event.event_id] = (old, turn, at - 31)
        self.assertFalse(await self.scheduler.acknowledge('default', event.event_id))
        self.save.assert_not_called()

    async def test_relevant_goal_is_preferred_to_generic_checkin(self):
        self.progress.return_value = {'goals': [{'goal_id': 4, 'title': 'Học Rust', 'status': 'stalled'}]}
        event = (await self.scheduler.tick())[0]
        self.assertEqual(event.payload['kind'], 'progress')
        self.assertIn('Học Rust', event.payload['message'])
        self.assertNotIn('im lặng', event.payload['message'])

    async def test_deleted_memory_after_offer_cannot_be_reintroduced_into_history(self):
        event = (await self.scheduler.tick())[0]
        self.recall.return_value = ([{'role': 'user', 'content': 'Mình đang học Rust.'}], [])
        self.assertFalse(await self.scheduler.acknowledge('default', event.event_id))
        self.save.assert_not_called()
