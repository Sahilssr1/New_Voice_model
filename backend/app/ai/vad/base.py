"""Voice activity detection provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class VADProvider(ABC):
    """Abstract VAD provider operating on raw audio frames."""

    name: str = "base"
    sample_rate: int = 16000

    @abstractmethod
    def is_speech(self, chunk: np.ndarray) -> tuple[bool, float]:
        """Classify one audio frame.

        Args:
            chunk: 1-D float32 mono audio (typically 20 ms @ 16 kHz).

        Returns:
            (is_speech, probability) tuple.
        """

    @abstractmethod
    async def health(self) -> dict:
        """Return a health dict, e.g. {"status": "up", ...}."""
