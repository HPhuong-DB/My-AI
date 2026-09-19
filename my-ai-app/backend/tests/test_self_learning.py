import unittest
from unittest.mock import patch

from agent.state_manager import StateManager
from services.self_learning_service import (
    SelfLearningError,
    SelfLearningRateLimitError,
    SelfLearningService,
    learning_policy,
)


class SelfLearningServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = SelfLearningService(StateManager(), max_updates=2, window_seconds=3600)

    @patch("services.self_learning_service.save_memory", return_value=True)
    def test_memory_learning_uses_only_memory_store(self, save_memory_mock):
        result = self.service.learn(
            "user-1",
            target="memory",
            title="Sở thích",
            content="Người dùng thích trà đào.",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["target"], "memory")
        save_memory_mock.assert_called_once_with("learned_fact", "Người dùng thích trà đào.", "user-1")

    @patch("services.self_learning_service.save_knowledge", return_value={"id": 1})
    def test_knowledge_learning_is_bounded_to_knowledge_store(self, save_knowledge_mock):
        result = self.service.learn(
            "user-1",
            target="knowledge",
            title="Python",
            content="Python là ngôn ngữ lập trình.",
            source_url="https://example.com/python",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["policy"], "knowledge_and_memory_only")
        save_knowledge_mock.assert_called_once()

    def test_code_and_permission_targets_are_rejected(self):
        for target in ("code", "permissions", "system"):
            with self.assertRaises(SelfLearningError):
                self.service.learn("user-1", target=target, title="x", content="y")

    def test_emergency_stop_blocks_learning(self):
        self.service.state_manager.set_emergency_stop(True)

        with self.assertRaises(SelfLearningError):
            self.service.learn("user-1", target="memory", title="x", content="y")

    @patch("services.self_learning_service.save_memory", return_value=True)
    def test_learning_rate_limit_is_enforced(self, save_memory_mock):
        for index in range(2):
            self.service.learn("user-1", target="memory", title=str(index), content="fact")

        with self.assertRaises(SelfLearningRateLimitError):
            self.service.learn("user-1", target="memory", title="3", content="fact")

        self.assertEqual(save_memory_mock.call_count, 2)

    def test_policy_exposes_hard_boundaries(self):
        policy = learning_policy()

        self.assertEqual(set(policy["allowed_targets"]), {"memory", "knowledge", "experience"})
        self.assertFalse(policy["code_changes_allowed"])
        self.assertFalse(policy["system_permission_changes_allowed"])


if __name__ == "__main__":
    unittest.main()
