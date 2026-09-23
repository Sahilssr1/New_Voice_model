"""Knowledge-base (RAG) building blocks.

Pipeline: uploaded file -> extract text -> chunk -> embed -> store.
At query time: embed query -> cosine search over the agent's chunks ->
inject top-k excerpts into the LLM system prompt.
"""
from app.ai.kb.chunking import chunk_text
from app.ai.kb.embeddings import (
    EmbeddingProvider,
    HashEmbeddings,
    get_embedding_provider,
)
from app.ai.kb.extract import extract_text

__all__ = [
    "chunk_text",
    "extract_text",
    "EmbeddingProvider",
    "HashEmbeddings",
    "get_embedding_provider",
]
