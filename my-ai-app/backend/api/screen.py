"""On-demand screen capture analysis endpoint."""

import os

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from agent import Event, EventType, PerceptionContentType, PerceptionSource, create_perception_event
from agent.runtime import event_bus, output_bus, privacy_manager
from services.perception_service import analyze_image, image_perception_input

router = APIRouter()
MAX_SCREEN_BYTES = int(os.getenv("SCREEN_MAX_UPLOAD_BYTES", 5 * 1024 * 1024))
ALLOWED_SCREEN_TYPES = {"image/png", "image/jpeg", "image/webp"}


@router.post("/perception/screen")
async def analyze_screen(
    image: UploadFile = File(...),
    question: str = Form("Bạn đang làm gì trên màn hình? Hãy tóm tắt nội dung chính."),
    user_id: str = Form("default"),
):
    if not user_id.strip() or len(user_id) > 100:
        raise HTTPException(status_code=400, detail="user_id không hợp lệ")
    if not privacy_manager.require(user_id, "screen"):
        raise HTTPException(status_code=403, detail="Chưa được cấp quyền phân tích màn hình")
    if image.content_type not in ALLOWED_SCREEN_TYPES:
        raise HTTPException(status_code=415, detail="Định dạng ảnh màn hình không được hỗ trợ")

    contents = await image.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Ảnh màn hình rỗng")
    if len(contents) > MAX_SCREEN_BYTES:
        raise HTTPException(status_code=413, detail="Ảnh màn hình vượt quá giới hạn 5 MB")

    try:
        privacy_manager.record_capture(user_id, "screen", content_type=image.content_type)
        await output_bus.publish(
            Event.create(
                EventType.PERCEPTION_STARTED,
                user_id=user_id,
                payload={"source": PerceptionSource.SCREEN, "filename": image.filename or "capture"},
            )
        )
        result = await analyze_image(
            image_bytes=contents,
            mime_type=image.content_type,
            question=question[:1000],
            source=PerceptionSource.SCREEN,
            content_type=PerceptionContentType.SCREENSHOT,
        )
        perception = image_perception_input(
            result,
            asset_ref=f"screen:{image.filename or 'capture'}",
        )
        await event_bus.publish(create_perception_event(perception, user_id=user_id))
        await output_bus.publish(
            Event.create(
                EventType.PERCEPTION_COMPLETED,
                user_id=user_id,
                payload={"source": PerceptionSource.SCREEN, **result.to_dict()},
            )
        )
        return {
            "reply_vi": result.vision_comment or "Huohuo chưa đọc được màn hình này.",
            "ocr": result.ocr,
            "vision": result.vision_analysis,
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except TimeoutError as error:
        raise HTTPException(status_code=504, detail="Phân tích màn hình timeout") from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Phân tích màn hình lỗi: {error}") from error
