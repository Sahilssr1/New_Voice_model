"""Paragraph-aware text chunking for the knowledge base."""
from __future__ import annotations

import re


def _split_paragraphs(text: str) -> list[str]:
    parts = re.split(r"\n\s*\n", text)
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if p:
            # Collapse interior whitespace/newlines inside a paragraph.
            out.append(re.sub(r"\s+", " ", p))
    return out


def chunk_text(
    text: str, chunk_size: int = 600, overlap: int = 100
) -> list[str]:
    """Split text into overlapping chunks of ~chunk_size characters.

    Greedy paragraph packing: paragraphs are appended to the current chunk
    until adding another would exceed chunk_size; over-long paragraphs are
    hard-split. Overlap carries the tail of the previous chunk forward so
    context is not lost at boundaries.
    """
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    paragraphs = _split_paragraphs(text)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    def flush() -> None:
        if current:
            chunks.append(" ".join(current))

    for para in paragraphs:
        # Hard-split pathological paragraphs first.
        while len(para) > chunk_size:
            flush()
            current, current_len = [], 0
            chunks.append(para[:chunk_size])
            para = para[chunk_size:]
        if current and current_len + 1 + len(para) > chunk_size:
            flush()
            # Overlap: seed the next chunk with the tail of the last one.
            tail = chunks[-1][-overlap:] if chunks else ""
            current = [tail] if tail else []
            current_len = len(tail)
        current.append(para)
        current_len += (1 if current_len else 0) + len(para)
    flush()
    return [c for c in chunks if c.strip()]
