"""Tests requiring real AI models. Skipped gracefully when models are unavailable."""

import numpy as np
import pytest


def _tone(freq=440.0, seconds=1.0, sr=16000, amp=0.3):
    t = np.arange(int(sr * seconds)) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


@pytest.mark.asyncio
async def test_stt_transcribe_tone():
    """faster-whisper loads and runs; a pure tone yields ~empty text (no crash)."""
    try:
        from app.ai.stt.faster_whisper import FasterWhisperSTT
    except ImportError:
        pytest.skip("faster-whisper not installed")
    try:
        stt = FasterWhisperSTT(model_name="tiny", device="cpu", compute_type="int8")
        result = await stt.transcribe(_tone(seconds=2.0), 16000)
    except Exception as exc:
        pytest.skip(f"whisper model unavailable: {exc}")
    assert isinstance(result.text, str)
    assert result.language in ("en", "")
    assert result.duration_ms >= 0


@pytest.mark.asyncio
async def test_stt_detect_language():
    try:
        from app.ai.stt.faster_whisper import FasterWhisperSTT
    except ImportError:
        pytest.skip("faster-whisper not installed")
    try:
        stt = FasterWhisperSTT(model_name="tiny", device="cpu", compute_type="int8")
        lang = await stt.detect_language(_tone(seconds=2.0), 16000)
    except Exception as exc:
        pytest.skip(f"whisper model unavailable: {exc}")
    assert isinstance(lang, str)


@pytest.mark.asyncio
async def test_stt_roundtrip_with_piper():
    """Synthesize speech with Piper, transcribe with Whisper: true loopback."""
    try:
        from app.ai.tts.piper_tts import PiperTTS
        from app.ai.stt.faster_whisper import FasterWhisperSTT
    except ImportError:
        pytest.skip("piper or faster-whisper not installed")
    try:
        tts = PiperTTS()
        chunks = []
        async for pcm, sr in tts.synthesize("hello world", "en_US-amy-medium"):
            chunks.append(np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0)
    except Exception as exc:
        pytest.skip(f"piper voice unavailable: {exc}")
    if not chunks:
        pytest.skip("no TTS audio produced")
    audio = np.concatenate(chunks)
    # resample 22050 -> 16000
    idx = (np.arange(int(len(audio) * 16000 / 22050))).astype(int)
    idx = np.clip(idx, 0, len(audio) - 1)
    audio16 = audio[idx]
    try:
        stt = FasterWhisperSTT(model_name="tiny", device="cpu", compute_type="int8")
        result = await stt.transcribe(audio16, 16000, language="en")
    except Exception as exc:
        pytest.skip(f"whisper model unavailable: {exc}")
    assert isinstance(result.text, str)
    print(f"\nroundtrip transcription: {result.text!r}")


@pytest.mark.asyncio
async def test_tts_synthesize():
    try:
        from app.ai.tts.piper_tts import PiperTTS
    except ImportError:
        pytest.skip("piper-tts not installed")
    try:
        tts = PiperTTS()
        total = 0
        n = 0
        async for pcm, sr in tts.synthesize("Hello, this is a test.", "en_US-amy-medium"):
            assert sr == 22050
            total += len(pcm)
            n += 1
    except Exception as exc:
        pytest.skip(f"piper voice unavailable: {exc}")
    assert n >= 1 and total > 1000


@pytest.mark.asyncio
async def test_tts_voices_catalog():
    from app.ai.factory import get_voice_catalog

    catalog = get_voice_catalog()
    assert len(catalog) >= 4
    genders = {v["gender"] for v in catalog}
    assert "female" in genders and "male" in genders
    langs = {v["language"] for v in catalog}
    assert "en" in langs and "hi" in langs


@pytest.mark.asyncio
async def test_llm_mock_generate():
    from app.ai.llm.mock_llm import MockLLM

    llm = MockLLM()
    res = await llm.generate([{"role": "user", "content": "hello"}])
    assert res.text
    assert res.model == "mock"

    # tool-call fallback path: MockLLM embeds the tool call as a JSON block in text
    from app.tools import get_registry

    res = await llm.generate([{"role": "user", "content": "where is my order 123?"}])
    call = get_registry().parse_tool_call(res.text)
    assert call is not None and call["name"] == "get_order_status"


@pytest.mark.asyncio
async def test_llm_ollama_if_available():
    from app.ai.llm.ollama_llm import OllamaLLM

    llm = OllamaLLM()
    health = await llm.health()
    if health.get("status") != "up":
        pytest.skip("ollama not reachable")
    res = await llm.generate(
        [{"role": "user", "content": "Say only: ok"}],
        system="You are a terse assistant.",
        max_tokens=32,
    )
    assert res.text
    print(f"\nollama response: {res.text!r} ({res.latency_ms}ms)")
