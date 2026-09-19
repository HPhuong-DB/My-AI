"""OCR processing shared by image, screen and document perception."""

from functools import lru_cache
import importlib
import io
import os
import time

import numpy as np
import pytesseract
from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError

MAX_IMAGE_DIMENSION = int(os.getenv("OCR_MAX_IMAGE_DIMENSION", 4096))
MAX_IMAGE_PIXELS = int(os.getenv("OCR_MAX_IMAGE_PIXELS", 16_000_000))


def _resize_if_needed(img: Image.Image, max_size: int = 1600) -> Image.Image:
    if img.width > max_size or img.height > max_size:
        scale = max_size / max(img.width, img.height)
        return img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    return img


def _preprocess_default(img: Image.Image) -> Image.Image:
    gray = img.convert("L")
    enhanced = ImageOps.autocontrast(gray, cutoff=1)
    enhanced = enhanced.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3))
    enhanced = _resize_if_needed(enhanced)
    return enhanced.point(lambda value: 0 if value < 140 else 255, mode="1").convert("L")


def _preprocess_invert(img: Image.Image) -> Image.Image:
    return _preprocess_default(ImageOps.invert(img.convert("RGB")))


def _preprocess_yellow_mask(img: Image.Image) -> Image.Image:
    arr = np.array(img.convert("RGB"))
    red, green, blue = arr[..., 0], arr[..., 1], arr[..., 2]
    mask = (red > 140) & (green > 120) & (blue < 160)
    gray = np.array(img.convert("L"))
    output = np.where(mask, gray, 255).astype(np.uint8)
    result = Image.fromarray(output).filter(ImageFilter.UnsharpMask(radius=1, percent=200, threshold=2))
    return result.point(lambda value: 0 if value < 180 else 255, mode="1").convert("L")


def _score_text(text: str) -> float:
    if not text:
        return 0.0
    stripped = text.strip()
    letters = sum(1 for char in stripped if char.isalpha() or char.isdigit())
    return letters / max(len(stripped), 1) * 0.7 + min(len(stripped.split()) / 20, 1.0) * 0.3


@lru_cache(maxsize=1)
def _get_easyocr_reader():
    easyocr = importlib.import_module("easyocr")
    return easyocr.Reader(["vi", "en"], gpu=False)


def validate_image(contents: bytes) -> tuple[int, int]:
    try:
        image = Image.open(io.BytesIO(contents))
        image.verify()
        image = Image.open(io.BytesIO(contents))
    except (UnidentifiedImageError, OSError) as error:
        raise ValueError("File không phải ảnh hợp lệ") from error
    if image.width > MAX_IMAGE_DIMENSION or image.height > MAX_IMAGE_DIMENSION:
        raise ValueError("Kích thước ảnh vượt giới hạn")
    if image.width * image.height > MAX_IMAGE_PIXELS:
        raise ValueError("Số pixel ảnh vượt giới hạn")
    return image.width, image.height


def extract_ocr(contents: bytes) -> dict:
    """Run configured OCR variants and return JSON-serializable data."""
    validate_image(contents)
    try:
        image = Image.open(io.BytesIO(contents)).convert("RGB")
    except (UnidentifiedImageError, OSError) as error:
        raise ValueError("File không phải ảnh hợp lệ") from error

    variants = []
    methods = [
        ("default", _preprocess_default),
        ("invert", _preprocess_invert),
        ("yellow_mask", _preprocess_yellow_mask),
    ]
    for name, preprocess in methods:
        try:
            started = time.time()
            text = pytesseract.image_to_string(preprocess(image), lang="vie+eng", config="--psm 6")
            variants.append({
                "name": name,
                "text": text.strip(),
                "score": round(_score_text(text), 3),
                "duration": round(time.time() - started, 2),
            })
        except Exception:
            variants.append({"name": name, "text": "", "score": 0.0, "duration": 0.0})

    try:
        reader = _get_easyocr_reader()
        started = time.time()
        result = reader.readtext(np.array(image))
        text = "\n".join(item[1] for item in result)
        variants.append({
            "name": "easyocr",
            "text": text.strip(),
            "score": round(_score_text(text), 3),
            "duration": round(time.time() - started, 2),
        })
    except Exception:
        pass

    best = max(variants, key=lambda item: item["score"], default={"text": "", "score": 0.0})
    return {"text": best.get("text", "").strip(), "score": best.get("score", 0.0), "variants": variants}
