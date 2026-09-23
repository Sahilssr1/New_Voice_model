"""Adaptive energy-based VAD.

Classifies 20 ms frames at 16 kHz as speech when the frame RMS exceeds an
adaptive threshold derived from a slowly-tracked noise floor. No ML model or
extra dependency required, so this is the default/fallback VAD.
"""

from __future__ import annotations

import numpy as np

from .base import VADProvider


class EnergyVAD(VADProvider):
    name = "energy"

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_ms: int = 20,
        min_threshold: float = 0.008,
        adapt_rate: float = 0.02,
        ratio: float = 3.0,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_len = int(sample_rate * frame_ms / 1000)
        self.min_threshold = min_threshold
        self.adapt_rate = adapt_rate
        self.ratio = ratio
        self.noise_floor = min_threshold

    def reset(self) -> None:
        """Reset the tracked noise floor (e.g. at call start)."""
        self.noise_floor = self.min_threshold

    def is_speech(self, chunk: np.ndarray) -> tuple[bool, float]:
        x = np.asarray(chunk, dtype=np.float32).ravel()
        if x.size == 0:
            return False, 0.0
        rms = float(np.sqrt(np.mean(x * x)))
        threshold = max(self.min_threshold, self.noise_floor * self.ratio)
        speech = rms > threshold
        if not speech:
            # Track background noise only during non-speech frames.
            self.noise_floor = (1.0 - self.adapt_rate) * self.noise_floor + self.adapt_rate * rms
            self.noise_floor = max(self.min_threshold * 0.5, self.noise_floor)
        span = threshold - self.noise_floor + 1e-6
        prob = min(1.0, max(0.0, (rms - self.noise_floor) / span))
        return speech, prob

    async def health(self) -> dict:
        return {
            "status": "up",
            "provider": self.name,
            "sample_rate": self.sample_rate,
            "frame_ms": int(self.frame_len / self.sample_rate * 1000),
        }
