"""Relationship state derived from the user-scoped profile."""

from __future__ import annotations

from typing import Any

from services.memory_service import get_relationship_tone, get_user_profile


def _stage(affection_level: int) -> tuple[str, str]:
    if affection_level <= 0:
        return "new", "Mới gặp, nên giữ khoảng cách lịch sự."
    if affection_level <= 3:
        return "familiar", "Đã quen, có thể nói chuyện thân thiện và ôn hòa."
    if affection_level <= 6:
        return "close", "Đã khá thân, có thể cá nhân hóa phản hồi tự nhiên hơn."
    if affection_level <= 9:
        return "trusted", "Có mức tin tưởng tốt, nên giữ sự ấm áp và quan tâm."
    return "very_close", "Rất thân, nhưng vẫn phải tôn trọng ranh giới của người dùng."


def get_relationship(user_id: str = "default") -> dict[str, Any]:
    profile = get_user_profile(user_id=user_id)
    if not profile:
        affection_level = 0
        stage, guidance = _stage(affection_level)
        return {
            "user_id": user_id,
            "username": None,
            "affection_level": affection_level,
            "stage": stage,
            "guidance": guidance,
            "tone": get_relationship_tone(affection_level),
            "interaction_count": 0,
            "last_interaction": None,
        }

    affection_level = max(0, min(10, int(profile.get("affection_level") or 0)))
    stage, guidance = _stage(affection_level)
    return {
        "user_id": user_id,
        "username": profile.get("username"),
        "affection_level": affection_level,
        "stage": stage,
        "guidance": guidance,
        "tone": get_relationship_tone(affection_level),
        "interaction_count": int(profile.get("interaction_count") or 0),
        "last_interaction": profile.get("last_interaction"),
        "mood": profile.get("mood") or "neutral",
    }
