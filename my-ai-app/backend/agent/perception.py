"""Normalized input format for Huohuo's perception pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from agent.events import Event, EventType


class PerceptionSource:
    MICROPHONE = "microphone"
    IMAGE = "image"
    SCREEN = "screen"
    DOCUMENT = "document"
    OCR = "ocr"


class PerceptionContentType:
    SPEECH = "speech"
    IMAGE = "image"
    SCREENSHOT = "screenshot"
    DOCUMENT = "document"
    TEXT = "text"


VALID_SOURCES = frozenset({
    PerceptionSource.MICROPHONE,
    PerceptionSource.IMAGE,
    PerceptionSource.SCREEN,
    PerceptionSource.DOCUMENT,
    PerceptionSource.OCR,
})
VALID_CONTENT_TYPES = frozenset({
    PerceptionContentType.SPEECH,
    PerceptionContentType.IMAGE,
    PerceptionContentType.SCREENSHOT,
    PerceptionContentType.DOCUMENT,
    PerceptionContentType.TEXT,
})


@dataclass(frozen=True, slots=True)
class PerceptionInput:
    """Source-agnostic perception data carried inside an Event payload."""

    source: str
    content_type: str
    content: str | None = None
    asset_ref: str | None = None
    confidence: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.source not in VALID_SOURCES:
            raise ValueError(f"Perception source không hợp lệ: {self.source}")
        if self.content_type not in VALID_CONTENT_TYPES:
            raise ValueError(f"Perception content_type không hợp lệ: {self.content_type}")
        if self.content is None and self.asset_ref is None:
            raise ValueError("Perception cần content hoặc asset_ref")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("Perception confidence phải nằm trong khoảng 0 đến 1")
        if self.captured_at.tzinfo is None:
            raise ValueError("Perception captured_at phải có timezone")

    def to_payload(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "content_type": self.content_type,
            "content": self.content,
            "asset_ref": self.asset_ref,
            "confidence": self.confidence,
            "metadata": dict(self.metadata),
            "captured_at": self.captured_at.isoformat(),
        }


def create_perception_event(perception: PerceptionInput, *, user_id: str = "default") -> Event:
    return Event.create(EventType.PERCEPTION_INPUT, user_id=user_id, payload=perception.to_payload())


def parse_perception_event(event: Event) -> PerceptionInput:
    if event.type != EventType.PERCEPTION_INPUT:
        raise ValueError("Event không phải perception_input")
    payload = event.payload
    captured_at = payload.get("captured_at")
    if isinstance(captured_at, str):
        captured_at = datetime.fromisoformat(captured_at)
    return PerceptionInput(
        source=str(payload.get("source", "")),
        content_type=str(payload.get("content_type", "")),
        content=payload.get("content"),
        asset_ref=payload.get("asset_ref"),
        confidence=payload.get("confidence"),
        metadata=payload.get("metadata") or {},
        captured_at=captured_at or event.created_at,
    )
