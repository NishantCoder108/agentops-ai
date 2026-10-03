import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.chunking import MAX_CHUNKS, chunk_text
from app.knowledge.embeddings import EMBEDDING_DIMENSIONS, EmbeddingProvider, EmbeddingProviderError
from app.knowledge.extract import InvalidDocumentError
from app.models.document import Document, DocumentChunk, DocumentFormat
from app.schemas.knowledge import KnowledgeHit, KnowledgeSearchResult


class KnowledgeService:
    """Store document chunks and search them. The caller chooses the organization, never the model."""

    def __init__(
        self, session: AsyncSession, organization_id: uuid.UUID, embedder: EmbeddingProvider
    ) -> None:
        self._session = session
        self._organization_id = organization_id
        self._embedder = embedder

    async def add_document(self, filename: str, document_format: DocumentFormat, text: str) -> Document:
        chunks = chunk_text(text, document_format)
        if not chunks:
            raise InvalidDocumentError("Document has no text")
        if len(chunks) > MAX_CHUNKS:
            raise InvalidDocumentError(
                "Document is too long", details={"max_chunks": MAX_CHUNKS, "chunk_count": len(chunks)}
            )

        vectors = await self._embedder.embed(chunks)
        _check_vectors(vectors, len(chunks))

        document = Document(
            organization_id=self._organization_id, filename=filename, format=document_format
        )
        document.chunks = [
            DocumentChunk(position=position, content=content, embedding=vector)
            for position, (content, vector) in enumerate(zip(chunks, vectors, strict=True))
        ]
        self._session.add(document)
        await self._session.commit()
        return document

    @staticmethod
    async def embed_query(embedder: EmbeddingProvider, query: str) -> list[float]:
        [vector] = _check_vectors(await embedder.embed([query]), 1)
        return vector

    async def search_by_vector(self, vector: list[float], limit: int) -> KnowledgeSearchResult:
        distance = DocumentChunk.embedding.cosine_distance(vector)
        similarity = (1 - distance).label("similarity")
        rows = await self._session.execute(
            select(Document.filename, DocumentChunk.content, similarity)
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(Document.organization_id == self._organization_id)
            .order_by(distance, DocumentChunk.position)
            .limit(limit)
        )
        return KnowledgeSearchResult(
            results=[
                KnowledgeHit(
                    document=filename,
                    chunk=content,
                    similarity=_score(score),
                )
                for filename, content, score in rows
            ]
        )


def _check_vectors(vectors: list[list[float]], expected: int) -> list[list[float]]:
    if len(vectors) != expected or any(len(vector) != EMBEDDING_DIMENSIONS for vector in vectors):
        raise EmbeddingProviderError(
            f"Embedding provider must return {expected} vectors of {EMBEDDING_DIMENSIONS} dimensions"
        )
    return vectors


def _score(value: object) -> float:
    score = float(value)  # type: ignore[arg-type]
    if score < 0:
        return 0.0
    if score > 1:
        return 1.0
    return round(score, 4)
