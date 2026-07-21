"""Resume upload type, signature, and archive bomb validation."""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from pathlib import Path


PDF_MEDIA_TYPE = "application/pdf"
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TEXT_MEDIA_TYPE = "text/plain"
MARKDOWN_MEDIA_TYPE = "text/markdown"
ALLOWED = {
    ".pdf": {PDF_MEDIA_TYPE},
    ".docx": {DOCX_MEDIA_TYPE},
    ".txt": {TEXT_MEDIA_TYPE},
    ".md": {MARKDOWN_MEDIA_TYPE, TEXT_MEDIA_TYPE, "text/x-markdown"},
    ".markdown": {MARKDOWN_MEDIA_TYPE, TEXT_MEDIA_TYPE, "text/x-markdown"},
}
MAX_DOCX_FILES = 300
MAX_DOCX_EXPANDED_BYTES = 50 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100


class UnsafeUpload(ValueError):
    pass


def safe_display_filename(value: str) -> str:
    name = Path(value or "resume").name
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return (name or "resume")[:255]


def validate_resume_upload(
    filename: str,
    media_type: str,
    data: bytes,
    maximum_bytes: int,
) -> tuple[str, str, str]:
    if not data:
        raise UnsafeUpload("Uploaded resume is empty.")
    if len(data) > maximum_bytes:
        raise UnsafeUpload("Uploaded resume exceeds the configured size limit.")
    display_name = safe_display_filename(filename)
    extension = Path(display_name).suffix.lower()
    expected_media_types = ALLOWED.get(extension)
    if expected_media_types is None or media_type not in expected_media_types:
        raise UnsafeUpload("Only PDF, DOCX, TXT, and Markdown resumes with matching media types are accepted.")
    if extension == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise UnsafeUpload("PDF file signature is invalid.")
    elif extension == ".docx":
        _validate_docx(data)
    return display_name, extension, hashlib.sha256(data).hexdigest()


def _validate_docx(data: bytes) -> None:
    if not data.startswith(b"PK"):
        raise UnsafeUpload("DOCX file signature is invalid.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            names = {entry.filename for entry in entries}
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise UnsafeUpload("DOCX structure is incomplete.")
            if len(entries) > MAX_DOCX_FILES:
                raise UnsafeUpload("DOCX contains too many archive entries.")
            total = 0
            for entry in entries:
                if entry.is_dir():
                    continue
                total += entry.file_size
                if total > MAX_DOCX_EXPANDED_BYTES:
                    raise UnsafeUpload("DOCX expanded size is too large.")
                if entry.compress_size == 0 and entry.file_size > 0:
                    raise UnsafeUpload("DOCX contains an unsafe compressed entry.")
                if entry.compress_size and entry.file_size / entry.compress_size > MAX_COMPRESSION_RATIO:
                    raise UnsafeUpload("DOCX compression ratio is unsafe.")
    except zipfile.BadZipFile as exc:
        raise UnsafeUpload("DOCX archive is invalid.") from exc
