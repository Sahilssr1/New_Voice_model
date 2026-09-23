"""Knowledge-base service: ingest, manage, and search agent documents."""
from __future__ import annotations

import asyncio
import logging

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.kb.chunking import chunk_text
from app.ai.kb.embeddings import get_embedding_provider
from app.ai.kb.extract import SUPPORTED_EXTENSIONS, extract_text
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument

log = logging.getLogger(__name__)


def _kb_settings():
    from app.core.config import settings

    return settings


async def add_document(
    db: AsyncSession,
    agent_id: str,
    filename: str,
    content: bytes,
    content_type: str = "",
) -> KnowledgeDocument:
    """Extract -> chunk -> embed -> persist. Raises ValueError on bad input."""
    settings = _kb_settings()
    max_bytes = int(getattr(settings, "KB_MAX_FILE_MB", 10)) * 1024 * 1024
    if len(content) > max_bytes:
        raise ValueError(f"File too large (>{getattr(settings, 'KB_MAX_FILE_MB', 10)} MB).")

    text = extract_text(filename, content).strip()
    if not text:
        raise ValueError("No readable text found in the uploaded file.")
    max_chars = 200_000
    if len(text) > max_chars:
        text = text[:max_chars]

    chunks = chunk_text(
        text,
        chunk_size=int(getattr(settings, "KB_CHUNK_SIZE", 600)),
        overlap=int(getattr(settings, "KB_CHUNK_OVERLAP", 100)),
    )
    if not chunks:
        raise ValueError("No readable text found in the uploaded file.")

    provider = get_embedding_provider()
    embeddings = await asyncio.to_thread(provider.embed, chunks)

    doc = KnowledgeDocument(
        agent_id=agent_id,
        filename=filename,
        content_type=content_type or "",
        char_count=len(text),
        chunk_count=len(chunks),
        embedding_model=provider.model_id,
    )
    db.add(doc)
    await db.flush()  # assign doc.id

    for i, (chunk_text_, vec) in enumerate(zip(chunks, embeddings)):
        db.add(
            KnowledgeChunk(
                document_id=doc.id,
                agent_id=agent_id,
                chunk_index=i,
                text=chunk_text_,
                embedding=np.asarray(vec, dtype=np.float32).tobytes(),
            )
        )
    await db.commit()
    await db.refresh(doc)
    log.info("KB: agent %s added '%s' (%d chunks)", agent_id, filename, len(chunks))
    return doc


async def list_documents(
    db: AsyncSession, agent_id: str
) -> list[KnowledgeDocument]:
    result = await db.execute(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.agent_id == agent_id)
        .order_by(KnowledgeDocument.created_at.desc())
    )
    return list(result.scalars().all())


async def delete_document(db: AsyncSession, agent_id: str, doc_id: str) -> bool:
    result = await db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == doc_id,
            KnowledgeDocument.agent_id == agent_id,
        )
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        return False
    await db.delete(doc)
    await db.commit()
    return True


def _cosine_top_k(
    query_vec: np.ndarray,
    chunk_rows: list[tuple[str, str, str, bytes]],
    top_k: int,
    min_score: float,
) -> list[dict]:
    """Brute-force cosine search (fine for local KB sizes; pgvector later)."""
    scored: list[dict] = []
    q = query_vec / (np.linalg.norm(query_vec) + 1e-9)
    for chunk_id, filename, text, emb_bytes in chunk_rows:
        if not emb_bytes:
            continue
        vec = np.frombuffer(emb_bytes, dtype=np.float32)
        if vec.size == 0:
            continue
        vec = vec / (np.linalg.norm(vec) + 1e-9)
        score = float(np.dot(q, vec))
        if score >= min_score:
            scored.append(
                {"chunk_id": chunk_id, "filename": filename, "text": text, "score": score}
            )
    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:top_k]


async def search(
    db: AsyncSession,
    agent_id: str,
    query: str,
    top_k: int | None = None,
    min_score: float | None = None,
) -> list[dict]:
    """Return the most relevant chunks for a query (never raises)."""
    settings = _kb_settings()
    try:
        query = (query or "").strip()
        if not query:
            return []
        top_k = top_k or int(getattr(settings, "KB_TOP_K", 3))
        min_score = (
            getattr(settings, "KB_MIN_SCORE", 0.25)
            if min_score is None
            else min_score
        )
        result = await db.execute(
            select(
                KnowledgeChunk.id,
                KnowledgeDocument.filename,
                KnowledgeChunk.text,
                KnowledgeChunk.embedding,
            )
            .join(
                KnowledgeDocument,
                KnowledgeChunk.document_id == KnowledgeDocument.id,
            )
            .where(
                KnowledgeChunk.agent_id == agent_id,
                # Never mix embedding spaces: ignore docs ingested with a
                # different KB_MODEL (re-upload them after switching models).
                KnowledgeDocument.embedding_model == get_embedding_provider().model_id,
            )
        )
        rows = [(r[0], r[1], r[2], r[3]) for r in result.all()]
        if not rows:
            return []
        provider = get_embedding_provider()
        qvec = (await asyncio.to_thread(provider.embed, [query]))[0]
        return _cosine_top_k(qvec, rows, top_k, float(min_score))
    except Exception as exc:
        log.warning("KB search failed: %s", exc)
        return []


async def retrieve_context(
    session_factory, agent_id: str, query: str
) -> str | None:
    """One-shot helper for the voice pipeline: returns formatted excerpts."""
    settings = _kb_settings()
    if not bool(getattr(settings, "KB_ENABLED", True)):
        return None
    try:
        async with session_factory() as db:
            hits = await search(db, agent_id, query)
    except Exception as exc:
        log.warning("KB retrieve failed: %s", exc)
        return None
    if not hits:
        return None
    excerpts = "\n---\n".join(
        f"[from {h['filename']}]\n{h['text']}" for h in hits
    )
    return excerpts


def supported_extensions() -> list[str]:
    return sorted(SUPPORTED_EXTENSIONS)
