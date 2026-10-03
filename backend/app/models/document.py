import uuid
from enum import StrEnum

from pgvector import Vector
from pgvector.sqlalchemy import Vector as VectorColumn
from sqlalchemy import CheckConstraint, Dialect, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin, enum_column
from app.knowledge.embeddings import EMBEDDING_DIMENSIONS
from app.models.organization import Organization


class EmbeddingColumn(VectorColumn):
    """Pass a pgvector Vector through so asyncpg's registered codec can encode it.

    The stock SQLAlchemy type turns the value into a string first, which that codec rejects.
    """

    cache_ok = True

    def bind_processor(self, dialect: Dialect):  # type: ignore[no-untyped-def]
        def process(value: object) -> Vector | None:
            if value is None or isinstance(value, Vector):
                return value
            return Vector(value)  # type: ignore[arg-type]

        return process


class DocumentFormat(StrEnum):
    TXT = "txt"
    MARKDOWN = "markdown"


class Document(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """An uploaded text document. Its searchable text lives in `chunks`."""

    __tablename__ = "documents"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    format: Mapped[DocumentFormat] = mapped_column(enum_column(DocumentFormat, "format"))

    organization: Mapped[Organization] = relationship(back_populates="documents")
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document",
        order_by="DocumentChunk.position",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class DocumentChunk(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "position"),
        CheckConstraint("position >= 0", name="position_non_negative"),
        Index(
            "ix_document_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int]
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(EmbeddingColumn(EMBEDDING_DIMENSIONS))

    document: Mapped[Document] = relationship(back_populates="chunks")
