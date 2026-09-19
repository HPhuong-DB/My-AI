import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from services import knowledge_service, progress_service


class MemoryProgressTests(unittest.TestCase):
    def test_progress_evaluator_detects_at_risk_goal(self):
        now = datetime.now(timezone.utc)
        goal = {
            "id": 1,
            "title": "Học Python",
            "progress": 10,
            "status": "active",
            "created_at": now - timedelta(days=10),
            "target_date": now + timedelta(days=20),
            "updated_at": now,
        }
        evaluation = progress_service.evaluate_goal(goal, [], now)
        self.assertEqual(evaluation["status"], "at_risk")
        self.assertTrue(evaluation["recommendations"])

    def test_progress_evaluator_detects_stalled_goal_without_deadline(self):
        now = datetime.now(timezone.utc)
        goal = {"id": 2, "title": "Viết sách", "progress": 20, "status": "active", "updated_at": now - timedelta(days=10)}
        evaluation = progress_service.evaluate_goal(goal, [], now)
        self.assertEqual(evaluation["status"], "stalled")
        self.assertGreaterEqual(len(evaluation["recommendations"]), 2)

    @patch.object(knowledge_service, "get_recent_memories", return_value=[{"fact": "Thích Python"}])
    @patch.object(knowledge_service, "list_knowledge", return_value=[{"summary": "Python async"}])
    @patch.object(knowledge_service, "list_experiences", return_value=[{"lesson": "Chia nhỏ task"}])
    def test_long_term_memory_keeps_categories_separate(self, _experiences, _knowledge, _personal):
        result = knowledge_service.get_long_term_memory("user-1")
        self.assertEqual(result.keys(), {"user_id", "personal", "knowledge", "experiences"})
        self.assertEqual(result["personal"][0]["fact"], "Thích Python")
        self.assertEqual(result["knowledge"][0]["summary"], "Python async")
        self.assertEqual(result["experiences"][0]["lesson"], "Chia nhỏ task")

    def test_experience_requires_title_and_lesson(self):
        with self.assertRaises(ValueError):
            knowledge_service.save_experience(title="", lesson="")


if __name__ == "__main__":
    unittest.main()
