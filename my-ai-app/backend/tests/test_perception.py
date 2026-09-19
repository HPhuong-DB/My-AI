import unittest
from datetime import datetime, timezone

from agent import (
    AgentActivity,
    PerceptionContentType,
    PerceptionInput,
    PerceptionSource,
    StateManager,
    create_perception_event,
    parse_perception_event,
)
from services.ocr_service import validate_image
from services.perception_service import ImagePerceptionResult, image_perception_input


class PerceptionTests(unittest.TestCase):
    def test_creates_and_parses_normalized_speech_event(self):
        perception = PerceptionInput(
            source=PerceptionSource.MICROPHONE,
            content_type=PerceptionContentType.SPEECH,
            content="Mình đang mệt",
            confidence=0.94,
            metadata={"language": "vi-VN"},
            captured_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
        )
        event = create_perception_event(perception, user_id="user-1")
        parsed = parse_perception_event(event)
        self.assertEqual(event.type, "perception_input")
        self.assertEqual(event.user_id, "user-1")
        self.assertEqual(parsed.source, PerceptionSource.MICROPHONE)
        self.assertEqual(parsed.metadata["language"], "vi-VN")

    def test_supports_binary_asset_by_reference(self):
        perception = PerceptionInput(PerceptionSource.SCREEN, PerceptionContentType.SCREENSHOT, asset_ref="screen.png")
        self.assertEqual(perception.to_payload()["asset_ref"], "screen.png")

    def test_rejects_invalid_or_empty_perception(self):
        with self.assertRaises(ValueError):
            PerceptionInput("camera", PerceptionContentType.IMAGE, content="x")
        with self.assertRaises(ValueError):
            PerceptionInput(PerceptionSource.IMAGE, PerceptionContentType.IMAGE, confidence=1.5)
        with self.assertRaises(ValueError):
            PerceptionInput(PerceptionSource.IMAGE, PerceptionContentType.IMAGE)

    def test_perception_updates_agent_context(self):
        perception = PerceptionInput(PerceptionSource.IMAGE, PerceptionContentType.IMAGE, asset_ref="photo.png", confidence=0.8)
        state = StateManager().apply_event(create_perception_event(perception, user_id="user-1"))
        self.assertEqual(state.activity, AgentActivity.THINKING)
        self.assertEqual(state.metadata["last_perception_source"], "image")

    def test_ocr_service_rejects_invalid_bytes(self):
        with self.assertRaises(ValueError):
            validate_image(b"not-an-image")

    def test_image_result_can_be_converted_to_normalized_input(self):
        result = ImagePerceptionResult(
            source=PerceptionSource.IMAGE,
            content_type=PerceptionContentType.IMAGE,
            ocr={"text": "Xin chào", "score": 0.7, "variants": []},
            vision_comment="Một tấm ảnh có chữ.",
            vision_analysis={"summary": "Một tấm ảnh có chữ.", "confidence": 0.9},
            width=100,
            height=80,
        )
        perception = image_perception_input(result, asset_ref="upload:photo.png")

        self.assertEqual(perception.content, "Một tấm ảnh có chữ.")
        self.assertEqual(perception.asset_ref, "upload:photo.png")
        self.assertEqual(perception.metadata["width"], 100)

    def test_screen_result_preserves_screen_source(self):
        result = ImagePerceptionResult(
            source=PerceptionSource.SCREEN,
            content_type=PerceptionContentType.SCREENSHOT,
            ocr={"text": "Terminal", "score": 0.6, "variants": []},
            vision_comment="Một cửa sổ terminal.",
            vision_analysis={"summary": "Một cửa sổ terminal.", "confidence": 0.8},
            width=1280,
            height=720,
        )
        perception = image_perception_input(result, asset_ref="screen:capture.png")
        self.assertEqual(perception.source, PerceptionSource.SCREEN)
        self.assertEqual(perception.content_type, PerceptionContentType.SCREENSHOT)
