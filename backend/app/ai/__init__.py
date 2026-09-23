"""Open-source AI provider layer: STT, TTS, LLM, VAD, NLP.

All heavy third-party imports (faster-whisper, piper, torch, httpx) are done
lazily inside provider implementations so importing this package never fails
when optional dependencies are missing. Use app.ai.factory to obtain
ready-to-use singletons with safe fallbacks.
"""

from app.ai.factory import get_ai_health, get_llm, get_stt, get_tts, get_vad, get_voice_catalog

__all__ = ["get_stt", "get_tts", "get_llm", "get_vad", "get_voice_catalog", "get_ai_health"]
