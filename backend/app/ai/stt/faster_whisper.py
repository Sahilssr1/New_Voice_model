"""faster-whisper based STT provider (CPU or NVIDIA GPU).

The model is loaded lazily on first use so importing this module is always
safe, even when faster-whisper is not installed. Transcription runs in a worker
thread because faster-whisper is blocking.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import time

import numpy as np

from .base import SpeechToTextProvider, STTResult

log = logging.getLogger(__name__)

TARGET_SR = 16000


def _sanitize_proxy_env() -> None:
    """Strip bracketed IPv6 literals from NO_PROXY/no_proxy.

    Some environments ship NO_PROXY with values like ``[::1]`` which crash
    httpx's proxy parsing (used by huggingface_hub for model downloads) with
    ``InvalidURL: Invalid port: ':1]'``. Unbracketed ``::1`` is equivalent
    for no-proxy matching.
    """
    for key in ("NO_PROXY", "no_proxy"):
        val = os.environ.get(key)
        if val and "[" in val:
            os.environ[key] = val.replace("[", "").replace("]", "")


def _resample_to_16k(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    """Resample mono float32 audio to 16 kHz with numpy linear interpolation."""
    x = np.asarray(audio, dtype=np.float32).ravel()
    if sample_rate == TARGET_SR or x.size == 0:
        return x
    duration = x.size / float(sample_rate)
    n_out = int(duration * TARGET_SR)
    if n_out <= 0:
        return np.zeros(0, dtype=np.float32)
    old_idx = np.linspace(0.0, float(x.size - 1), x.size)
    new_idx = np.linspace(0.0, float(x.size - 1), n_out)
    return np.interp(new_idx, old_idx, x).astype(np.float32)


def _map_language(language: str | None) -> str | None:
    """Map agent language config to a whisper language hint."""
    if not language:
        return None
    lang = language.strip().lower()
    if lang in ("auto", "hinglish"):
        # hinglish is romanized Hindi; let whisper auto-detect per utterance
        return None
    return lang


class FasterWhisperSTT(SpeechToTextProvider):
    """STT via faster-whisper (CTranslate2)."""

    name = "faster-whisper"

    def __init__(
        self,
        model_name: str | None = None,
        device: str | None = None,
        compute_type: str = "int8",
    ) -> None:
        self.model_name = model_name or os.environ.get("WHISPER_MODEL", "base")
        self.device = device or os.environ.get("WHISPER_DEVICE", "cpu")
        self.compute_type = compute_type
        self._model = None

    # -- model loading -----------------------------------------------------
    def _load(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError(
                    "faster-whisper is not installed; cannot transcribe audio"
                ) from exc
            _sanitize_proxy_env()
            log.info(
                "Loading faster-whisper model=%s device=%s compute_type=%s",
                self.model_name,
                self.device,
                self.compute_type,
            )
            self._model = WhisperModel(
                self.model_name, device=self.device, compute_type=self.compute_type
            )
        return self._model

    # -- API ---------------------------------------------------------------
    async def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int,
        language: str | None = None,
    ) -> STTResult:
        model = self._load()
        x = _resample_to_16k(audio, sample_rate)
        lang_hint = _map_language(language)

        def _run():
            segments, info = model.transcribe(
                x, language=lang_hint, beam_size=5, vad_filter=False
            )
            texts: list[str] = []
            logprobs: list[float] = []
            for seg in segments:
                texts.append(seg.text)
                try:
                    logprobs.append(float(seg.avg_logprob))
                except (TypeError, ValueError):
                    pass
            return "".join(texts).strip(), logprobs, info

        t0 = time.perf_counter()
        text, logprobs, info = await asyncio.to_thread(_run)
        duration_ms = int((time.perf_counter() - t0) * 1000)

        if logprobs:
            confidence = float(math.exp(sum(logprobs) / len(logprobs)))
        else:
            confidence = float(getattr(info, "language_probability", 0.0) or 0.0)
        detected = getattr(info, "language", None) or lang_hint or "en"
        audio_ms = int(len(x) / TARGET_SR * 1000)
        return STTResult(
            text=text,
            language=detected,
            confidence=max(0.0, min(1.0, confidence)),
            duration_ms=audio_ms or duration_ms,
        )

    async def detect_language(self, audio: np.ndarray, sample_rate: int) -> str:
        """Detect language via a lightweight transcription pass on the first 30s."""
        model = self._load()
        x = _resample_to_16k(audio, sample_rate)[: 30 * TARGET_SR]

        def _run() -> str:
            # language=None lets whisper auto-detect; info.language carries it.
            _, info = model.transcribe(x, task="transcribe", beam_size=1)
            return str(getattr(info, "language", "") or "")

        lang = await asyncio.to_thread(_run)
        return lang or "en"

    async def health(self) -> dict:
        try:
            self._load()
            return {
                "status": "up",
                "provider": self.name,
                "model": self.model_name,
                "device": self.device,
            }
        except Exception as exc:  # missing dep or model download failure
            return {
                "status": "down",
                "provider": self.name,
                "model": self.model_name,
                "device": self.device,
                "detail": str(exc)[:300],
            }
