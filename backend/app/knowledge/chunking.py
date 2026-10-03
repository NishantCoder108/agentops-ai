import re

from app.models.document import DocumentFormat

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
MAX_CHUNKS = 200

_HEADING = re.compile(r"(?m)(?=^#{1,6} )")


def chunk_text(text: str, document_format: DocumentFormat) -> list[str]:
    """Split text into overlapping chunks. Markdown keeps each heading with its section."""
    pieces = _pieces(text, document_format)
    if document_format == DocumentFormat.MARKDOWN:
        chunks: list[str] = []
        for piece in pieces:
            chunks.extend(_windows(piece) if len(piece) > CHUNK_SIZE else [piece])
        return chunks
    return _pack(pieces)


def _pack(pieces: list[str]) -> list[str]:
    chunks: list[str] = []
    buffer = ""
    for piece in pieces:
        if len(piece) > CHUNK_SIZE:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            chunks.extend(_windows(piece))
            continue
        candidate = f"{buffer}\n\n{piece}" if buffer else piece
        if len(candidate) <= CHUNK_SIZE:
            buffer = candidate
            continue
        chunks.append(buffer)
        tail = buffer[-CHUNK_OVERLAP:].strip()
        buffer = f"{tail}\n\n{piece}" if tail else piece
    if buffer:
        chunks.append(buffer)
    return chunks


def _pieces(text: str, document_format: DocumentFormat) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    if document_format == DocumentFormat.MARKDOWN:
        parts = _HEADING.split(normalized)
    else:
        parts = re.split(r"\n\s*\n", normalized)
    return [part.strip() for part in parts if part.strip()]


def _windows(text: str) -> list[str]:
    step = CHUNK_SIZE - CHUNK_OVERLAP
    chunks: list[str] = []
    start = 0
    while start < len(text):
        piece = text[start : start + CHUNK_SIZE].strip()
        if piece:
            chunks.append(piece)
        if start + CHUNK_SIZE >= len(text):
            break
        start += step
    return chunks
