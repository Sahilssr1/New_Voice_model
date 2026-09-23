"""AI component tests: VAD, language detection, tools registry, NLP memory."""

import numpy as np
import pytest


def _tone(freq=440.0, seconds=1.0, sr=16000, amp=0.3):
    t = np.arange(int(sr * seconds)) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_energy_vad_silence_vs_speech():
    from app.ai.vad.energy_vad import EnergyVAD

    vad = EnergyVAD()
    silence = np.zeros(320, dtype=np.float32)
    # let noise floor settle
    for _ in range(20):
        vad.is_speech(silence)
    speech, prob = vad.is_speech(silence)
    assert speech is False

    tone = _tone()
    hits = sum(vad.is_speech(tone[i : i + 320])[0] for i in range(0, len(tone) - 320, 320))
    assert hits > 5, "tone should be detected as speech"


def test_vad_factory_falls_back():
    from app.ai import factory

    factory.reset_providers()
    vad = factory.get_vad()
    assert vad is not None
    assert hasattr(vad, "is_speech")


def test_language_detection_text():
    from app.ai.nlp.language import detect_text_language

    assert detect_text_language("मुझे अपने ऑर्डर का स्टेटस बताइए") == "hi"
    assert detect_text_language("Can you tell me my order status?") == "en"
    assert detect_text_language("Mera order kab tak aa jayega?") == "hinglish"
    assert detect_text_language("Hello, how are you today?") == "en"


def test_tool_registry_parse_and_execute():
    import asyncio
    from app.tools import get_registry

    reg = get_registry()

    async def dummy(order_id: str):
        return {"ok": True, "order_id": order_id}

    reg.register("dummy_tool", "test tool", {"order_id": "string"}, dummy)

    call = reg.parse_tool_call('```json\n{"tool": "dummy_tool", "arguments": {"order_id": "123"}}\n```')
    assert call == {"name": "dummy_tool", "arguments": {"order_id": "123"}}

    call = reg.parse_tool_call('{"tool": "dummy_tool", "arguments": {"order_id": "9"}}')
    assert call["name"] == "dummy_tool"

    assert reg.parse_tool_call("just a normal sentence") is None

    result = asyncio.new_event_loop().run_until_complete(reg.execute("dummy_tool", {"order_id": "123"}))
    assert result["ok"] is True
    assert result["result"]["order_id"] == "123"

    with pytest.raises(Exception):
        asyncio.new_event_loop().run_until_complete(reg.execute("nope", {}))


def test_builtin_tools_execute():
    import asyncio
    from app.tools import get_registry

    reg = get_registry()
    loop = asyncio.new_event_loop()
    res = loop.run_until_complete(reg.execute("get_order_status", {"order_id": "12345"}))
    assert "12345" in str(res)
    res = loop.run_until_complete(reg.execute("transfer_to_human", {"reason": "angry"}))
    assert res is not None


def test_conversation_memory_window():
    from app.ai.nlp.memory import ConversationMemory

    mem = ConversationMemory()
    for i in range(25):
        mem.add_message("user" if i % 2 == 0 else "assistant", f"message {i}", "en")
    window = mem.get_window(10)
    assert len(window) == 10
    assert window[-1]["text"] == "message 24"
    assert mem.needs_summary() is True


def test_nlp_validate_response():
    from app.ai.nlp.pipeline import NLPPipeline

    nlp = NLPPipeline()
    out = nlp.validate_response('```json\n{"tool": "x"}\n```\nHello there!')
    assert "Hello" in out
    long_text = "word " * 500
    assert len(nlp.validate_response(long_text)) <= 650
