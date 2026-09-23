"""Null TTS provider.

Yields 0.3 s of silence per sentence. Used for tests and as a last-resort
fallback so the voice pipeline never crashes when no real TTS engine is
available.
"""

from __future__ import annotations

import re
from typing import AsyncIterator

import numpy as np

from .base import TextToSpeechProvider, VoiceMeta

SAMPLE_RATE = 22050


class NullTTS(TextToSpeechProvider):
    name = "null"

    async def list_voices(self) -> list[VoiceMeta]:
        return [
            VoiceMeta("null-female", "Null Female", "null", "en", "female", SAMPLE_RATE),
            VoiceMeta("null-male", "Null Male", "null", "en", "male", SAMPLE_RATE),
        ]

    async def synthesize(
        self,
        text: str,
        voice_id: str,
        language: str | None = None,
        speed: float = 1.0,
    ) -> AsyncIterator[tuple[bytes, int]]:
        sentences = [s for s in re.split(r"(?<=[.!?…।])\s+|\n+", text or "") if s.strip()]
        if not sentences:
            sentences = [""]
        n = int(SAMPLE_RATE * 0.3)
        silence = np.zeros(n, dtype=np.int16).tobytes()
        for _ in sentences:
            yield silence, SAMPLE_RATE

    async def health(self) -> dict:
        return {"status": "up", "provider": self.name}
