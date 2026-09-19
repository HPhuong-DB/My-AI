import unittest

from agent.tooling import ToolDefinition, ToolExecutor, ToolRegistry


class ToolingTests(unittest.IsolatedAsyncioTestCase):
    async def test_confirmation_is_required_before_dangerous_tool(self):
        registry = ToolRegistry()
        registry.register(
            ToolDefinition("write", "write", {"type": "object"}, requires_confirmation=True),
            lambda user_id, arguments: {"written": True, "user_id": user_id},
        )
        executor = ToolExecutor(registry, max_calls=10)

        pending = await executor.execute("write", "user-1", {"path": "a.txt"})
        self.assertEqual(pending.status, executor.STATUS_CONFIRMATION_REQUIRED)
        self.assertIsNotNone(pending.confirmation_id)

        confirmed = await executor.execute(
            "write",
            "user-1",
            {},
            confirmation_id=pending.confirmation_id,
        )
        self.assertEqual(confirmed.status, executor.STATUS_EXECUTED)

    async def test_rate_limit_is_enforced(self):
        registry = ToolRegistry()
        registry.register(ToolDefinition("ping", "ping", {"type": "object"}), lambda user_id, arguments: {"ok": True})
        executor = ToolExecutor(registry, max_calls=1)

        first = await executor.execute("ping", "user-1")
        second = await executor.execute("ping", "user-1")
        self.assertEqual(first.status, executor.STATUS_EXECUTED)
        self.assertEqual(second.status, executor.STATUS_RATE_LIMITED)


if __name__ == "__main__":
    unittest.main()
