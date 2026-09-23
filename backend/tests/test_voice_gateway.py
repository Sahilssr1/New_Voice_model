"""WebSocket voice gateway tests with fake providers (no real models needed)."""

import asyncio
import base64

import numpy as np
import pytest

from app.ai.llm.base import LLMResult
from app.ai.stt.base import STTResult


class FakeSTT:
    name = "fake-stt"

    async def transcribe(self, audio, sample_rate, language=None):
        return STTResult(text="hello agent", language="en", confidence=0.9, duration_ms=50)

    async def detect_language(self, audio, sample_rate):
        return "en"

    async def health(self):
        return {"status": "up"}


class FakeTTS:
    name = "fake-tts"

    async def synthesize(self, text, voice_id, language=None, speed=1.0):
        # yield two small PCM chunks at 22050 Hz
        for _ in range(2):
            yield (np.zeros(2205, dtype=np.int16).tobytes(), 22050)

    async def health(self):
        return {"status": "up"}


class FakeLLM:
    name = "fake-llm"

    async def generate(self, messages, system=None, tools=None, temperature=0.7, max_tokens=512):
        return LLMResult(text="Hi there! How can I help?", tool_calls=[], latency_ms=10, model="fake")

    async def health(self):
        return {"status": "up"}


class FakeVAD:
    name = "fake-vad"
    sample_rate = 16000

    def __init__(self, speech_frames=50):
        self.n = 0
        self.speech_frames = speech_frames

    def is_speech(self, chunk):
        self.n += 1
        # speech for the first `speech_frames` frames, then silence
        return (self.n <= self.speech_frames, 0.9 if self.n <= self.speech_frames else 0.0)

    async def health(self):
        return {"status": "up"}


def _patch_providers(monkeypatch):
    # The gateway binds get_stt/get_tts/get_llm/get_vad directly
    # (from ..ai.factory import ...), so patch at the usage site.
    import app.websocket.voice_gateway as gw

    monkeypatch.setattr(gw, "get_stt", lambda: FakeSTT())
    monkeypatch.setattr(gw, "get_tts", lambda: FakeTTS())
    monkeypatch.setattr(gw, "get_llm", lambda: FakeLLM())
    monkeypatch.setattr(gw, "get_vad", lambda: FakeVAD())


def _pcm_frame(sr=16000, ms=20, amp=0.3):
    n = int(sr * ms / 1000)
    t = np.arange(n) / sr
    pcm = (amp * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
    return base64.b64encode(pcm.tobytes()).decode()


def test_voice_gateway_full_call(client, auth_headers, agent_id, monkeypatch):
    """start_call -> greeting audio -> simulated speech -> transcript + reply -> end_call."""
    _patch_providers(monkeypatch)
    token = auth_headers["Authorization"].split(" ", 1)[1]

    with client.websocket_connect("/ws/voice") as ws:
        ws.send_json({"type": "start_call", "agent_id": agent_id, "token": token})
        msg = ws.receive_json()
        assert msg["type"] == "call_started", msg
        call_id = msg["call_id"]

        # greeting: expect audio frames then audio_end (state may interleave)
        got_audio_end = False
        for _ in range(30):
            m = ws.receive_json()
            if m["type"] == "audio_end":
                got_audio_end = True
                break
        assert got_audio_end, "greeting audio_end not received"

        # send ~1s of "speech" frames then silence to trigger utterance end
        for _ in range(50):
            ws.send_json({"type": "audio", "data": _pcm_frame(), "seq": 1})
        # FakeVAD: 50 speech frames then silence; send enough silence frames
        # for the VAD's soft close (900ms) + merge window (600ms) + margin.
        for _ in range(100):
            ws.send_json({"type": "audio", "data": _pcm_frame(amp=0.0), "seq": 2})

        saw_user_transcript = False
        saw_assistant = False
        saw_latency = False
        for _ in range(60):
            m = ws.receive_json()
            t = m["type"]
            if t == "transcript" and m["role"] == "user":
                saw_user_transcript = True
                assert m["text"] == "hello agent"
            elif t == "transcript" and m["role"] == "assistant":
                saw_assistant = True
            elif t == "latency":
                saw_latency = True
                assert {"stt_ms", "llm_ms", "tts_ms", "total_ms"} <= set(m.keys())
            if saw_user_transcript and saw_assistant and saw_latency:
                break
        assert saw_user_transcript and saw_assistant and saw_latency

        ws.send_json({"type": "end_call"})
        ended = False
        for _ in range(20):
            m = ws.receive_json()
            if m["type"] == "call_ended":
                ended = True
                break
        assert ended

    # call persisted with messages
    r = client.get(f"/api/calls/{call_id}", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    roles = [m["role"] for m in body["messages"]]
    assert "user" in roles and "assistant" in roles


def test_voice_gateway_auth_failure(client):
    with client.websocket_connect("/ws/voice") as ws:
        ws.send_json({"type": "start_call", "agent_id": "nope", "token": "bad"})
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert msg["code"] == "auth_failed"


def test_voice_gateway_stt_failure_recovers(client, auth_headers, agent_id, monkeypatch):
    """STT raising must produce an error frame + recovery, not a dead call."""

    class BoomSTT(FakeSTT):
        async def transcribe(self, audio, sample_rate, language=None):
            raise RuntimeError("stt exploded")

    import app.websocket.voice_gateway as gw

    monkeypatch.setattr(gw, "get_stt", lambda: BoomSTT())
    monkeypatch.setattr(gw, "get_tts", lambda: FakeTTS())
    monkeypatch.setattr(gw, "get_llm", lambda: FakeLLM())
    monkeypatch.setattr(gw, "get_vad", lambda: FakeVAD())
    token = auth_headers["Authorization"].split(" ", 1)[1]

    with client.websocket_connect("/ws/voice") as ws:
        ws.send_json({"type": "start_call", "agent_id": agent_id, "token": token})
        assert ws.receive_json()["type"] == "call_started"
        # drain greeting
        for _ in range(30):
            if ws.receive_json()["type"] == "audio_end":
                break
        for _ in range(50):
            ws.send_json({"type": "audio", "data": _pcm_frame(), "seq": 1})
        for _ in range(100):
            ws.send_json({"type": "audio", "data": _pcm_frame(amp=0.0), "seq": 2})
        # STT fails -> expect an error frame, then the call must still end cleanly.
        saw_error = False
        for _ in range(30):
            m = ws.receive_json()
            if m["type"] == "error":
                saw_error = True
                break
        assert saw_error, "no error frame after STT failure"
        ws.send_json({"type": "end_call"})
        for _ in range(20):
            m = ws.receive_json()
            if m["type"] == "call_ended":
                break
        else:
            pytest.fail("call did not end cleanly after STT failure")
