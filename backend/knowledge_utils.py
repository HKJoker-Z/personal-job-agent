from io import BytesIO
from typing import Any

from docx import Document
from pypdf import PdfReader


MAX_KNOWLEDGE_TEXT_CHARS = 30000
CHUNK_SIZE_CHARS = 1000
CHUNK_OVERLAP_CHARS = 125
SUPPORTED_KNOWLEDGE_EXTENSIONS = (".pdf", ".docx", ".txt", ".md", ".markdown")


def clean_knowledge_text(text: Any) -> str:
    raw_text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in raw_text.splitlines()]

    cleaned_lines: list[str] = []
    previous_blank = False
    for line in lines:
        if not line:
            if not previous_blank and cleaned_lines:
                cleaned_lines.append("")
            previous_blank = True
            continue

        cleaned_lines.append(line)
        previous_blank = False

    return "\n".join(cleaned_lines).strip()


def truncate_knowledge_text(text: str) -> str:
    return text[:MAX_KNOWLEDGE_TEXT_CHARS]


def build_text_chunks(text: str) -> list[str]:
    clean_text = truncate_knowledge_text(clean_knowledge_text(text))
    if not clean_text:
        return []

    chunks: list[str] = []
    start = 0
    text_length = len(clean_text)

    while start < text_length:
        end = min(start + CHUNK_SIZE_CHARS, text_length)
        chunk = clean_text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= text_length:
            break

        start = max(end - CHUNK_OVERLAP_CHARS, start + 1)

    return chunks


def extract_pdf_text(file_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(file_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()


def extract_docx_text(file_bytes: bytes) -> str:
    document = Document(BytesIO(file_bytes))
    paragraphs = [paragraph.text for paragraph in document.paragraphs]
    return "\n".join(paragraphs).strip()


def extract_text_file(file_bytes: bytes) -> str:
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return file_bytes.decode("latin-1")


def extract_knowledge_file_text(filename: str, file_bytes: bytes) -> str:
    clean_filename = filename.lower()

    if not file_bytes:
        raise ValueError("Uploaded knowledge file is empty.")

    if clean_filename.endswith(".pdf"):
        return extract_pdf_text(file_bytes)
    if clean_filename.endswith(".docx"):
        return extract_docx_text(file_bytes)
    if clean_filename.endswith((".txt", ".md", ".markdown")):
        return extract_text_file(file_bytes)

    supported = ", ".join(SUPPORTED_KNOWLEDGE_EXTENSIONS)
    raise ValueError(f"Knowledge file must use one of these extensions: {supported}.")


def validate_knowledge_filename(filename: str) -> None:
    clean_filename = filename.lower()
    if not clean_filename.endswith(SUPPORTED_KNOWLEDGE_EXTENSIONS):
        supported = ", ".join(SUPPORTED_KNOWLEDGE_EXTENSIONS)
        raise ValueError(f"Knowledge file must use one of these extensions: {supported}.")
