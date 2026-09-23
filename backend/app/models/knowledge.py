"""Knowledge-base models: per-agent documents and their vector chunks."""
from typing import Optional

from sqlalchemy import ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._common import created_at_col, uuid_pk


class KnowledgeDocument(Base):
    """An uploaded source file belonging to one agent's knowledge base."""

    __tablename__ = "knowledge_documents"

    id: Mapped[str] = uuid_pk()
    agent_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Embedding space this document was ingested with. Chunks embedded with a
    # different KB_MODEL are never mixed into search results (stale vectors).
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    created_at = created_at_col()

    agent: Mapped["Agent"] = relationship(back_populates="knowledge_documents")
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class KnowledgeChunk(Base):
    """One embedded text chunk. Embedding stored as float32 bytes (numpy)."""

    __tablename__ = "knowledge_chunks"

    id: Mapped[str] = uuid_pk()
    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    created_at = created_at_col()

    document: Mapped["KnowledgeDocument"] = relationship(back_populates="chunks")
