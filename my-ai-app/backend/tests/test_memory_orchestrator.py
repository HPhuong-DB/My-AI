import json
import unittest
from unittest.mock import patch

from core.database import DatabaseUnavailable
from services import memory_orchestrator as orchestrator_module
from services.memory_orchestrator import MemoryOrchestrator


class MemoryOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.orchestrator = MemoryOrchestrator()

    def test_prepare_turn_consolidates_before_persisting_history(self):
        order = []
        with patch.object(
            orchestrator_module,
            "save_memory_from_conversation",
            side_effect=lambda *args, **kwargs: order.append(("consolidate", args, kwargs)),
        ), patch.object(
            orchestrator_module,
            "save_chat_message",
            side_effect=lambda *args, **kwargs: order.append(("history", args, kwargs)),
        ):
            self.orchestrator.prepare_user_turn("alice", "Mình thích trà")

        self.assertEqual([item[0] for item in order], ["consolidate", "history"])
        self.assertEqual(order[0][1][:3], ("Mình thích trà", "", "alice"))
        self.assertTrue(order[0][2]["strict"])
        self.assertEqual(order[1][1], ("user", "Mình thích trà", "alice"))
        self.assertTrue(order[1][2]["strict"])

    def test_failed_consolidation_does_not_persist_user_history(self):
        with patch.object(
            orchestrator_module,
            "save_memory_from_conversation",
            side_effect=DatabaseUnavailable("memory unavailable"),
        ), patch.object(orchestrator_module, "save_chat_message") as history:
            with self.assertRaises(DatabaseUnavailable):
                self.orchestrator.prepare_user_turn("alice", "Mình thích trà")

        history.assert_not_called()

    def test_prompt_recall_is_bounded_scoped_and_includes_runtime_context(self):
        history = [
            {"role": "assistant", "content": "Bạn đang học gì?"},
            {"role": "user", "content": "Mình đang học Rust"},
        ]
        memories = [{"memory_type": "goal", "fact": "Người dùng đang học Rust"}]
        runtime = {
            "activity": "listening",
            "attention": "focused",
            "current_topic": "Rust",
        }
        with patch.object(orchestrator_module, "get_recent_chat_history", return_value=history) as history_read, patch.object(
            orchestrator_module, "get_recent_memories", return_value=memories
        ) as memory_read, patch.object(
            orchestrator_module, "get_user_profile", return_value={"username": "An"}
        ), patch.object(self.orchestrator, "_runtime_context", return_value=runtime), patch.object(
            self.orchestrator, "_load_archival_candidates", return_value=([], [])
        ), patch.object(
            self.orchestrator, "_load_conversation_candidates", return_value=([], [])
        ):
            recalled = self.orchestrator.recall_prompt(
                "Học tiếp thế nào?",
                "alice",
                history_limit=13,
                memory_limit=200,
                max_chars=4000,
            )

        history_read.assert_called_once_with(limit=13, user_id="alice", strict=True)
        memory_read.assert_called_once_with(limit=200, user_id="alice", strict=True)
        self.assertEqual(recalled.history_count, 2)
        self.assertEqual(recalled.memory_candidate_count, 1)
        evidence = json.loads(recalled.prompt.evidence)
        self.assertEqual(evidence["ngu_canh_tuc_thoi"]["current_topic"], "Rust")

    def test_runtime_context_is_removed_before_relevant_memory_when_budget_is_tight(self):
        runtime = {
            "current_topic": "x" * 500,
            "attention": "focused",
        }
        with patch.object(orchestrator_module, "get_recent_chat_history", return_value=[]), patch.object(
            orchestrator_module,
            "get_recent_memories",
            return_value=[{"memory_type": "communication_style", "fact": "Huohuo xưng tớ, gọi người dùng là cậu"}],
        ), patch.object(orchestrator_module, "get_user_profile", return_value=None), patch.object(
            self.orchestrator, "_runtime_context", return_value=runtime
        ), patch.object(
            self.orchestrator, "_load_archival_candidates", return_value=([], [])
        ):
            recalled = self.orchestrator.recall_prompt(
                "Chào",
                "alice",
                history_limit=13,
                memory_limit=200,
                max_chars=500,
            )

        evidence = json.loads(recalled.prompt.evidence)
        self.assertNotIn("ngu_canh_tuc_thoi", evidence)
        self.assertEqual(evidence["ky_uc_lien_quan"][0]["loai"], "communication_style")

    def test_prompt_recall_selects_relevant_knowledge_and_experience(self):
        history = [
            {"role": "user", "content": "Mình đang học Rust"},
            {"role": "assistant", "content": "Rust khá thú vị."},
        ]
        knowledge = [
            {
                "title": "Ownership trong Rust",
                "query_text": "học Rust",
                "summary": "Ownership quản lý vùng nhớ.",
                "key_points": ["Mỗi giá trị có một owner"],
            },
            {"title": "Trồng cà chua", "summary": "Tưới vừa đủ", "key_points": []},
        ]
        experiences = [
            {"title": "Học Rust", "lesson": "Viết ví dụ nhỏ sau mỗi khái niệm", "context": "Lộ trình lập trình"},
            {"title": "Nấu cơm", "lesson": "Đong đủ nước", "context": "Nhà bếp"},
        ]
        with patch.object(orchestrator_module, "get_recent_chat_history", return_value=history), patch.object(
            orchestrator_module, "get_recent_memories", return_value=[]
        ), patch.object(orchestrator_module, "get_user_profile", return_value=None), patch.object(
            self.orchestrator, "_runtime_context", return_value=None
        ), patch.object(
            self.orchestrator, "_load_archival_candidates", return_value=(knowledge, experiences)
        ), patch.object(
            self.orchestrator,
            "_load_conversation_candidates",
            return_value=(
                [{
                    "id": 9,
                    "topics": ["rust"],
                    "user_points": [{"chat_id": 2, "text": "Mình đang học Rust"}],
                    "assistant_points": [{"chat_id": 2, "text": "Hãy bắt đầu với ownership"}],
                }],
                [{
                    "id": 8,
                    "event_type": "decision",
                    "title": "Quyết định: Mình quyết định học Rust",
                    "description": "Mình quyết định học Rust",
                    "source_role": "user",
                    "salience": 0.8,
                }],
            ),
        ):
            recalled = self.orchestrator.recall_prompt(
                "Học tiếp thế nào?",
                "alice",
                history_limit=13,
                memory_limit=200,
                max_chars=4000,
            )

        evidence = json.loads(recalled.prompt.evidence)
        self.assertEqual(recalled.knowledge_candidate_count, 2)
        self.assertEqual(recalled.experience_candidate_count, 2)
        self.assertEqual(recalled.knowledge_recall_count, 1)
        self.assertEqual(recalled.experience_recall_count, 1)
        self.assertEqual(recalled.session_recall_count, 1)
        self.assertEqual(recalled.episode_recall_count, 1)
        self.assertEqual(recalled.retrieval_mode, "hybrid_lexical")
        self.assertEqual(evidence["kien_thuc_lien_quan"][0]["tieu_de"], "Ownership trong Rust")
        self.assertEqual(evidence["kinh_nghiem_lien_quan"][0]["tieu_de"], "Học Rust")
        self.assertEqual(evidence["tom_tat_phien_lien_quan"][0]["chu_de"], ["rust"])
        self.assertEqual(evidence["su_kien_ca_nhan_lien_quan"][0]["loai"], "decision")
        self.assertNotIn("cà chua", recalled.prompt.evidence)
        self.assertNotIn("Nấu cơm", recalled.prompt.evidence)

    def test_archive_follow_up_never_uses_assistant_words_as_recall_query(self):
        history = [
            {"role": "user", "content": "Kể mình một chuyện đi"},
            {"role": "assistant", "content": "Kubernetes dùng pod để chạy workload."},
        ]
        query = self.orchestrator._archive_recall_query("Kể tiếp đi", history)
        selected = self.orchestrator._select_archival_items(
            query,
            [{"title": "Kubernetes", "summary": "Pod và workload", "key_points": []}],
            fields=("title", "summary", "key_points"),
            limit=3,
        )

        self.assertNotIn("Kubernetes", query)
        self.assertEqual(selected, [])

    def test_explicit_session_and_episode_recall_can_use_recent_items_without_keyword_overlap(self):
        self.assertTrue(self.orchestrator._asks_for_session_recall("Lần trước mình nói gì?"))
        self.assertTrue(self.orchestrator._asks_for_episode_recall("Bạn nhớ sự kiện nào của mình không?"))
        self.assertFalse(self.orchestrator._asks_for_episode_recall("Giải thích vòng lặp"))

    def test_realtime_search_turn_skips_archival_recall(self):
        with patch.object(orchestrator_module, "get_recent_chat_history", return_value=[]), patch.object(
            orchestrator_module, "get_recent_memories", return_value=[]
        ), patch.object(orchestrator_module, "get_user_profile", return_value=None), patch.object(
            self.orchestrator, "_runtime_context", return_value=None
        ), patch.object(self.orchestrator, "_load_archival_candidates") as archive_read:
            recalled = self.orchestrator.recall_prompt(
                "Tỷ giá hôm nay?\n\n[TRA CỨU THỜI GIAN THỰC]\n1 USD = 26000 VND",
                "alice",
                history_limit=13,
                memory_limit=200,
                max_chars=4000,
            )

        archive_read.assert_not_called()
        evidence = json.loads(recalled.prompt.evidence)
        self.assertNotIn("kien_thuc_lien_quan", evidence)
        self.assertNotIn("kinh_nghiem_lien_quan", evidence)

    def test_simple_greeting_skips_archive_database_reads(self):
        with patch.object(orchestrator_module, "get_recent_chat_history", return_value=[]), patch.object(
            orchestrator_module, "get_recent_memories", return_value=[]
        ), patch.object(orchestrator_module, "get_user_profile", return_value=None), patch.object(
            self.orchestrator, "_runtime_context", return_value=None
        ), patch.object(self.orchestrator, "_load_archival_candidates") as archive_read:
            self.orchestrator.recall_prompt(
                "Xin chào Huohuo",
                "alice",
                history_limit=13,
                memory_limit=200,
                max_chars=4000,
            )

        archive_read.assert_not_called()

    def test_hybrid_personal_recall_does_not_expose_user_name_for_third_party_question(self):
        memories = [{"memory_type": "user_name", "fact": "Tên người dùng là An"}]
        with patch.object(orchestrator_module, "get_recent_chat_history", return_value=[]), patch.object(
            orchestrator_module, "get_recent_memories", return_value=memories
        ), patch.object(orchestrator_module, "get_user_profile", return_value={"username": "An"}), patch.object(
            self.orchestrator, "_runtime_context", return_value=None
        ), patch.object(
            self.orchestrator, "_load_archival_candidates", return_value=([], [])
        ), patch.object(
            self.orchestrator, "_load_conversation_candidates", return_value=([], [])
        ):
            recalled = self.orchestrator.recall_prompt(
                "Tên bạn thân của mình là gì?",
                "alice",
                history_limit=13,
                memory_limit=200,
                max_chars=4000,
            )

        self.assertNotIn("An", recalled.prompt.evidence)

    def test_update_forget_and_direct_remember_use_repository_boundaries(self):
        with patch.object(orchestrator_module, "save_memory", return_value=True) as save, patch.object(
            orchestrator_module, "update_memory", return_value=True
        ) as update, patch.object(orchestrator_module, "delete_memory", return_value=True) as delete:
            self.assertTrue(self.orchestrator.remember("preference", "Người dùng thích trà", "alice", strict=True))
            self.assertTrue(self.orchestrator.update(3, "Người dùng thích cà phê", "alice"))
            self.assertTrue(self.orchestrator.forget(3, "alice"))

        save.assert_called_once_with(
            "preference",
            "Người dùng thích trà",
            "alice",
            confidence=0.9,
            importance=None,
            source_type="conversation",
            source_ref=None,
            expires_at=None,
            strict=True,
        )
        update.assert_called_once_with(3, "Người dùng thích cà phê", "alice")
        delete.assert_called_once_with(3, "alice")

    def test_completed_reply_updates_derived_conversation_memory(self):
        with patch.object(orchestrator_module, "save_chat_message", return_value=12) as save, patch(
            "services.conversation_memory_service.record_completed_turn"
        ) as record:
            self.orchestrator.record_assistant_message(
                "alice",
                "Chúc mừng bạn!",
                user_message="Hôm nay mình đã thi đậu",
            )

        save.assert_called_once_with("assistant", "Chúc mừng bạn!", "alice", strict=True)
        record.assert_called_once_with(
            "alice",
            "Hôm nay mình đã thi đậu",
            "Chúc mừng bạn!",
            12,
            strict=False,
        )

    def test_long_term_recall_preserves_existing_contract(self):
        expected = {
            "user_id": "alice",
            "personal": [],
            "knowledge": [],
            "experiences": [],
        }
        with patch("services.knowledge_service.get_long_term_memory", return_value=expected) as recall:
            result = self.orchestrator.recall_long_term("alice", "Rust", 7)

        self.assertEqual(result, expected)
        recall.assert_called_once_with("alice", "Rust", 7)


if __name__ == "__main__":
    unittest.main()
