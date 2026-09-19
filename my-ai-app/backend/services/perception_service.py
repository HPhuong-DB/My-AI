"""Orchestration layer for OCR and multimodal vision perception."""

from dataclasses import dataclass

from fastapi.concurrency import run_in_threadpool

from agent import PerceptionContentType, PerceptionInput, PerceptionSource
from services.ocr_service import extract_ocr, validate_image


@dataclass(frozen=True, slots=True)
class ImagePerceptionResult:
    source: str
    content_type: str
    ocr: dict
    vision_comment: str | None
    vision_analysis: dict | None
    width: int
    height: int

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "content_type": self.content_type,
            "ocr": self.ocr,
            "vision_comment": self.vision_comment,
            "vision_analysis": self.vision_analysis,
            "width": self.width,
            "height": self.height,
        }


async def analyze_image(
    image_bytes: bytes,
    *,
    mime_type: str,
    question: str = "Nhận xét nội dung bức ảnh và giải thích chữ nếu có.",
    run_ocr: bool = True,
    run_vision: bool = True,
    ocr_text: str = "",
    source: str = PerceptionSource.IMAGE,
    content_type: str = PerceptionContentType.IMAGE,
) -> ImagePerceptionResult:
    """Run OCR and Vision through one consistent image-perception entrypoint."""
    width, height = await run_in_threadpool(validate_image, image_bytes)
    ocr_result = {"text": ocr_text, "score": 0.0, "variants": []}
    if run_ocr and not ocr_text:
        ocr_result = await run_in_threadpool(extract_ocr, image_bytes)

    vision_comment = None
    vision_analysis = None
    if run_vision:
        from services.vision_service import generate_image_analysis

        vision_analysis = await generate_image_analysis(
            image_bytes=image_bytes,
            mime_type=mime_type,
            question=question[:1000],
            ocr_text=(ocr_text or ocr_result.get("text", ""))[:4000],
        )
        vision_comment = vision_analysis["summary"]

    return ImagePerceptionResult(
        source=source,
        content_type=content_type,
        ocr=ocr_result,
        vision_comment=vision_comment,
        vision_analysis=vision_analysis,
        width=width,
        height=height,
    )


def image_perception_input(result: ImagePerceptionResult, *, asset_ref: str) -> PerceptionInput:
    """Build the normalized perception payload for a completed image analysis."""
    return PerceptionInput(
        source=result.source,
        content_type=result.content_type,
        content=result.vision_comment or result.ocr.get("text") or None,
        asset_ref=asset_ref,
        confidence=(result.vision_analysis or {}).get("confidence") or result.ocr.get("score"),
        metadata={"width": result.width, "height": result.height},
    )
