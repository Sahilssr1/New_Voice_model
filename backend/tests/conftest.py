"""Shared pytest fixtures for the voiceagent backend test suite."""

from __future__ import annotations

import os
import sys
import uuid

import pytest

# Ensure the backend package is importable.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("OLLAMA_BASE_URL", "http://127.0.0.1:11434")


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def user_token(client):
    email = f"test-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/api/auth/register",
        json={"email": email, "password": "secret123", "name": "Tester"},
    )
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


@pytest.fixture()
def auth_headers(user_token):
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture()
def agent_id(client, auth_headers):
    r = client.post(
        "/api/agents",
        headers=auth_headers,
        json={
            "name": "Test Agent",
            "description": "agent for tests",
            "system_prompt": "You are a helpful test assistant. Keep replies short.",
            "language": "auto",
            "voice_gender": "female",
            "voice_id": "en_US-amy-medium",
            "greeting": "Hello! How can I help?",
            "max_duration_sec": 120,
            "silence_timeout_sec": 30,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]
