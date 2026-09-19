"""Restricted per-user file tools. Never allow paths outside TOOL_FILE_ROOT."""

from __future__ import annotations

import os
from pathlib import Path

FILE_ROOT = Path(os.getenv("TOOL_FILE_ROOT")).resolve()
MAX_FILE_BYTES = int(os.getenv("TOOL_MAX_FILE_BYTES"))
ALLOWED_EXTENSIONS = frozenset({".txt", ".md", ".json", ".csv", ".log"})


def _safe_path(user_id: str, relative_path: str) -> Path:
    value = str(relative_path or "").strip()
    candidate = Path(value)
    if not value or candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("Đường dẫn file không hợp lệ")
    if candidate.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError("Chỉ hỗ trợ file txt, md, json, csv hoặc log")
    user_root = (FILE_ROOT / user_id).resolve()
    target = (user_root / candidate).resolve()
    if user_root != target and user_root not in target.parents:
        raise ValueError("Đường dẫn vượt khỏi thư mục user")
    return target


def read_file(user_id: str, relative_path: str) -> dict:
    target = _safe_path(user_id, relative_path)
    if not target.exists() or not target.is_file():
        return {"ok": False, "error": "file_not_found", "path": relative_path}
    if target.stat().st_size > MAX_FILE_BYTES:
        return {"ok": False, "error": "file_too_large", "path": relative_path}
    return {"ok": True, "path": relative_path, "content": target.read_text(encoding="utf-8")}


def write_file(user_id: str, relative_path: str, content: str) -> dict:
    target = _safe_path(user_id, relative_path)
    value = str(content or "")
    if len(value.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError("Nội dung file vượt quá giới hạn")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(value, encoding="utf-8")
    return {"ok": True, "path": relative_path, "bytes": len(value.encode("utf-8"))}
