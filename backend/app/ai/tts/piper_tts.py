"""Piper TTS provider (open-source neural TTS, ONNX).

Voices are loaded lazily per voice_id from TTS_VOICES_DIR. If a voice file is
missing, a best-effort download is attempted via
``python -m piper.download_voices <voice_id>``.

This module follows the documented piper-tts Python API
(``from piper import PiperVoice`` / ``PiperVoice.load`` /
``voice.synthesize(text, wav_file, ...)``). ``piper`` is imported lazily so
this module is importable without it.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import subprocess
import sys
import wave
from pathlib import Path
from typing import AsyncIterator

import numpy as np

from .base import TextToSpeechProvider, VoiceMeta

log = logging.getLogger(__name__)

# Static voice catalog: voice_id -> metadata. No gender/language assumptions
# are hard-coded anywhere else; selection is driven by this metadata.
PIPER_CATALOG: list[VoiceMeta] = [
    VoiceMeta("en_US-amy-medium", "Amy", "piper", "en", "female", 22050),
    VoiceMeta("en_US-lessac-medium", "Lessac", "piper", "en", "male", 22050),
    VoiceMeta("en_US-ryan-medium", "Ryan", "piper", "en", "male", 22050),
    VoiceMeta("hi_IN-priyamvada-medium", "Priyamvada", "piper", "hi", "female", 22050),
]

# ~0.5 s audio chunks at 22050 Hz.
_CHUNK_SAMPLES = 11025


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?…।])\s+|\n+", text or "")
    return [p.strip() for p in parts if p.strip()]


class PiperTTS(TextToSpeechProvider):
    name = "piper"

    def __init__(self, voices_dir: str | None = None) -> None:
        self.voices_dir = Path(
            voices_dir or os.environ.get("TTS_VOICES_DIR", "./voices")
        )
        self._voices: dict[str, object] = {}

    # -- voice loading -----------------------------------------------------
    def _find_onnx(self, voice_id: str) -> Path | None:
        """Search voices_dir recursively for <voice_id>.onnx.

        ``piper.download_voices`` nests files like
        voices/en/en_US/amy/medium/en_US-amy-medium.onnx, so a recursive
        search covers both flat and nested layouts.
        """
        try:
            matches = sorted(self.voices_dir.rglob(f"{voice_id}.onnx"))
        except OSError:
            return None
        return matches[0] if matches else None

    def _ensure_voice_files(self, voice_id: str) -> Path | None:
        onnx = self._find_onnx(voice_id)
        if onnx is not None:
            return onnx
        # Best-effort download; never fatal.
        try:
            self.voices_dir.mkdir(parents=True, exist_ok=True)
            log.info("Piper voice '%s' missing, attempting download", voice_id)
            subprocess.run(
                [sys.executable, "-m", "piper.download_voices", voice_id],
                cwd=str(self.voices_dir),
                timeout=180,
                capture_output=True,
            )
        except Exception as exc:
            log.warning("Piper voice download failed for '%s': %s", voice_id, exc)
        return self._find_onnx(voice_id)

    def _get_voice(self, voice_id: str):
        """Load (and cache) a PiperVoice. Blocking; call from a worker thread."""
        if voice_id not in self._voices:
            try:
                from piper import PiperVoice
            except ImportError as exc:
                raise RuntimeError(
                    "piper-tts is not installed; cannot synthesize speech"
                ) from exc
            onnx = self._ensure_voice_files(voice_id)
            if onnx is None:
                raise RuntimeError(
                    f"Piper voice '{voice_id}' not found in {self.voices_dir}"
                )
            config_path = onnx.with_suffix(".onnx.json")
            self._voices[voice_id] = PiperVoice.load(
                str(onnx),
                config_path=str(config_path) if config_path.exists() else None,
                use_cuda=False,
            )
        return self._voices[voice_id]

    def _synth_sentence(self, voice, sentence: str, length_scale: float) -> tuple[bytes, int]:
        """Synthesize one sentence -> (pcm16le bytes, sample_rate). Blocking."""
        from piper.config import SynthesisConfig

        syn_config = SynthesisConfig(length_scale=length_scale)
        chunks: list[bytes] = []
        sample_rate = 22050
        # piper-tts >= 1.8 API: synthesize(text, syn_config) -> AudioChunk stream
        for chunk in voice.synthesize(sentence, syn_config=syn_config):
            chunks.append(chunk.audio_int16_bytes)
            sample_rate = getattr(chunk, "sample_rate", sample_rate) or sample_rate
        pcm = b"".join(chunks)
        if not pcm:
            raise RuntimeError("piper produced no audio")
        # sample rate comes from the voice config; read it from the model file
        return pcm, self._voice_sample_rate(voice, sample_rate)

    @staticmethod
    def _voice_sample_rate(voice, default: int) -> int:
        try:
            return int(voice.config.sample_rate)
        except Exception:
            return default

    # -- API ---------------------------------------------------------------
    async def list_voices(self) -> list[VoiceMeta]:
        return list(PIPER_CATALOG)

    async def synthesize(
        self,
        text: str,
        voice_id: str,
        language: str | None = None,
        speed: float = 1.0,
    ) -> AsyncIterator[tuple[bytes, int]]:
        voice = await asyncio.to_thread(self._get_voice, voice_id)
        sentences = _split_sentences(text)
        if not sentences:
            return
        length_scale = 1.0 / max(0.5, min(2.0, float(speed or 1.0)))
        for sentence in sentences:
            pcm, sample_rate = await asyncio.to_thread(
                self._synth_sentence, voice, sentence, length_scale
            )
            # Yield ~0.5 s chunks so playback can start before the full
            # utterance is synthesized.
            step = _CHUNK_SAMPLES * 2  # int16 -> 2 bytes/sample
            for i in range(0, len(pcm), step):
                yield pcm[i : i + step], sample_rate

    async def health(self) -> dict:
        try:
            import piper  # noqa: F401

            piper_ok = True
        except ImportError:
            piper_ok = False
        available = []
        if piper_ok:
            for meta in PIPER_CATALOG:
                if self._find_onnx(meta.voice_id) is not None:
                    available.append(meta.voice_id)
        if not piper_ok:
            status, detail = "down", "piper-tts is not installed"
        elif not available:
            status, detail = (
                "degraded",
                f"piper installed but no voices found in {self.voices_dir}",
            )
        else:
            status, detail = "up", None
        out = {
            "status": status,
            "provider": self.name,
            "voices_dir": str(self.voices_dir),
            "voices_available": available,
        }
        if detail:
            out["detail"] = detail
        return out
