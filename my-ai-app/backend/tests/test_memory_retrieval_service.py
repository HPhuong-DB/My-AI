import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx

from services.memory_retrieval_service import HybridMemoryRetriever, OllamaEmbeddingClient


class MemoryRetrievalServiceTests(unittest.TestCase):
    def test_lexical_hybrid_handles_typo_and_ranks_rare_topic(self):
        retriever = HybridMemoryRetriever(embedder=lambda texts: None)
        ownership = {"title": "Ownership trong Rust", "summary": "Quản lý vùng nhớ an toàn"}
        tomato = {"title": "Trồng cà chua", "summary": "Tưới cây mỗi sáng"}

        selected, mode = retriever.rank_groups(
            "owership Rust",
            {"knowledge": ([tomato, ownership], ("title", "summary"), 2)},
        )

        self.assertEqual(mode, "hybrid_lexical")
        self.assertEqual(selected["knowledge"][0], ownership)
        self.assertNotIn(tomato, selected["knowledge"])

    def test_semantic_similarity_recalls_paraphrase_without_shared_keyword(self):
        calls = []

        def embed(texts):
            calls.append(texts)
            return [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]]

        retriever = HybridMemoryRetriever(embedder=embed)
        tea = {"fact": "Người dùng thích trà ô long"}
        unrelated = {"fact": "Người dùng đang học Rust"}
        selected, mode = retriever.rank_groups(
            "đồ uống ưa chuộng",
            {"personal": ([tea, unrelated], ("fact",), 2)},
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(mode, "hybrid_semantic")
        self.assertEqual(selected["personal"], [tea])

    def test_all_memory_groups_share_one_embedding_batch(self):
        calls = []

        def embed(texts):
            calls.append(texts)
            return [[1.0, 0.0] for _ in texts]

        retriever = HybridMemoryRetriever(embedder=embed)
        result, _ = retriever.rank_groups(
            "lập trình",
            {
                "knowledge": ([{"summary": "Python"}], ("summary",), 1),
                "episodes": ([{"description": "Mình hoàn thành dự án"}], ("description",), 1),
            },
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(len(calls[0]), 3)
        self.assertEqual(len(result["knowledge"]), 1)
        self.assertEqual(len(result["episodes"]), 1)

    def test_unrelated_items_do_not_enter_context_from_recency_alone(self):
        retriever = HybridMemoryRetriever(embedder=lambda texts: None)
        selected, _ = retriever.rank_groups(
            "tỷ giá đô la",
            {"items": ([{"text": "trồng cà chua"}], ("text",), 1)},
        )

        self.assertEqual(selected["items"], [])

    def test_embedding_failure_opens_circuit_and_does_not_delay_every_turn(self):
        client = OllamaEmbeddingClient()
        with patch.dict("os.environ", {
            "MEMORY_EMBEDDING_ENABLED": "true",
            "MEMORY_EMBEDDING_FAILURE_COOLDOWN_SECONDS": "300",
        }), patch(
            "services.memory_retrieval_service.httpx.post",
            side_effect=httpx.ConnectError("offline"),
        ) as request:
            self.assertIsNone(client.embed(["lần đầu"]))
            self.assertIsNone(client.embed(["lần sau"]))

        request.assert_called_once()

    def test_expired_and_low_confidence_items_are_excluded(self):
        retriever = HybridMemoryRetriever(embedder=lambda texts: None)
        expired = {
            "fact": "Người dùng thích trà",
            "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1),
        }
        uncertain = {"fact": "Người dùng thích trà", "confidence": 0.2}
        valid = {"fact": "Người dùng thích trà", "confidence": 0.9}

        with patch.dict("os.environ", {"MEMORY_MIN_CONFIDENCE": "0.35"}):
            selected, _ = retriever.rank_groups(
                "thích trà",
                {"personal": ([expired, uncertain, valid], ("fact",), 3)},
            )

        self.assertEqual(selected["personal"], [valid])

    def test_confidence_and_importance_break_equal_relevance_ties(self):
        retriever = HybridMemoryRetriever(embedder=lambda texts: None)
        weak = {"fact": "Người dùng thích trà", "confidence": 0.4, "importance": 0.2}
        strong = {"fact": "Người dùng thích trà", "confidence": 0.95, "importance": 0.9}

        selected, _ = retriever.rank_groups(
            "thích trà",
            {"personal": ([weak, strong], ("fact",), 2)},
        )

        self.assertEqual(selected["personal"], [strong, weak])


if __name__ == "__main__":
    unittest.main()
