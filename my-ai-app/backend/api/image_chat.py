from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from agent import Event, EventType, create_perception_event
from agent.runtime import event_bus, output_bus, privacy_manager
from services.perception_service import analyze_image, image_perception_input

router = APIRouter()
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_DIMENSION = 4096
MAX_IMAGE_PIXELS = 16_000_000
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/bmp", "image/tiff"}


@router.post("/image-chat")
async def image_chat(
    image: UploadFile = File(...),
    question: str = Form("Nhận xét nội dung bức ảnh và giải thích chữ nếu có."),
    ocr_text: str = Form(""),
    user_id: str = Form("default"),
):
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=415, detail="Định dạng ảnh không được hỗ trợ")

    contents = await image.read()
    if not contents:
        raise HTTPException(status_code=400, detail="File ảnh rỗng")
    if len(contents) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="File ảnh vượt quá giới hạn 5 MB")

    try:
        privacy_manager.record_capture(user_id, "image", content_type=image.content_type)
        await output_bus.publish(
            Event.create(
                EventType.PERCEPTION_STARTED,
                user_id=user_id,
                payload={"source": "image", "filename": image.filename or "image"},
            )
        )
        result = await analyze_image(
            image_bytes=contents,
            mime_type=image.content_type,
            question=question,
            ocr_text=ocr_text,
            run_ocr=not bool(ocr_text),
        )
        await event_bus.publish(
            create_perception_event(
                image_perception_input(result, asset_ref=f"upload:{image.filename or 'image'}"),
                user_id=user_id,
            )
        )
        await output_bus.publish(
            Event.create(
                EventType.PERCEPTION_COMPLETED,
                user_id=user_id,
                payload=result.to_dict(),
            )
        )
        return {
            "reply_vi": result.vision_comment or "Huohuo chưa nhận xét được ảnh này.",
            "ocr": result.ocr,
            "vision": result.vision_analysis,
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except TimeoutError as error:
        raise HTTPException(status_code=504, detail="Gemini Vision timeout") from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Gemini Vision lỗi: {error}") from error
