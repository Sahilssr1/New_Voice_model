"""Provider factory: lazily-built singletons with safe fallbacks.

Factories must NEVER crash on missing optional dependencies:
- STT  -> FasterWhisperSTT (model loads lazily on first use; raises only when
          actually used without faster-whisper installed)
- TTS  -> PiperTTS if usable, else NullTTS (warning logged)
- LLM  -> OllamaLLM if constructible, else MockLLM (warning logged)
- VAD  -> SileroVAD if torch/model available, else EnergyVAD
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

_stt = None
_tts = None
_llm = None
_vad = None

# Static fallback catalog used when PiperTTS cannot be constructed.
_FALLBACK_CATALOG: list[dict] = [
    {
        "voice_id": "en_US-amy-medium",
        "name": "Amy",
        "provider": "piper",
        "language": "en",
        "gender": "female",
        "sample_rate": 22050,
    },
    {
        "voice_id": "en_US-lessac-medium",
        "name": "Lessac",
        "provider": "piper",
        "language": "en",
        "gender": "male",
        "sample_rate": 22050,
    },
    {
        "voice_id": "en_US-ryan-medium",
        "name": "Ryan",
        "provider": "piper",
        "language": "en",
        "gender": "male",
        "sample_rate": 22050,
    },
    {
        "voice_id": "hi_IN-priyamvada-medium",
        "name": "Priyamvada",
        "provider": "piper",
        "language": "hi",
        "gender": "female",
        "sample_rate": 22050,
    },
]


def get_stt():
    """Return the STT singleton (lazy model load on first transcribe)."""
    global _stt
    if _stt is None:
        from .stt.faster_whisper import FasterWhisperSTT

        _stt = FasterWhisperSTT()
    return _stt


def get_tts():
    """Return the TTS singleton (PiperTTS, else NullTTS fallback)."""
    global _tts
    if _tts is None:
        try:
            from .tts.piper_tts import PiperTTS

            candidate = PiperTTS()
            # Fail fast if piper-tts is not importable at all.
            import piper  # noqa: F401

            _tts = candidate
        except Exception as exc:
            log.warning("PiperTTS unavailable, using NullTTS: %s", exc)
            from .tts.null_tts import NullTTS

            _tts = NullTTS()
    return _tts


def get_llm():
    """Return the LLM singleton (OllamaLLM, else MockLLM fallback)."""
    global _llm
    if _llm is None:
        try:
            from .llm.ollama_llm import OllamaLLM

            _llm = OllamaLLM()
        except Exception as exc:
            log.warning("OllamaLLM unavailable, using MockLLM: %s", exc)
            from .llm.mock_llm import MockLLM

            _llm = MockLLM()
    return _llm


def get_vad():
    """Return the VAD singleton (SileroVAD, else EnergyVAD fallback)."""
    global _vad
    if _vad is None:
        try:
            from .vad.silero_vad import SileroVAD

            _vad = SileroVAD()
        except Exception as exc:
            log.warning("SileroVAD unavailable, using EnergyVAD: %s", exc)
            from .vad.energy_vad import EnergyVAD

            _vad = EnergyVAD()
    return _vad


def get_voice_catalog() -> list[dict]:
    """Return the voice catalog as plain dicts (for GET /api/voices).

    The catalog is static metadata; availability filtering happens in
    health checks, not here.
    """
    try:
        from .tts.piper_tts import PIPER_CATALOG

        return [
            {
                "voice_id": v.voice_id,
                "name": v.name,
                "provider": v.provider,
                "language": v.language,
                "gender": v.gender,
                "sample_rate": v.sample_rate,
            }
            for v in PIPER_CATALOG
        ]
    except Exception as exc:
        log.warning("Voice catalog unavailable: %s", exc)
        return [dict(v) for v in _FALLBACK_CATALOG]


async def get_ai_health() -> dict:
    """Health of all AI providers; never raises."""
    out: dict = {}
    for key, getter in (
        ("stt", get_stt),
        ("tts", get_tts),
        ("llm", get_llm),
        ("vad", get_vad),
    ):
        try:
            out[key] = await getter().health()
        except Exception as exc:
            out[key] = {"status": "down", "detail": str(exc)[:300]}
    return out


def reset_providers() -> None:
    """Clear singletons (used by tests)."""
    global _stt, _tts, _llm, _vad
    _stt = _tts = _llm = _vad = None
