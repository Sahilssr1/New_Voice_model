"""Knowledge-base (RAG) tests: chunking, extraction, retrieval, API, prompt wiring."""
from __future__ import annotations

import pytest

from app.ai.kb.chunking import chunk_text
from app.ai.kb.embeddings import (
    HashEmbeddings,
    get_embedding_provider,
    set_embedding_provider,
)
from app.ai.kb.extract import extract_text


@pytest.fixture()
def hash_provider():
    prev = get_embedding_provider() if _singleton_set() else None
    set_embedding_provider(HashEmbeddings(dim=64))
    yield
    set_embedding_provider(prev)


def _singleton_set() -> bool:
    from app.ai.kb import embeddings as emb_mod

    return emb_mod._provider is not None


# -- chunking ---------------------------------------------------------------

def test_chunk_text_short_passthrough():
    assert chunk_text("hello world", chunk_size=600) == ["hello world"]


def test_chunk_text_empty():
    assert chunk_text("", chunk_size=600) == []
    assert chunk_text("   \n  ", chunk_size=600) == []


def test_chunk_text_splits_long_input():
    text = "\n\n".join(f"Paragraph number {i} with some filler words." for i in range(20))
    chunks = chunk_text(text, chunk_size=200, overlap=20)
    assert len(chunks) > 1
    assert all(len(c) <= 220 for c in chunks)
    # All paragraphs survive across chunks.
    joined = " ".join(chunks)
    for i in range(20):
        assert f"Paragraph number {i}" in joined


# -- extraction --------------------------------------------------------------

def test_extract_text_txt():
    assert extract_text("notes.txt", "héllo".encode("utf-8")) == "héllo"
    assert extract_text("doc.md", b"# Title\nbody") == "# Title\nbody"


def test_extract_text_unsupported():
    with pytest.raises(ValueError):
        extract_text("data.xlsx", b"fake")


# -- embeddings ---------------------------------------------------------------

def test_hash_embeddings_deterministic_and_normalized():
    p = HashEmbeddings(dim=32)
    a = p.embed(["hello world"])
    b = p.embed(["hello world"])
    assert (a == b).all()
    assert abs(float((a[0] ** 2).sum()) - 1.0) < 1e-5
    assert p.embed(["completely different tokens xyz"]) .shape == (1, 32)


# -- API ----------------------------------------------------------------------

def _upload(client, headers, agent_id, filename, content, ctype="text/plain"):
    return client.post(
        f"/api/agents/{agent_id}/kb/documents",
        headers=headers,
        files={"file": (filename, content, ctype)},
    )


def test_kb_upload_list_delete(client, auth_headers, agent_id, hash_provider):
    r = _upload(client, auth_headers, agent_id, "faq.txt", b"Q: hours?\nA: 9 to 5.")
    assert r.status_code == 200, r.text
    doc_id = r.json()["id"]
    assert r.json()["chunk_count"] >= 1

    r = client.get(f"/api/agents/{agent_id}/kb/documents", headers=auth_headers)
    assert r.status_code == 200
    assert any(d["id"] == doc_id for d in r.json())

    r = client.delete(
        f"/api/agents/{agent_id}/kb/documents/{doc_id}", headers=auth_headers
    )
    assert r.status_code == 200

    r = client.get(f"/api/agents/{agent_id}/kb/documents", headers=auth_headers)
    assert all(d["id"] != doc_id for d in r.json())


def test_kb_upload_unsupported_type_rejected(client, auth_headers, agent_id):
    r = _upload(client, auth_headers, agent_id, "data.xlsx", b"fake")
    assert r.status_code == 400


def test_kb_search_ranking(client, auth_headers, agent_id, hash_provider):
    _upload(
        client, auth_headers, agent_id, "refunds.txt",
        b"Our refund policy: full refunds within 30 days of purchase. "
        b"Contact support@example.com to start a refund request.",
    )
    _upload(
        client, auth_headers, agent_id, "shipping.txt",
        b"Shipping times: standard delivery takes five business days. "
        b"Express delivery arrives in two business days.",
    )
    r = client.post(
        f"/api/agents/{agent_id}/kb/search",
        headers=auth_headers,
        json={"query": "how do I get a refund for my purchase", "top_k": 2},
    )
    assert r.status_code == 200, r.text
    hits = r.json()
    assert len(hits) >= 1
    assert hits[0]["filename"] == "refunds.txt"
    assert "refund" in hits[0]["text"].lower()


def test_kb_search_no_documents(client, auth_headers, agent_id, hash_provider):
    r = client.post(
        f"/api/agents/{agent_id}/kb/search",
        headers=auth_headers,
        json={"query": "anything", "top_k": 3},
    )
    assert r.status_code == 200
    assert r.json() == []


def test_kb_requires_auth(client, agent_id):
    r = client.get(f"/api/agents/{agent_id}/kb/documents")
    assert r.status_code == 401


# -- prompt wiring --------------------------------------------------------------

def test_build_llm_messages_includes_kb_context():
    from app.services.conversation_service import build_llm_messages

    class FakeAgent:
        language = "en"
        system_prompt = "You are Aria."

    class FakeMem:
        summary = ""
        facts = {}

        def get_window(self, n):
            return []

    msgs = build_llm_messages(
        FakeAgent(), FakeMem(), kb_context="[from faq.txt]\nWe are open 9 to 5."
    )
    assert msgs[0]["role"] == "system"
    assert "We are open 9 to 5." in msgs[0]["content"]
    assert "Knowledge base" in msgs[0]["content"]

    msgs2 = build_llm_messages(FakeAgent(), FakeMem(), kb_context=None)
    assert "Knowledge base" not in msgs2[0]["content"]
