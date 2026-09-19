import unittest

from agent import Permission, PrivacyManager


class PrivacyManagerTests(unittest.TestCase):
    def test_capture_permissions_are_denied_by_default(self):
        manager = PrivacyManager()
        self.assertFalse(manager.is_allowed("user-1", Permission.MICROPHONE))
        self.assertFalse(manager.require("user-1", Permission.SCREEN))

    def test_consent_and_capture_are_audited_without_content(self):
        manager = PrivacyManager()
        manager.set_consent("user-1", Permission.SCREEN, True)
        self.assertTrue(manager.require("user-1", Permission.SCREEN))
        manager.record_capture("user-1", Permission.SCREEN, content_type="image/png", raw_content="secret")

        entries = manager.get_audit("user-1")
        self.assertEqual(entries[-1]["action"], "capture_used")
        self.assertNotIn("raw_content", entries[-1]["metadata"])

    def test_emergency_revoke_disables_capture_permissions(self):
        manager = PrivacyManager()
        manager.set_consent("user-1", Permission.MICROPHONE, True)
        manager.set_consent("user-1", Permission.SCREEN, True)
        manager.revoke_capture_permissions()

        self.assertFalse(manager.is_allowed("user-1", Permission.MICROPHONE))
        self.assertFalse(manager.is_allowed("user-1", Permission.SCREEN))


if __name__ == "__main__":
    unittest.main()
