from pathlib import Path

from app.core.exceptions import AppError
from app.models.document import DocumentFormat

MAX_DOCUMENT_BYTES = 1_000_000

_EXTENSIONS = {
    ".txt": DocumentFormat.TXT,
    ".md": DocumentFormat.MARKDOWN,
    ".markdown": DocumentFormat.MARKDOWN,
}


class InvalidDocumentError(AppError):
    status_code = 422
    code = "invalid_document"


def document_format(filename: str) -> DocumentFormat:
    suffix = Path(filename).suffix.lower()
    try:
        return _EXTENSIONS[suffix]
    except KeyError:
        raise InvalidDocumentError(
            "Only .txt and .md files are supported",
            details={"filename": Path(filename).name},
        ) from None


def stored_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    if not name or name in {".", ".."} or len(name) > 255:
        raise InvalidDocumentError("Document filename is missing or too long")
    return name


def extract_text(data: bytes, document_format: DocumentFormat) -> str:
    """TXT and Markdown are already text. The format is metadata; nothing is executed."""
    del document_format
    if len(data) > MAX_DOCUMENT_BYTES:
        raise InvalidDocumentError(
            "Document is too large", details={"max_bytes": MAX_DOCUMENT_BYTES}
        )
    if b"\x00" in data:
        raise InvalidDocumentError("Document is not a text file")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InvalidDocumentError("Document must be UTF-8 text") from None
    if not text.strip():
        raise InvalidDocumentError("Document is empty")
    return text
