import unittest

from agent import (
    AgentAction,
    AgentExecutor,
    Decision,
    Event,
    EventType,
    ExecutionStatus,
    StateManager,
)


class AgentExecutorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.event = Event.create(EventType.USER_MESSAGE, user_id="user-1", payload={"text": "Xin chào"})
        self.state = StateManager().get_state("user-1")
        self.decision = Decision(
            should_respond=True,
            action=AgentAction.RESPOND,
            reason="user_message_requires_response",
            user_id="user-1",
            event_id=self.event.event_id,
        )

    async def test_async_handler_is_executed_and_result_is_normalized(self):
        called = []

        async def handler(decision, event, state):
            called.append((decision, event, state))
            return {"message": "Đã xử lý", "motion": "haoqi"}

        executor = AgentExecutor({AgentAction.RESPOND: handler})
        result = await executor.execute(self.decision, self.event, self.state)

        self.assertEqual(result.status, ExecutionStatus.EXECUTED)
        self.assertEqual(result.message, "Đã xử lý")
        self.assertEqual(result.data["motion"], "haoqi")
        self.assertEqual(len(called), 1)

    async def test_missing_handler_is_deferred(self):
        result = await AgentExecutor().execute(self.decision, self.event, self.state)
        self.assertEqual(result.status, ExecutionStatus.DEFERRED)

    async def test_ignored_decision_is_not_executed(self):
        decision = Decision(False, AgentAction.IGNORE, "cooldown", "user-1", self.event.event_id)
        result = await AgentExecutor().execute(decision, self.event, self.state)
        self.assertEqual(result.status, ExecutionStatus.IGNORED)

    async def test_handler_failure_is_reported_without_crashing_loop(self):
        def handler(*args):
            raise RuntimeError("test failure")

        result = await AgentExecutor({AgentAction.RESPOND: handler}).execute(
            self.decision, self.event, self.state
        )
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertEqual(result.message, "handler_failed")

    def test_unknown_action_cannot_be_registered(self):
        with self.assertRaises(ValueError):
            AgentExecutor().register("delete_everything", lambda *args: None)


if __name__ == "__main__":
    unittest.main()
