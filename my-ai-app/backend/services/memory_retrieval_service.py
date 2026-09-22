"""Hybrid lexical and optional local-embedding retrieval for memory stores."""

from __future__ import annotations

from collections import Counter, OrderedDict
from collections.abc import Callable, Mapping, Sequence
import json
import math
import os
import re
from threading import Lock
from time import monotonic
from typing import Any

import httpx

from services.dialogue_context_service import normalize, tokens
from services.memory_metadata import clamp_score, is_expired


Embedder = Callable[[list[str]], list[list[float]] | None]


def item_text(item: Mapping[str, Any], fields: Sequence[str], limit: int = 1600) -> str:
    parts: list[str] = []
    for field in fields:
        value = item.get(field, "")
        if isinstance(value, (list, dict)):
            parts.append(json.dumps(value, ensure_ascii=False))
        else:
            parts.append(str(value or ""))
    return re.sub(r"\s+", " ", " ".join(parts)).strip()[:limit]


def _char_ngrams(text: str, size: int = 3) -> set[str]:
    compact = re.sub(r"[^\w]+", " ", normalize(text)).strip()
    if not compact:
        return set()
    padded = f"  {compact}  "
    return {padded[index:index + size] for index in range(max(1, len(padded) - size + 1))}


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


class OllamaEmbeddingClient:
    """Small cached adapter with a failure cooldown for optional embeddings."""

    def __init__(self) -> None:
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._lock = Lock()
        self._disabled_until = 0.0

    def enabled(self) -> bool:
        return os.getenv("MEMORY_EMBEDDING_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        if not self.enabled() or not texts or monotonic() < self._disabled_until:
            return None
        normalized_texts = [str(text or "")[:1600] for text in texts]
        missing = []
        with self._lock:
            for text in normalized_texts:
                if text not in self._cache and text not in missing:
                    missing.append(text)
        if missing:
            try:
                timeout = max(0.2, min(float(os.getenv("MEMORY_EMBEDDING_TIMEOUT_SECONDS", "1.2")), 5.0))
                response = httpx.post(
                    os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/embed",
                    json={
                        "model": os.getenv("MEMORY_EMBEDDING_MODEL", "qwen3-embedding:0.6b"),
                        "input": missing,
                        "truncate": True,
                        "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "-1"),
                    },
                    timeout=timeout,
                )
                response.raise_for_status()
                vectors = response.json().get("embeddings")
                if not isinstance(vectors, list) or len(vectors) != len(missing):
                    raise ValueError("invalid embedding response")
                cache_limit = max(32, min(int(os.getenv("MEMORY_EMBEDDING_CACHE_SIZE", "512")), 4096))
                with self._lock:
                    for text, vector in zip(missing, vectors):
                        if not isinstance(vector, list) or not vector:
                            raise ValueError("invalid embedding vector")
                        self._cache[text] = [float(value) for value in vector]
                        self._cache.move_to_end(text)
                    while len(self._cache) > cache_limit:
                        self._cache.popitem(last=False)
            except (httpx.HTTPError, TypeError, ValueError):
                cooldown = max(10.0, float(os.getenv("MEMORY_EMBEDDING_FAILURE_COOLDOWN_SECONDS", "300")))
                self._disabled_until = monotonic() + cooldown
                return None
        with self._lock:
            result = [self._cache.get(text) for text in normalized_texts]
        if any(vector is None for vector in result):
            return None
        return [vector for vector in result if vector is not None]


class HybridMemoryRetriever:
    """Rank multiple stores in one pass and one optional embedding batch."""

    def __init__(self, embedder: Embedder | None = None) -> None:
        self._embedder = embedder or OllamaEmbeddingClient().embed

    def rank_groups(
        self,
        query: str,
        groups: Mapping[str, tuple[list[dict[str, Any]], tuple[str, ...], int]],
    ) -> tuple[dict[str, list[dict[str, Any]]], str]:
        query = str(query or "").strip()
        query_tokens = tokens(query)
        if not query_tokens:
            return {name: [] for name in groups}, "lexical"

        documents: list[tuple[str, int, dict[str, Any], str]] = []
        min_confidence = max(0.0, min(float(os.getenv("MEMORY_MIN_CONFIDENCE", "0.35")), 1.0))
        for group_name, (candidates, fields, limit) in groups.items():
            if limit <= 0:
                continue
            for index, item in enumerate(candidates):
                if is_expired(item.get("expires_at")):
                    continue
                if clamp_score(item.get("confidence"), 1.0) < min_confidence:
                    continue
                text = item_text(item, fields)
                if text:
                    documents.append((group_name, index, item, text))

        if not documents:
            return {name: [] for name in groups}, "lexical"

        document_tokens = [tokens(text) for _, _, _, text in documents]
        document_frequency = Counter(
            token
            for token_set in document_tokens
            for token in token_set
        )
        total_documents = len(documents)
        query_ngrams = _char_ngrams(query)
        lexical_scores = [
            self._lexical_score(
                query,
                query_tokens,
                query_ngrams,
                text,
                token_set,
                document_frequency,
                total_documents,
            )
            for (_, _, _, text), token_set in zip(documents, document_tokens)
        ]

        max_embedding_items = max(5, min(int(os.getenv("MEMORY_EMBEDDING_MAX_ITEMS", "48")), 200))
        embedding_positions = self._embedding_positions(documents, lexical_scores, max_embedding_items)
        embedding_inputs = [query, *[documents[position][3] for position in embedding_positions]]
        vectors = self._embedder(embedding_inputs)
        semantic_scores: dict[int, float] | None = None
        if vectors and len(vectors) == len(embedding_inputs):
            semantic_scores = {
                position: _cosine(vectors[0], vector)
                for position, vector in zip(embedding_positions, vectors[1:])
            }

        min_lexical = max(0.02, min(float(os.getenv("MEMORY_RETRIEVAL_MIN_LEXICAL_SCORE", "0.12")), 1.0))
        min_semantic = max(0.0, min(float(os.getenv("MEMORY_RETRIEVAL_MIN_SEMANTIC_SIMILARITY", "0.48")), 0.99))
        ranked: dict[str, list[tuple[float, int, dict[str, Any]]]] = {name: [] for name in groups}
        for position, (group_name, index, item, _) in enumerate(documents):
            lexical = lexical_scores[position]
            semantic = semantic_scores.get(position, 0.0) if semantic_scores is not None else 0.0
            if lexical < min_lexical and semantic < min_semantic:
                continue
            recency = 0.025 / (index + 1)
            if semantic_scores is None or position not in semantic_scores:
                final_score = lexical + recency
            else:
                semantic_scaled = max(0.0, (semantic - min_semantic) / (1.0 - min_semantic))
                final_score = 0.62 * semantic_scaled + 0.38 * lexical + recency
            confidence = clamp_score(item.get("confidence"), 1.0)
            importance = clamp_score(item.get("importance"), 0.50)
            final_score *= 0.55 + 0.25 * confidence + 0.20 * importance
            ranked[group_name].append((final_score, -index, item))

        selected: dict[str, list[dict[str, Any]]] = {}
        for group_name, (_, _, limit) in groups.items():
            rows = sorted(ranked[group_name], key=lambda row: (row[0], row[1]), reverse=True)
            selected[group_name] = [item for _, _, item in rows[:limit]]
        return selected, "hybrid_semantic" if semantic_scores is not None else "hybrid_lexical"

    @staticmethod
    def _embedding_positions(
        documents: list[tuple[str, int, dict[str, Any], str]],
        lexical_scores: list[float],
        limit: int,
    ) -> list[int]:
        """Prefilter a fair cross-store batch before expensive semantic scoring."""
        by_group: dict[str, list[int]] = {}
        for position, (group_name, _, _, _) in enumerate(documents):
            by_group.setdefault(group_name, []).append(position)
        per_group = max(2, limit // max(1, len(by_group)))
        selected: list[int] = []
        for positions in by_group.values():
            positions.sort(
                key=lambda position: (lexical_scores[position], -documents[position][1]),
                reverse=True,
            )
            selected.extend(positions[:per_group])
        selected = list(dict.fromkeys(selected))
        if len(selected) < limit:
            remaining = [position for position in range(len(documents)) if position not in selected]
            remaining.sort(
                key=lambda position: (lexical_scores[position], -documents[position][1]),
                reverse=True,
            )
            selected.extend(remaining[:limit - len(selected)])
        return selected[:limit]

    @staticmethod
    def _lexical_score(
        query: str,
        query_tokens: set[str],
        query_ngrams: set[str],
        document: str,
        document_tokens: set[str],
        document_frequency: Counter[str],
        total_documents: int,
    ) -> float:
        shared = query_tokens & document_tokens
        all_tokens = query_tokens | document_tokens
        idf_shared = sum(math.log((total_documents + 1) / (document_frequency[token] + 1)) + 1 for token in shared)
        idf_query = sum(math.log((total_documents + 1) / (document_frequency.get(token, 0) + 1)) + 1 for token in query_tokens)
        coverage = idf_shared / idf_query if idf_query else 0.0
        jaccard = len(shared) / len(all_tokens) if all_tokens else 0.0

        document_ngrams = _char_ngrams(document)
        ngram_union = query_ngrams | document_ngrams
        ngram_score = len(query_ngrams & document_ngrams) / len(ngram_union) if ngram_union else 0.0
        normalized_query = normalize(query).strip()
        normalized_document = normalize(document)
        phrase = 1.0 if len(normalized_query) >= 4 and normalized_query in normalized_document else 0.0
        return min(1.0, 0.48 * coverage + 0.22 * jaccard + 0.22 * ngram_score + 0.08 * phrase)


memory_retriever = HybridMemoryRetriever()
