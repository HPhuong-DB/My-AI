import asyncio
import json

from google.genai import types

from services.llm_service import MODEL_NAME, client


VISION_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "STRING"},
        "visible_elements": {"type": "ARRAY", "items": {"type": "STRING"}},
        "detected_text": {"type": "STRING"},
        "confidence": {"type": "NUMBER"},
    },
    "required": ["summary", "visible_elements", "detected_text", "confidence"],
}


async def generate_image_analysis(
    image_bytes: bytes,
    mime_type: str,
    question: str,
    ocr_text: str = "",
) -> dict:
    """Return structured visual analysis instead of an unvalidated text blob."""
    if client is None:
        raise RuntimeError("Chưa cấu hình GEMINI_API_KEY")

    prompt = f"""
Bạn là Huohuo, hãy phân tích ảnh bằng tiếng Việt.
Câu hỏi của người dùng: {question}
OCR tham khảo, có thể sai: {ocr_text or "Không có"}

Chỉ mô tả những gì chắc chắn nhìn thấy. Không suy đoán danh tính, địa chỉ,
thông tin riêng tư hoặc chi tiết không có trong ảnh. Trả về đúng JSON theo schema.
"""

    def request_vision():
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[types.Part.from_bytes(data=image_bytes, mime_type=mime_type), prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=VISION_RESPONSE_SCHEMA,
            ),
        )
        return response.text or "{}"

    raw = await asyncio.wait_for(asyncio.to_thread(request_vision), timeout=45.0)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError("Vision trả về JSON không hợp lệ") from error

    try:
        confidence = max(0.0, min(1.0, float(result.get("confidence", 0))))
    except (TypeError, ValueError):
        confidence = 0.0
    elements = result.get("visible_elements")
    return {
        "summary": str(result.get("summary") or "Huohuo chưa nhận xét được ảnh này.").strip(),
        "visible_elements": [str(item).strip() for item in elements if str(item).strip()] if isinstance(elements, list) else [],
        "detected_text": str(result.get("detected_text") or ocr_text or "").strip(),
        "confidence": confidence,
    }


async def generate_image_comment(
    image_bytes: bytes,
    mime_type: str,
    question: str,
    ocr_text: str = "",
) -> str:
    if client is None:
        raise RuntimeError("Chưa cấu hình GEMINI_API_KEY")

    prompt = f"""
Bạn là Huohuo, hãy trả lời bằng tiếng Việt, tự nhiên và ngắn gọn.
Câu hỏi của người dùng: {question}

Nếu ảnh có chữ, hãy giải thích hoặc dịch phần chữ đó khi phù hợp.
Kết quả OCR tham khảo (có thể sai): {ocr_text or "Không có"}
Hãy mô tả những gì nhìn thấy trong ảnh, không bịa thêm chi tiết không chắc chắn.
"""

    def request_vision():
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                prompt,
            ],
        )
        return response.text or "Huohuo chưa nhận xét được ảnh này."

    return await asyncio.wait_for(asyncio.to_thread(request_vision), timeout=45.0)
