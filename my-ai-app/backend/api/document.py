"""Document perception endpoint."""

import os

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from agent import Event, EventType, PerceptionContentType, PerceptionInput, PerceptionSource, create_perception_event
from agent.runtime import event_bus, output_bus, privacy_manager
from services.document_service import chunk_text, extract_document

router = APIRouter()
MAX_DOCUMENT_BYTES = int(os.getenv("DOCUMENT_MAX_UPLOAD_BYTES", 10 * 1024 * 1024))
ALLOWED_DOCUMENT_TYPES = {
    "text/plain", "text/markdown", "text/csv", "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@router.post("/perception/document")
async def read_document(
    document: UploadFile = File(...),
    user_id: str = Form("default"),
    question: str = Form("Hãy tóm tắt tài liệu này."),
):
    if not user_id.strip() or len(user_id) > 100:
        raise HTTPException(status_code=400, detail="user_id không hợp lệ")
    if document.content_type not in ALLOWED_DOCUMENT_TYPES:
        raise HTTPException(status_code=415, detail="Định dạng tài liệu không được hỗ trợ")
    contents = await document.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Tài liệu rỗng")
    if len(contents) > MAX_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="Tài liệu vượt quá giới hạn 10 MB")

    try:
        privacy_manager.record_capture(user_id, "document", document_type=(document.filename or "").rsplit(".", 1)[-1].lower())
        await output_bus.publish(
            Event.create(
                EventType.PERCEPTION_STARTED,
                user_id=user_id,
                payload={"source": PerceptionSource.DOCUMENT, "filename": document.filename or "document"},
            )
        )
        result = await run_in_threadpool(extract_document, contents, document.filename or "document")
        chunks = chunk_text(result.text)
        perception = PerceptionInput(
            source=PerceptionSource.DOCUMENT,
            content_type=PerceptionContentType.DOCUMENT,
            content=result.text[:4000] or question[:1000],
            asset_ref=f"document:{result.filename}",
            confidence=1.0,
            metadata={"document_type": result.document_type, "chunk_count": len(chunks)},
        )
        await event_bus.publish(create_perception_event(perception, user_id=user_id))
        payload = {**result.to_dict(), "chunks": chunks}
        await output_bus.publish(
            Event.create(EventType.PERCEPTION_COMPLETED, user_id=user_id, payload=payload)
        )
        return payload
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=501, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Lỗi đọc tài liệu: {error}") from error
