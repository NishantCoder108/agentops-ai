import zlib

import pytest
from pydantic import ValidationError

from app.knowledge.chunking import CHUNK_SIZE, chunk_text
from app.knowledge.embeddings import EMBEDDING_DIMENSIONS, EmbeddingConfigurationError, create_embedding_provider
from app.knowledge.extract import InvalidDocumentError, document_format, extract_text, stored_filename
from app.models.document import DocumentFormat
from app.tools import KnowledgeSearchInput, create_default_tool_registry
from tests.conftest import make_settings


def test_txt_and_markdown_are_extracted_as_utf8() -> None:
    assert document_format("notes.txt") == DocumentFormat.TXT
    assert document_format("Guide.MD") == DocumentFormat.MARKDOWN
    assert extract_text("Hello\n\nworld".encode(), DocumentFormat.TXT) == "Hello\n\nworld"
    assert extract_text("\ufeff# Title".encode("utf-8"), DocumentFormat.MARKDOWN) == "# Title"


@pytest.mark.parametrize("filename", ["notes.pdf", "file.docx", "no-extension", "archive.txt.gz"])
def test_other_file_types_are_rejected(filename: str) -> None:
    with pytest.raises(InvalidDocumentError, match="Only .txt and .md"):
        document_format(filename)


def test_extract_rejects_empty_binary_and_non_utf8() -> None:
    with pytest.raises(InvalidDocumentError, match="empty"):
        extract_text(b"   \n", DocumentFormat.TXT)
    with pytest.raises(InvalidDocumentError, match="not a text file"):
        extract_text(b"hello\x00world", DocumentFormat.TXT)
    with pytest.raises(InvalidDocumentError, match="UTF-8"):
        extract_text(b"\xff\xfe", DocumentFormat.TXT)


def test_filename_uses_the_base_name() -> None:
    assert stored_filename("../secret/policy.md") == "policy.md"


def test_short_text_is_one_chunk() -> None:
    assert chunk_text("Refunds take five days.", DocumentFormat.TXT) == ["Refunds take five days."]


def test_markdown_keeps_a_heading_with_its_section() -> None:
    text = "# Refunds\n\nFive days.\n\n# Shipping\n\nTwo days."

    assert chunk_text(text, DocumentFormat.MARKDOWN) == [
        "# Refunds\n\nFive days.",
        "# Shipping\n\nTwo days.",
    ]


def test_long_text_is_split_with_overlap() -> None:
    text = "a" * (CHUNK_SIZE + 50)

    chunks = chunk_text(text, DocumentFormat.TXT)

    assert len(chunks) == 2
    assert len(chunks[0]) == CHUNK_SIZE
    assert chunks[1].startswith(chunks[0][-200:])


def test_knowledge_search_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError, match="sql"):
        KnowledgeSearchInput.model_validate({"query": "refunds", "sql": "select 1"})


def test_embedding_provider_requires_model_and_key() -> None:
    with pytest.raises(EmbeddingConfigurationError):
        create_embedding_provider(make_settings())


def test_registry_adds_knowledge_search_only_with_an_embedder() -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/none")
    factory = async_sessionmaker(engine)
    organization_id = "7f1c7b7e-3c2e-4a59-9d39-2b0f5c3d8a10"

    without = create_default_tool_registry(session_factory=factory, organization_id=organization_id)
    with_embedder = create_default_tool_registry(
        session_factory=factory,
        organization_id=organization_id,
        embedder=_FakeEmbedder(),
    )

    assert [tool.name for tool in without.list_tools()] == ["calculator", "analytics"]
    assert [tool.name for tool in with_embedder.list_tools()] == [
        "calculator",
        "analytics",
        "search_knowledge",
    ]
    engine.sync_engine.dispose()


class _FakeEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [vector_for(text) for text in texts]

    async def aclose(self) -> None:
        return None


def vector_for(text: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSIONS
    vector[zlib.crc32(text.encode()) % EMBEDDING_DIMENSIONS] = 1.0
    return vector
