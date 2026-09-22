import unittest
from unittest.mock import patch

from services import memory_service as memory
from core.database import DatabaseUnavailable
from test_memory_service import FakeConnection, FakeCursor


class MemoryCorrectionTests(unittest.TestCase):
    def extract(self, text):
        with patch.object(memory, "save_memory") as saved, patch.object(memory, "get_user_profile", return_value=None), patch.object(memory, "get_recent_memories", return_value=[]), patch.object(memory, "save_user_profile"):
            memory.save_memory_from_conversation(text, "", "alice")
            return saved.call_args_list

    def test_negative_preference_and_goal_are_saved_as_negative(self):
        calls = self.extract("Mình không còn thích trà nữa. Mình không còn học Python.")
        self.assertEqual(calls[0].args[:2], ("preference", "Người dùng không còn thích trà"))
        self.assertEqual(calls[1].args[:2], ("goal", "Người dùng không còn học Python"))

    def test_questions_quotes_and_conditionals_are_not_personal_facts(self):
        for text in ['Mình thích trà không?', 'Ví dụ: mình thích trà', 'Nếu mình thích trà thì sao?', '"Mình thích trà"']:
            self.assertEqual(self.extract(text), [], text)

    def test_full_name_is_preserved(self):
        self.assertEqual(memory._extract_name("Mình tên là Nguyễn Văn An"), "Nguyễn Văn An")

    def test_multiple_quoted_sentences_are_not_saved_as_speakers_own_facts(self):
        for text in ["Mai nói: 'Mình thích cà phê. Mình học piano.'", 'Bạn mình nhắn: “Mình tên là Mai. Mình học piano.”', '```\nMình học piano.\n```']:
            self.assertEqual(self.extract(text), [], text)

    def test_pronoun_preference_is_not_saved_as_a_personal_name(self):
        calls = self.extract('Từ giờ gọi mình là cậu, xưng tớ nhé.')
        self.assertEqual(calls[0].args[:2], ('communication_style', 'Huohuo xưng tớ, gọi người dùng là cậu'))
        self.assertIsNone(memory._extract_name('Gọi mình là cậu'))

    def test_reversed_direct_style_request_is_saved_but_quotes_are_not(self):
        calls = self.extract('Từ giờ xưng tớ và gọi mình là cậu nhé.')
        self.assertEqual(calls[0].args[:2], ('communication_style', 'Huohuo xưng tớ, gọi người dùng là cậu'))
        for text in ['Mai nói từ giờ xưng tớ và gọi mình là cậu nhé.', '“Từ giờ xưng tớ và gọi mình là cậu nhé.”', 'Nếu xưng tớ và gọi mình là cậu thì sao?']:
            self.assertEqual(self.extract(text), [])

    def test_to_pronoun_preserves_personal_facts(self):
        calls = self.extract('Tớ tên là Hà. Tớ thích đọc sách. Tớ không còn học Rust nữa.')
        self.assertEqual([call.args[:2] for call in calls], [
            ('user_name', 'Tên người dùng là Hà'),
            ('preference', 'Người dùng thích đọc sách'),
            ('goal', 'Người dùng không còn học Rust'),
        ])

    def test_third_party_style_request_is_not_users_preference(self):
        self.assertEqual(self.extract('Mai nói gọi mình là cậu, xưng tớ nhé.'), [])

    def test_correction_replaces_matching_subject_only(self):
        cursor = FakeCursor(
            fetchall_result=[{"id": 1, "fact": "Người dùng thích trà"}, {"id": 2, "fact": "Người dùng thích cà phê"}],
            lastrowid=9,
        )
        conn = FakeConnection(cursor)
        with patch.object(memory, "get_db_connection", return_value=conn), patch.object(memory, "_ensure_memory_tables"), patch("services.chat_service._ensure_table_exists"):
            self.assertTrue(memory.save_memory("preference", "Người dùng không còn thích trà", "alice", strict=True))
        updates = [params for sql, params in cursor.executed if sql.startswith("UPDATE core_memories")]
        self.assertEqual(updates, [(9, 1, "alice")])
        self.assertTrue(any("forget_reason = 'superseded'" in sql for sql, _ in cursor.executed))
        self.assertTrue(any("cutoff_chat_id" in sql for sql, _ in cursor.executed))

    def test_correction_with_provenance_excludes_only_source_turn(self):
        cursor = FakeCursor(
            fetchall_result=[{
                "id": 1,
                "fact": "Người dùng thích trà",
                "source_ref": "user_message:0123456789abcdef",
            }],
            lastrowid=9,
        )
        conn = FakeConnection(cursor)
        with patch.object(memory, "get_db_connection", return_value=conn), patch.object(memory, "_ensure_memory_tables"), patch("services.chat_service._ensure_table_exists"):
            self.assertTrue(memory.save_memory("preference", "Người dùng không còn thích trà", "alice", strict=True))

        sql = " ".join(statement for statement, _ in cursor.executed)
        self.assertIn("memory_context_exclusions", sql)
        self.assertNotIn("ON DUPLICATE KEY UPDATE cutoff_chat_id", sql)
        exclusion_params = [params for statement, params in cursor.executed if "SHA2(TRIM(content)" in statement]
        self.assertEqual(exclusion_params[0][-1], "0123456789abcdef")

    def test_missing_or_other_users_memory_cannot_be_edited(self):
        cursor = FakeCursor()
        with patch.object(memory, "get_db_connection", return_value=FakeConnection(cursor)), patch.object(memory, "_ensure_memory_tables"), patch("services.chat_service._ensure_table_exists"):
            self.assertFalse(memory.update_memory(5, "new", "bob"))
        self.assertEqual(cursor.executed[0][1], (5, "bob"))
        self.assertFalse(any(sql.startswith("UPDATE core_memories") for sql, _ in cursor.executed))

    def test_deleting_name_clears_profile_and_old_context(self):
        cursor = FakeCursor(fetchone_result={"id": 5, "memory_type": "user_name", "fact": "Tên người dùng là An"})
        with patch.object(memory, "get_db_connection", return_value=FakeConnection(cursor)), patch.object(memory, "_ensure_memory_tables"), patch("services.chat_service._ensure_table_exists"):
            self.assertTrue(memory.delete_memory(5, "alice"))
        self.assertIn(("Bạn", "alice"), [params for sql, params in cursor.executed if sql.startswith("UPDATE user_profiles")])
        self.assertTrue(any("cutoff_chat_id" in sql for sql, _ in cursor.executed))

    def test_unavailable_database_is_not_reported_as_missing_memory(self):
        with patch.object(memory, "get_db_connection", return_value=None):
            with self.assertRaises(DatabaseUnavailable):
                memory.delete_memory(1, "alice")
            with self.assertRaises(DatabaseUnavailable):
                memory.get_recent_memories(user_id="alice", strict=True)


if __name__ == "__main__":
    unittest.main()
