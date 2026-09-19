import unittest
from unittest.mock import patch

from services import goal_service, planner_service, tool_service


class GoalPlannerTests(unittest.TestCase):
    def test_goal_validation_and_generic_plan(self):
        with self.assertRaises(ValueError):
            goal_service.create_goal(title="", description="")

        steps = planner_service.suggest_steps("Học Python", "Nắm được async")
        self.assertEqual(len(steps), 4)
        self.assertIn("Học Python", steps[0]["title"])

    def test_goal_progress_validation(self):
        with self.assertRaises(ValueError):
            goal_service.update_goal(1, progress=101)

    def test_phase5_tools_are_registered(self):
        names = {definition.name for definition in tool_service.tool_registry.definitions()}
        self.assertTrue({"create_goal", "list_goals", "update_goal", "create_plan", "get_goal_plan", "update_goal_step"} <= names)

    @patch.object(goal_service, "get_db_connection", return_value=None)
    def test_create_goal_returns_none_without_database(self, _connection):
        self.assertIsNone(goal_service.create_goal(title="Học Python"))


if __name__ == "__main__":
    unittest.main()
