"""Context-aware, non-repetitive messages for proactive interaction."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any


class NaturalInteractionEngine:
    """Choose short prompts from bounded templates instead of repeating one line."""

    def __init__(self, *, history_size: int = 5) -> None:
        self.history_size = max(1, int(history_size))
        self._recent_messages: dict[str, deque[str]] = defaultdict(
            lambda: deque(maxlen=self.history_size)
        )

    def _choose(self, user_id: str, candidates: list[str]) -> str:
        recent = self._recent_messages[user_id]
        for candidate in candidates:
            if candidate not in recent:
                recent.append(candidate)
                return candidate
        selected = candidates[len(recent) % len(candidates)]
        recent.append(selected)
        return selected

    def idle_message(self, user_id: str, *, mood: str = "neutral", stage: str = "new") -> str:
        if mood == "sad":
            candidates = [
                "Mình ở đây nhé. Hôm nay bạn thấy trong lòng thế nào rồi?",
                "Bạn không cần phải cố tỏ ra ổn đâu. Mình ngồi đây với bạn một chút nhé?",
            ]
        elif mood == "stressed":
            candidates = [
                "Có vẻ bạn đã khá áp lực rồi. Mình cùng chọn một việc nhỏ để xử lý nhé?",
                "Mình nhắc nhẹ thôi: bạn muốn nghỉ một chút hay cùng mình gỡ một việc đang vướng?",
            ]
        elif mood == "happy":
            candidates = [
                "Hôm nay có vẻ tâm trạng bạn khá tốt nhỉ. Có chuyện vui gì muốn kể mình nghe không?",
                "Mình vẫn ở đây nè. Bạn muốn tiếp tục việc đang làm hay kể mình nghe một chuyện vui?",
            ]
        elif stage in {"close", "trusted", "very_close"}:
            candidates = [
                "Bạn im lặng một lúc rồi đó. Mọi chuyện vẫn ổn chứ?",
                "Mình ghé qua hỏi thăm một chút thôi. Bạn đang làm gì vậy?",
            ]
        else:
            candidates = [
                "Bạn đã yên lặng một lúc rồi. Mọi việc vẫn ổn chứ?",
                "Mình vẫn ở đây nếu bạn muốn hỏi gì hoặc cần xử lý một việc nhỏ.",
            ]
        return self._choose(user_id, candidates)

    def progress_message(self, user_id: str, *, title: str, status: str, mood: str = "neutral") -> str:
        if status == "overdue":
            candidates = [
                f'Mục tiêu "{title}" đã quá hạn. Mình cùng lùi deadline hoặc chia nhỏ phần còn lại nhé?',
                f'Mình thấy "{title}" đang quá hạn. Bạn muốn xử lý bước nào trước?',
            ]
        elif status == "stalled":
            candidates = [
                f'Mục tiêu "{title}" đã lâu chưa cập nhật. Có trở ngại nào mình cùng tháo gỡ không?',
                f"Mình nhớ mục tiêu {title} vẫn đang chờ bạn. Cần mình giúp chia thành một bước nhỏ hơn không?",
            ]
        else:
            candidates = [
                f'Mục tiêu "{title}" đang chậm hơn kế hoạch. Mình làm bước nhỏ tiếp theo nhé?',
                f"Mình nhắc nhẹ về {title}: hôm nay bạn muốn tiến thêm một chút không?",
            ]
        if mood in {"sad", "stressed"}:
            candidates.insert(0, f'Mình không muốn tạo áp lực, nhưng "{title}" đang cần một bước nhỏ. Mình làm cùng nhau nhé?')
        return self._choose(user_id, candidates)

    def clear_user(self, user_id: str) -> None:
        self._recent_messages.pop(user_id, None)

    def stats(self) -> dict[str, Any]:
        return {"tracked_users": len(self._recent_messages), "history_size": self.history_size}
