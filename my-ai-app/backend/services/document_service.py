"""Safe text extraction for document perception."""

from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import PurePath
from typing import Iterable
from xml.etree import ElementTree


SUPPORTED_EXTENSIONS = {".txt", ".md", ".csv", ".pdf", ".docx"}
MAX_DOCUMENT_CHARS = 200_000


@dataclass(frozen=True, slots=True)
class DocumentResult:
    filename: str
    document_type: str
    text: str
    char_count: int
    truncated: bool
    metadata: dict

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "document_type": self.document_type,
            "text": self.text,
            "char_count": self.char_count,
            "truncated": self.truncated,
            "metadata": self.metadata,
        }


def _extension(filename: str) -> str:
    return PurePath(filename or "").suffix.lower()


def _decode_text(contents: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1258", "latin-1"):
        try:
            return contents.decode(encoding)
        except UnicodeDecodeError:
            continue
    return contents.decode("utf-8", errors="replace")


def _extract_docx(contents: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(contents)) as archive:
        xml_content = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml_content)
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = []
    for paragraph in root.iter(f"{namespace}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{namespace}t"))
        if text.strip():
            paragraphs.append(text.strip())
    return "\n".join(paragraphs)


def _extract_pdf(contents: bytes) -> tuple[str, dict]:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError as error:
        raise RuntimeError("Chưa cài pypdf để đọc PDF. Chạy pip install -r requirements.txt") from error

    reader = PdfReader(io.BytesIO(contents))
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    return "\n\n".join(text for text in pages if text), {"pages": len(reader.pages)}


def _extract_csv(contents: bytes) -> str:
    rows = csv.reader(io.StringIO(_decode_text(contents)))
    return "\n".join(" | ".join(cell.strip() for cell in row) for row in rows)


def _clean_text(text: str) -> str:
    text = text.replace("\x00", "")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_document(contents: bytes, filename: str) -> DocumentResult:
    extension = _extension(filename)
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Định dạng tài liệu chưa được hỗ trợ: {extension or 'không rõ'}")
    if not contents:
        raise ValueError("Tài liệu rỗng")

    metadata = {"extension": extension}
    if extension in {".txt", ".md"}:
        text = _decode_text(contents)
    elif extension == ".csv":
        text = _extract_csv(contents)
    elif extension == ".docx":
        try:
            text = _extract_docx(contents)
        except (KeyError, zipfile.BadZipFile, ElementTree.ParseError) as error:
            raise ValueError("File DOCX không hợp lệ") from error
    else:
        text, pdf_metadata = _extract_pdf(contents)
        metadata.update(pdf_metadata)

    cleaned = _clean_text(text)
    original_count = len(cleaned)
    truncated = original_count > MAX_DOCUMENT_CHARS
    if truncated:
        cleaned = cleaned[:MAX_DOCUMENT_CHARS]
    return DocumentResult(
        filename=PurePath(filename).name or "document",
        document_type=extension.removeprefix("."),
        text=cleaned,
        char_count=original_count,
        truncated=truncated,
        metadata=metadata,
    )


def chunk_text(text: str, *, chunk_size: int = 4000) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size phải lớn hơn 0")
    return [text[index:index + chunk_size] for index in range(0, len(text), chunk_size)] or []
