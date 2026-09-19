import os

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from services.ocr_service import extract_ocr

router = APIRouter()
MAX_UPLOAD_BYTES = int(os.getenv("OCR_MAX_UPLOAD_BYTES", "5242880"))  # 5 MB
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/bmp", "image/tiff"}


@router.post("/ocr")
async def ocr_screen(image: UploadFile = File(...)):
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=415, detail="Định dạng ảnh không được hỗ trợ")
    contents = await image.read()
    if not contents:
        raise HTTPException(status_code=400, detail="File ảnh rỗng")
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File ảnh vượt quá giới hạn 5 MB")
    try:
        result = await run_in_threadpool(extract_ocr, contents)
        return JSONResponse(content=result)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Lỗi OCR: {error}") from error
