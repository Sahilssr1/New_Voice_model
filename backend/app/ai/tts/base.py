"""Text-to-speech provider interface.

Implementations (Piper, Null) live beside this module. Voice selection is
metadata-driven (VoiceMeta) so no gender/language assumptions are hard-coded
into the backend.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class VoiceMeta:
    voice_id: str
    name: str
    provider: str
    language: str
    gender: str  # "female" | "male"
    sample_rate: int


class TextToSpeechProvider(ABC):
    """Abstract text-to-speech provider."""

    name: str = "base"

    @abstractmethod
    async def list_voices(self) -> list[VoiceMeta]:
        """Return the available voices with their metadata."""

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        voice_id: str,
        language: str | None = None,
        speed: float = 1.0,
    ) -> AsyncIterator[tuple[bytes, int]]:
        """Synthesize text to speech.

        Yields:
            (pcm16le_bytes, sample_rate) chunks of mono 16-bit PCM audio.
        """

    @abstractmethod
    async def health(self) -> dict:
        """Return a health dict, e.g. {"status": "up", ...}."""
