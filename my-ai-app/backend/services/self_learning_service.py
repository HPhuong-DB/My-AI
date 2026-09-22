"""Bounded self-learning writes for knowledge and memory only."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any

from agent.state_manager import StateManager
from services.memory_orchestrator import memory_orchestrator


class SelfLearningError(ValueError):
    """Raised when a learning update violates the safe learning policy."""


class SelfLearningRateLimitError(SelfLearningError):
    """Raised when one user produces too many learning updates."""


class SelfLearningService:
    """Allow writes to approved memory stores, never to files or system state."""

    ALLOWED_TARGETS = frozenset({"memory", "knowledge", "experience"})
    BLOCKED_TARGETS = frozenset({
        "code", "config", "configuration", "filesystem", "permission",
        "permissions", "system", "system_permission", "tool", "shell",
    })

    def __init__(
        self,
        state_manager: StateManager,
        *,
        max_updates: int = 10,
        window_seconds: float = 3600,
        max_content_chars: int = 12000,
    ) -> None:
        if max_updates <= 0 or window_seconds <= 0 or max_content_chars <= 0:
            raise ValueError("Giới hạn self-learning không hợp lệ")
        self.state_manager = state_manager
        self.max_updates = int(max_updates)
        self.window_seconds = float(window_seconds)
        self.max_content_chars = int(max_content_chars)
        self._updates: dict[str, deque[float]] = defaultdict(deque)

    def _check_policy(self, user_id: str, target: str, title: str, content: str) -> None:
        normalized_target = target.strip().lower()
        if normalized_target in self.BLOCKED_TARGETS or normalized_target not in self.ALLOWED_TARGETS:
            raise SelfLearningError(
                "Self-learning chỉ được ghi vào memory, knowledge hoặc experience; "
                "không được sửa code, quyền hay cấu hình hệ thống."
            )
        if self.state_manager.emergency_stopped or self.state_manager.get_state(user_id).emergency_stopped:
            raise SelfLearningError("emergency_stop_enabled")
        if not title.strip() or not content.strip():
            raise SelfLearningError("title_and_content_required")
        if len(content) > self.max_content_chars:
            raise SelfLearningError("learning_content_too_large")

    def _check_rate(self, user_id: str) -> None:
        now = time.monotonic()
        updates = self._updates[user_id]
        while updates and now - updates[0] >= self.window_seconds:
            updates.popleft()
        if len(updates) >= self.max_updates:
            raise SelfLearningRateLimitError("self_learning_rate_limit_reached")
        updates.append(now)

    def learn(
        self,
        user_id: str,
        *,
        target: str,
        title: str,
        content: str,
        context: str = "",
        source_url: str = "",
    ) -> dict[str, Any]:
        target = str(target or "").strip().lower()
        title = str(title or "").strip()
        content = str(content or "").strip()
        context = str(context or "").strip()
        source_url = str(source_url or "").strip()
        self._check_policy(user_id, target, title, content)
        self._check_rate(user_id)

        if target == "memory":
            stored = memory_orchestrator.remember(
                "learned_fact",
                content,
                user_id,
                confidence=0.65,
                importance=0.60,
                source_type="self_learning",
                source_ref=source_url or title,
            )
        elif target == "experience":
            stored = memory_orchestrator.remember_experience(
                user_id,
                title,
                content,
                context,
                source_type="self_learning",
                source_ref=source_url or title,
                confidence=0.70,
                importance=0.65,
            )
        else:
            sources = [{"url": source_url, "title": title}] if source_url else []
            stored = memory_orchestrator.remember_knowledge(
                user_id,
                title,
                title,
                content,
                [content],
                sources,
                confidence=0.65,
                importance=0.60,
                source_type="self_learning",
                source_ref=source_url or title,
            )

        if stored is None or stored is False:
            return {"ok": False, "target": target, "error": "database_unavailable"}
        return {
            "ok": True,
            "target": target,
            "title": title,
            "stored": stored if target != "memory" else {"memory_type": "learned_fact", "fact": content},
            "policy": "knowledge_and_memory_only",
        }


def learning_policy() -> dict[str, Any]:
    """Expose the effective boundary for UI and audit consumers."""
    return {
        "allowed_targets": sorted(SelfLearningService.ALLOWED_TARGETS),
        "blocked_targets": sorted(SelfLearningService.BLOCKED_TARGETS),
        "code_changes_allowed": False,
        "system_permission_changes_allowed": False,
    }
