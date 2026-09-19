"""Long-term mood analysis built from the persisted mood timeline."""

from __future__ import annotations

from collections import Counter
from typing import Any

from services.memory_service import get_user_mood_timeline, infer_relationship_state


MOOD_SCORES = {
    "happy": 1.0,
    "neutral": 0.0,
    "stressed": -0.6,
    "sad": -1.0,
}


class MoodManager:
    """Analyze mood signals without allowing callers to mutate history."""

    @staticmethod
    def analyze_message(message: str) -> dict[str, Any]:
        mood, affection_delta = infer_relationship_state(message)
        signal_strength = min(1.0, abs(affection_delta) / 3)
        return {
            "mood": mood,
            "signal_strength": round(signal_strength, 2),
            "affection_signal": affection_delta,
        }

    def summarize(
        self,
        user_id: str = "default",
        limit: int = 20,
        timeline: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 100))
        timeline = timeline if timeline is not None else get_user_mood_timeline(user_id=user_id, limit=safe_limit)
        moods = [str(item.get("mood") or "neutral") for item in timeline]
        counts = Counter(moods)
        scores = [MOOD_SCORES.get(mood, 0.0) for mood in moods]
        recent_size = max(1, len(scores) // 2)
        recent = scores[:recent_size]
        older = scores[recent_size:]
        recent_average = sum(recent) / len(recent) if recent else 0.0
        older_average = sum(older) / len(older) if older else recent_average
        delta = recent_average - older_average
        if len(older) == 0 or abs(delta) < 0.2:
            trend = "stable"
        elif delta > 0:
            trend = "improving"
        else:
            trend = "declining"
        dominant_mood = counts.most_common(1)[0][0] if counts else "neutral"
        stability = "stable" if counts and counts[dominant_mood] / len(moods) >= 0.6 else "variable"
        return {
            "user_id": user_id,
            "current_mood": moods[0] if moods else "neutral",
            "dominant_mood": dominant_mood,
            "trend": trend,
            "stability": stability,
            "sample_count": len(moods),
            "distribution": dict(counts),
            "recent_average": round(recent_average, 2),
            "timeline": timeline,
        }


mood_manager = MoodManager()
