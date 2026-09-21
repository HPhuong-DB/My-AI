"""Application-level coordination for Huohuo's memory stores.

Low-level services remain responsible for their own tables.  This module owns
the order in which a conversation is persisted, how prompt context is recalled,
and the public operations used to update or forget memories.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Any, Mapping

from services.chat_service import get_recent_chat_history, save_chat_message
from services.dialogue_context_service import (
    DialoguePrompt,
    asks_user_name,
    build_dialogue_context,
    is_simple_greeting,
    normalize,
    tokens,
)
from services.memory_retrieval_service import memory_retriever
from services.memory_service import (
    DEFAULT_USER_ID,
    delete_memory,
    get_recent_memories,
    list_memory_audit,
    get_user_mood_timeline,
    get_user_profile,
    save_memory,
    save_memory_from_conversation,
    update_memory,
)


@dataclass(frozen=True, slots=True)
class PromptMemoryContext:
    """The bounded memory snapshot supplied to one model generation."""

    prompt: DialoguePrompt
    profile: Mapping[str, Any] | None
    history_count: int
    memory_candidate_count: int
    knowledge_candidate_count: int = 0
    experience_candidate_count: int = 0
    knowledge_recall_count: int = 0
    experience_recall_count: int = 0
    session_candidate_count: int = 0
    session_recall_count: int = 0
    episode_candidate_count: int = 0
    episode_recall_count: int = 0
    retrieval_mode: str = "rules"
    runtime_context: Mapping[str, Any] | None = None


class MemoryOrchestrator:
    """Coordinate memory writes, recall, consolidation and forgetting.

    Methods are synchronous because the underlying MySQL repositories are
    synchronous. API callers run them with ``asyncio.to_thread``.
    """

    def __init__(
        self,
        *,
        archive_candidate_limit: int | None = None,
        archive_recall_limit: int | None = None,
    ) -> None:
        self._archive_candidate_limit_override = archive_candidate_limit
        self._archive_recall_limit_override = archive_recall_limit

    def consolidate_user_message(
        self,
        user_id: str,
        user_message: str,
        assistant_reply: str = "",
        *,
        strict: bool = True,
    ) -> None:
        """Extract durable facts and relationship signals from one user turn."""
        save_memory_from_conversation(
            user_message,
            assistant_reply,
            user_id,
            strict=strict,
        )

    def prepare_user_turn(self, user_id: str, user_message: str) -> None:
        """Consolidate new facts before persisting the user transcript.

        A changed fact first excludes its proven source turns, then the new
        message is stored, so unrelated history and the current turn remain
        visible to recall. Legacy facts without provenance retain cutoff safety.
        """
        self.consolidate_user_message(user_id, user_message, strict=True)
        save_chat_message("user", user_message, user_id, strict=True)

    def record_assistant_message(
        self,
        user_id: str,
        reply: str,
        *,
        user_message: str = "",
    ) -> None:
        """Persist a validated reply, then update optional conversation memory."""
        assistant_chat_id = save_chat_message("assistant", reply, user_id, strict=True)
        if user_message and isinstance(assistant_chat_id, int) and not isinstance(assistant_chat_id, bool):
            from services.conversation_memory_service import record_completed_turn

            # The chat transcript is the required record. A transient failure in
            # these derived indexes must not turn a valid reply into a chat error.
            record_completed_turn(
                user_id,
                user_message,
                reply,
                assistant_chat_id,
                strict=False,
            )

    def recall_prompt(
        self,
        user_message: str,
        user_id: str = DEFAULT_USER_ID,
        *,
        history_limit: int,
        memory_limit: int,
        max_chars: int,
    ) -> PromptMemoryContext:
        """Build one bounded, user-scoped prompt memory snapshot."""
        history = get_recent_chat_history(
            limit=history_limit,
            user_id=user_id,
            strict=True,
        )
        memories = get_recent_memories(
            limit=memory_limit,
            user_id=user_id,
            strict=True,
        )
        profile = get_user_profile(user_id=user_id)
        runtime_context = self._runtime_context(user_id)
        knowledge: list[dict[str, Any]] = []
        experiences: list[dict[str, Any]] = []
        knowledge_candidates: list[dict[str, Any]] = []
        experience_candidates: list[dict[str, Any]] = []
        session_candidates: list[dict[str, Any]] = []
        episode_candidates: list[dict[str, Any]] = []
        session_summaries: list[dict[str, Any]] = []
        episodes: list[dict[str, Any]] = []
        selected_memories: list[dict[str, Any]] | None = None
        retrieval_mode = "rules"
        if self._should_recall_archives(user_message):
            knowledge_candidates, experience_candidates = self._load_archival_candidates(user_id)
            session_candidates, episode_candidates = self._load_conversation_candidates(user_id)
            archive_query = self._archive_recall_query(user_message, history)
            personal_always = [item for item in memories if item.get("memory_type") == "communication_style"]
            personal_candidates = [
                item for item in memories
                if item.get("memory_type") != "communication_style"
                and (item.get("memory_type") != "user_name" or asks_user_name(user_message))
            ]
            ranked, retrieval_mode = memory_retriever.rank_groups(archive_query, {
                "personal": (personal_candidates, ("memory_type", "fact"), max(0, 8 - len(personal_always))),
                "knowledge": (
                    knowledge_candidates,
                    ("query_text", "title", "summary", "key_points"),
                    self._archive_recall_limit(),
                ),
                "experiences": (
                    experience_candidates,
                    ("title", "lesson", "context"),
                    self._archive_recall_limit(),
                ),
                "sessions": (
                    session_candidates,
                    ("topics", "user_points"),
                    self._session_recall_limit(),
                ),
                "episodes": (
                    episode_candidates,
                    ("event_type", "title", "description"),
                    self._episode_recall_limit(),
                ),
            })
            selected_memories = (personal_always + ranked["personal"])[:8]
            knowledge = ranked["knowledge"]
            experiences = ranked["experiences"]
            session_summaries = ranked["sessions"]
            episodes = ranked["episodes"]
            if not session_summaries and self._asks_for_session_recall(user_message):
                session_summaries = session_candidates[:self._session_recall_limit()]
            if not episodes and self._asks_for_episode_recall(user_message):
                episodes = episode_candidates[:self._episode_recall_limit()]
        prompt = build_dialogue_context(
            user_message,
            history,
            memories,
            profile,
            max_chars=max_chars,
            runtime_context=runtime_context,
            knowledge=knowledge,
            experiences=experiences,
            session_summaries=session_summaries,
            episodes=episodes,
            selected_memories=selected_memories,
        )
        return PromptMemoryContext(
            prompt=prompt,
            profile=profile,
            history_count=len(history),
            memory_candidate_count=len(memories),
            knowledge_candidate_count=len(knowledge_candidates),
            experience_candidate_count=len(experience_candidates),
            knowledge_recall_count=len(knowledge),
            experience_recall_count=len(experiences),
            session_candidate_count=len(session_candidates),
            session_recall_count=len(session_summaries),
            episode_candidate_count=len(episode_candidates),
            episode_recall_count=len(episodes),
            retrieval_mode=retrieval_mode,
            runtime_context=runtime_context,
        )

    def _load_archival_candidates(
        self,
        user_id: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Load bounded knowledge and experience pools for one user."""
        # Lazy imports avoid a cycle: research_service imports llm_service,
        # while llm_service delegates prompt recall to this orchestrator.
        from services.knowledge_service import list_experiences
        from services.research_service import list_knowledge

        limit = self._archive_candidate_limit()
        return list_knowledge(user_id, limit), list_experiences(user_id, limit)

    def _load_conversation_candidates(
        self,
        user_id: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        from services.conversation_memory_service import load_conversation_memory

        return load_conversation_memory(
            user_id,
            session_limit=self._session_candidate_limit(),
            episode_limit=self._episode_candidate_limit(),
        )

    @staticmethod
    def _has_realtime_search_evidence(message: str) -> bool:
        """Do not mix potentially stale archive facts into a live-search turn."""
        return "[TRA CỨU THỜI GIAN THỰC" in str(message or "").upper()

    @classmethod
    def _should_recall_archives(cls, message: str) -> bool:
        current = str(message or "").split("\n\n[TRA CỨU", 1)[0].strip()
        return bool(tokens(current)) and not is_simple_greeting(current) and not cls._has_realtime_search_evidence(message)

    @staticmethod
    def _archive_recall_query(message: str, history: list[dict[str, Any]]) -> str:
        """Expand vague follow-ups with recent user words, never assistant claims."""
        current = str(message or "").split("\n\n[TRA CỨU", 1)[0].strip()
        normalized = normalize(current)
        vague_follow_up = bool(
            re.search(
                r"\b(tiep|them|do|no|cai nay|viec nay|van de nay|y do|vay|the nao|con sao)\b",
                normalized,
            )
        )
        if not vague_follow_up:
            return current

        previous_user_messages: list[str] = []
        for item in reversed(history):
            if item.get("role") != "user":
                continue
            content = str(item.get("content") or "").strip()
            if not content or content == current:
                continue
            previous_user_messages.append(content)
            if len(previous_user_messages) == 2:
                break
        return " ".join([current, *reversed(previous_user_messages)]).strip()

    @staticmethod
    def _asks_for_session_recall(message: str) -> bool:
        value = normalize(str(message or "").split("\n\n[TRA CỨU", 1)[0])
        return bool(re.search(r"\b(phien truoc|lan truoc|vua noi|noi gi|dang noi|cau chuyen truoc)\b", value))

    @staticmethod
    def _asks_for_episode_recall(message: str) -> bool:
        value = normalize(str(message or "").split("\n\n[TRA CỨU", 1)[0])
        return bool(re.search(r"\b(ky niem|su kien|chuyen hom truoc|da xay ra|nho chuyen)\b", value))

    @staticmethod
    def _select_archival_items(
        query: str,
        candidates: list[dict[str, Any]],
        *,
        fields: tuple[str, ...],
        limit: int,
    ) -> list[dict[str, Any]]:
        """Compatibility wrapper around the shared hybrid retriever."""
        selected, _ = memory_retriever.rank_groups(
            query,
            {"items": (candidates, fields, limit)},
        )
        return selected["items"]

    def _archive_candidate_limit(self) -> int:
        value = self._archive_candidate_limit_override
        if value is None:
            value = int(os.getenv("MEMORY_ARCHIVAL_CANDIDATE_LIMIT", "40"))
        return max(1, min(int(value), 50))

    def _archive_recall_limit(self) -> int:
        value = self._archive_recall_limit_override
        if value is None:
            value = int(os.getenv("MEMORY_ARCHIVAL_RECALL_LIMIT", "3"))
        return max(0, min(int(value), 8))

    @staticmethod
    def _session_candidate_limit() -> int:
        return max(1, min(int(os.getenv("SESSION_SUMMARY_CANDIDATE_LIMIT", "10")), 50))

    @staticmethod
    def _session_recall_limit() -> int:
        return max(0, min(int(os.getenv("SESSION_SUMMARY_RECALL_LIMIT", "2")), 5))

    @staticmethod
    def _episode_candidate_limit() -> int:
        return max(1, min(int(os.getenv("EPISODIC_MEMORY_CANDIDATE_LIMIT", "40")), 100))

    @staticmethod
    def _episode_recall_limit() -> int:
        return max(0, min(int(os.getenv("EPISODIC_MEMORY_RECALL_LIMIT", "3")), 8))

    def recall_proactive_evidence(
        self,
        user_id: str = DEFAULT_USER_ID,
        *,
        history_limit: int = 8,
        memory_limit: int = 200,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Read a consistent user-scoped evidence pair for proactive decisions."""
        history = get_recent_chat_history(
            limit=history_limit,
            user_id=user_id,
            strict=True,
        )
        memories = get_recent_memories(
            limit=memory_limit,
            user_id=user_id,
            strict=True,
        )
        return history, memories

    def recall_history(
        self,
        user_id: str = DEFAULT_USER_ID,
        *,
        limit: int = 15,
        for_context: bool = True,
        strict: bool = True,
    ) -> list[dict[str, Any]]:
        """Read a bounded transcript through the shared memory boundary."""
        return get_recent_chat_history(
            limit=limit,
            user_id=user_id,
            for_context=for_context,
            strict=strict,
        )

    def recall_long_term(
        self,
        user_id: str = DEFAULT_USER_ID,
        query: str = "",
        limit: int = 10,
    ) -> dict[str, Any]:
        """Recall the existing personal, knowledge and experience stores."""
        # Lazy import avoids a module cycle: research_service uses llm_service,
        # while llm_service delegates prompt recall to this orchestrator.
        from services.knowledge_service import get_long_term_memory

        return get_long_term_memory(user_id, query, limit)

    def personal_snapshot(
        self,
        user_id: str = DEFAULT_USER_ID,
        *,
        memory_limit: int = 100,
        mood_limit: int = 20,
    ) -> dict[str, Any]:
        """Return the editable personal-memory view used by the UI."""
        return {
            "user_id": user_id,
            "profile": get_user_profile(user_id=user_id),
            "mood_timeline": get_user_mood_timeline(
                user_id=user_id,
                limit=mood_limit,
            ),
            "memories": get_recent_memories(
                limit=memory_limit,
                user_id=user_id,
                strict=True,
            ),
        }

    def conversation_snapshot(
        self,
        user_id: str = DEFAULT_USER_ID,
        *,
        session_limit: int = 10,
        episode_limit: int = 40,
    ) -> dict[str, Any]:
        """Return inspectable session summaries and episodic memories."""
        from services.conversation_memory_service import load_conversation_memory

        sessions, episodes = load_conversation_memory(
            user_id,
            session_limit=session_limit,
            episode_limit=episode_limit,
            strict=True,
        )
        return {"user_id": user_id, "sessions": sessions, "episodes": episodes}

    def remember(
        self,
        memory_type: str,
        fact: str,
        user_id: str = DEFAULT_USER_ID,
        *,
        confidence: float = 0.90,
        importance: float | None = None,
        source_type: str = "conversation",
        source_ref: str | None = None,
        expires_at: Any = None,
        strict: bool = False,
    ) -> bool:
        """Write a validated personal fact through the central memory boundary."""
        return bool(save_memory(
            memory_type,
            fact,
            user_id,
            confidence=confidence,
            importance=importance,
            source_type=source_type,
            source_ref=source_ref,
            expires_at=expires_at,
            strict=strict,
        ))

    def remember_experience(
        self,
        user_id: str,
        title: str,
        lesson: str,
        context: str = "",
        source_type: str = "goal",
        source_id: int | None = None,
        *,
        source_ref: str | None = None,
        confidence: float = 0.80,
        importance: float = 0.75,
        expires_at: Any = None,
    ) -> dict[str, Any] | None:
        from services.knowledge_service import save_experience

        return save_experience(
            user_id,
            title,
            lesson,
            context,
            source_type,
            source_id,
            source_ref=source_ref,
            confidence=confidence,
            importance=importance,
            expires_at=expires_at,
        )

    def remember_knowledge(
        self,
        user_id: str,
        query: str,
        title: str,
        summary: str,
        key_points: list[str],
        sources: list[dict[str, Any]],
        *,
        confidence: float = 0.75,
        importance: float = 0.60,
        source_type: str = "research",
        source_ref: str | None = None,
        expires_at: Any = None,
    ) -> dict[str, Any] | None:
        from services.research_service import save_knowledge

        return save_knowledge(
            user_id,
            query,
            title,
            summary,
            key_points,
            sources,
            confidence=confidence,
            importance=importance,
            source_type=source_type,
            source_ref=source_ref,
            expires_at=expires_at,
        )

    def update(self, memory_id: int, fact: str, user_id: str = DEFAULT_USER_ID) -> bool:
        """Update one active personal memory and invalidate dependent context."""
        return bool(update_memory(memory_id, fact, user_id))

    def forget(self, memory_id: int, user_id: str = DEFAULT_USER_ID) -> bool:
        """Forget one active personal memory through the existing safe delete path."""
        return bool(delete_memory(memory_id, user_id))

    def maintain(self, user_id: str | None = None, *, strict: bool = False) -> dict[str, Any]:
        """Apply bounded forgetting policies without touching unexpired memories."""
        from services.memory_forgetting_service import forget_expired_memories

        return forget_expired_memories(user_id, strict=strict)

    def audit(self, user_id: str = DEFAULT_USER_ID, *, limit: int = 100) -> list[dict[str, Any]]:
        """Inspect active, superseded and expired personal memories."""
        return list_memory_audit(user_id, limit)

    @staticmethod
    def _runtime_context(user_id: str) -> Mapping[str, Any] | None:
        """Read only a bounded runtime snapshot; persistence must not depend on it."""
        try:
            from agent.runtime import context_manager

            snapshot = context_manager.get(user_id)
            if snapshot is None:
                return None
            return {
                "mood": snapshot.mood,
                "energy": snapshot.energy,
                "activity": snapshot.activity,
                "attention": snapshot.attention,
                "current_topic": snapshot.current_topic,
                "last_input_source": snapshot.last_input_source,
                "last_input_type": snapshot.last_input_type,
            }
        except (AttributeError, ImportError, RuntimeError):
            # Runtime context is temporary supporting evidence. Durable memory
            # and chat history remain available if the autonomous loop is off.
            return None


memory_orchestrator = MemoryOrchestrator()
