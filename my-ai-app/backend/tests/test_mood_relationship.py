import unittest
from unittest.mock import patch

from services.mood_service import MoodManager
from services.interaction_service import NaturalInteractionEngine
from services.relationship_service import get_relationship


class MoodManagerTests(unittest.TestCase):
    @patch("services.mood_service.get_user_mood_timeline")
    def test_summary_detects_improving_long_term_mood(self, timeline_mock):
        timeline_mock.return_value = [
            {"mood": "happy", "created_at": "2026-09-07"},
            {"mood": "happy", "created_at": "2026-09-06"},
            {"mood": "sad", "created_at": "2026-09-05"},
            {"mood": "stressed", "created_at": "2026-09-04"},
        ]

        summary = MoodManager().summarize("user-1", limit=10)

        self.assertEqual(summary["current_mood"], "happy")
        self.assertEqual(summary["dominant_mood"], "happy")
        self.assertEqual(summary["trend"], "improving")
        self.assertEqual(summary["sample_count"], 4)

    def test_message_analysis_returns_bounded_signal(self):
        signal = MoodManager().analyze_message("Mình rất vui và cảm ơn bạn")

        self.assertEqual(signal["mood"], "happy")
        self.assertGreaterEqual(signal["signal_strength"], 0)
        self.assertLessEqual(signal["signal_strength"], 1)


class RelationshipManagerTests(unittest.TestCase):
    @patch("services.relationship_service.get_user_profile", return_value={
        "user_id": "user-1",
        "username": "An",
        "affection_level": 8,
        "mood": "happy",
        "interaction_count": 24,
        "last_interaction": "2026-09-07",
    })
    def test_relationship_maps_affection_to_trusted_stage(self, profile_mock):
        relationship = get_relationship("user-1")

        self.assertEqual(relationship["stage"], "trusted")
        self.assertEqual(relationship["affection_level"], 8)
        self.assertEqual(relationship["interaction_count"], 24)
        self.assertIn("thân quen", relationship["tone"])
        profile_mock.assert_called_once_with(user_id="user-1")

    @patch("services.relationship_service.get_user_profile", return_value=None)
    def test_unknown_user_starts_at_new_stage(self, profile_mock):
        relationship = get_relationship("new-user")

        self.assertEqual(relationship["stage"], "new")
        self.assertEqual(relationship["affection_level"], 0)
        self.assertEqual(relationship["interaction_count"], 0)


class NaturalInteractionTests(unittest.TestCase):
    def test_idle_messages_rotate_before_repeating(self):
        engine = NaturalInteractionEngine(history_size=2)

        first = engine.idle_message("user-1", mood="neutral", stage="new")
        second = engine.idle_message("user-1", mood="neutral", stage="new")

        self.assertNotEqual(first, second)

    def test_message_adapts_to_stressed_mood(self):
        message = NaturalInteractionEngine().progress_message(
            "user-1",
            title="Học Python",
            status="at_risk",
            mood="stressed",
        )

        self.assertIn("không muốn tạo áp lực", message)


if __name__ == "__main__":
    unittest.main()
