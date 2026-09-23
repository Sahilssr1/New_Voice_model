"""Auth + agents + calls + dashboard + health API tests."""


def test_register_login_me(client):
    import uuid

    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "pw123456"})
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    assert token

    # duplicate register -> 400
    r = client.post("/api/auth/register", json={"email": email, "password": "pw123456"})
    assert r.status_code == 400

    # login JSON
    r = client.post("/api/auth/login", json={"email": email, "password": "pw123456"})
    assert r.status_code == 200, r.text

    # bad password
    r = client.post("/api/auth/login", json={"email": email, "password": "wrong"})
    assert r.status_code == 401

    # me
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == email

    # no auth
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_agent_crud(client, auth_headers, agent_id):
    # get
    r = client.get(f"/api/agents/{agent_id}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["name"] == "Test Agent"
    assert isinstance(r.json()["tools"], list)

    # list
    r = client.get("/api/agents", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) >= 1

    # invalid gender -> 422
    r = client.post(
        "/api/agents",
        headers=auth_headers,
        json={
            "name": "Bad",
            "system_prompt": "x",
            "language": "en",
            "voice_gender": "robot",
            "voice_id": "en_US-amy-medium",
        },
    )
    assert r.status_code == 422

    # patch
    r = client.patch(
        f"/api/agents/{agent_id}", headers=auth_headers, json={"temperature": 0.3}
    )
    assert r.status_code == 200
    assert r.json()["temperature"] == 0.3

    # missing -> 404
    r = client.get("/api/agents/00000000-0000-0000-0000-000000000000", headers=auth_headers)
    assert r.status_code == 404

    # delete
    r = client.delete(f"/api/agents/{agent_id}", headers=auth_headers)
    assert r.status_code == 200
    r = client.get(f"/api/agents/{agent_id}", headers=auth_headers)
    assert r.status_code == 404


def test_voices_filter(client, auth_headers):
    r = client.get("/api/voices?language=hi&gender=female", headers=auth_headers)
    assert r.status_code == 200
    voices = r.json()
    assert any(v["voice_id"] == "hi_IN-priyamvada-medium" for v in voices)
    assert all(v["language"] == "hi" and v["gender"] == "female" for v in voices)

    r = client.get("/api/voices?gender=male", headers=auth_headers)
    assert all(v["gender"] == "male" for v in r.json())


def test_tools_attach_detach(client, auth_headers, agent_id):
    r = client.get("/api/tools", headers=auth_headers)
    assert r.status_code == 200
    tools = r.json()
    assert any(t["name"] == "get_order_status" for t in tools)
    tool_id = next(t["id"] for t in tools if t["name"] == "get_order_status")

    r = client.post(f"/api/agents/{agent_id}/tools", headers=auth_headers, json={"tool_id": tool_id})
    assert r.status_code == 200

    r = client.get(f"/api/agents/{agent_id}", headers=auth_headers)
    assert any(t["name"] == "get_order_status" for t in r.json()["tools"])

    r = client.delete(f"/api/agents/{agent_id}/tools/{tool_id}", headers=auth_headers)
    assert r.status_code == 200


def test_calls_and_dashboard(client, auth_headers, agent_id):
    r = client.get("/api/calls", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)

    r = client.get("/api/dashboard", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    for key in ("total_agents", "total_calls", "total_duration_sec", "successful_calls", "failed_calls", "languages", "recent_calls"):
        assert key in body, key
    assert body["total_agents"] >= 1


def test_health_endpoints(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    assert "services" in body

    for path in ("/health/ai", "/health/stt", "/health/tts", "/health/llm", "/health/database", "/health/redis"):
        r = client.get(path)
        assert r.status_code == 200, path
        body = r.json()
        if path == "/health/ai":
            assert {"stt", "tts", "llm", "vad"} <= set(body.keys()), path
        else:
            assert "status" in body, path
