"""Speech-to-text provider interface.

Implementations (e.g. faster-whisper) live beside this module. Business logic
must depend only on SpeechToTextProvider so another open-source STT engine can
be swapped in later.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass
class STTResult:
    text: str
    language: str
    confidence: float
    duration_ms: int


class SpeechToTextProvider(ABC):
    """Abstract speech-to-text provider."""

    name: str = "base"

    @abstractmethod
    async def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int,
        language: str | None = None,
    ) -> STTResult:
        """Transcribe float32 mono audio to text.

        Args:
            audio: 1-D float32 numpy array, mono.
            sample_rate: sample rate of ``audio`` in Hz.
            language: optional ISO language hint (e.g. "en", "hi") or None
                for auto-detect.
        """

    @abstractmethod
    async def detect_language(self, audio: np.ndarray, sample_rate: int) -> str:
        """Return the ISO-639-1 language code spoken in ``audio``."""

    @abstractmethod
    async def health(self) -> dict:
        """Return a health dict, e.g. {"status": "up", ...}."""
