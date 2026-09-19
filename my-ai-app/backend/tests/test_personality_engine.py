import unittest

from services.llm_service import SYSTEM_PROMPT
from services.personality_service import personality_engine


class PersonalityEngineTests(unittest.TestCase):
    def test_profile_has_stable_identity_and_boundaries(self):
        profile = personality_engine.public_profile()

        self.assertEqual(profile["name"], "Huohuo")
        self.assertEqual(profile["role"], "AI companion")
        self.assertTrue(profile["core_traits"])
        self.assertTrue(profile["boundaries"])
        self.assertIn("", profile["allowed_motions"])
        self.assertIn("", profile["allowed_expressions"])

    def test_system_prompt_contains_consistency_contract(self):
        self.assertIn("Personality Engine", SYSTEM_PROMPT)
        self.assertIn("không thao túng cảm xúc người dùng", SYSTEM_PROMPT)
        self.assertIn("danh tính cố định", SYSTEM_PROMPT.lower())

    def test_context_changes_tone_guidance_not_core_identity(self):
        rules = personality_engine.contextual_rules(
            {"mood": "stressed", "affection_level": 8},
            "fast",
        )

        self.assertIn("giảm áp lực", rules)
        self.assertIn("affection_level=8", rules)
        self.assertIn("Mood là trạng thái", rules)

    def test_invalid_affect_is_removed(self):
        motion, expression = personality_engine.validate_affect("unknown", "unknown")

        self.assertEqual(motion, "")
        self.assertEqual(expression, "")


if __name__ == "__main__":
    unittest.main()
