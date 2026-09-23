"""Silero VAD provider (torch).

Loads the open-source Silero VAD model via torch.hub. Raises on init when
torch is unavailable or the model cannot be downloaded -- the factory in
app.ai.factory catches this and falls back to EnergyVAD.
"""

from __future__ import annotations

import numpy as np

from .base import VADProvider

# Silero VAD expects 512-sample windows at 16 kHz.
_SILERO_WINDOW = 512
_BUFFER_KEEP = 1536


class SileroVAD(VADProvider):
    name = "silero"

    def __init__(self, sample_rate: int = 16000, threshold: float = 0.5) -> None:
        try:
            import torch
        except ImportError as exc:
            raise ImportError("torch is required for SileroVAD") from exc
        self._torch = torch
        self.sample_rate = sample_rate
        self.threshold = threshold
        self._buf = np.zeros(0, dtype=np.float32)
        self._last: tuple[bool, float] = (False, 0.0)
        try:
            model, _utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                trust_repo=True,
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to load Silero VAD model: {exc}") from exc
        model.eval()
        self._model = model

    def reset(self) -> None:
        self._buf = np.zeros(0, dtype=np.float32)
        self._last = (False, 0.0)

    def is_speech(self, chunk: np.ndarray) -> tuple[bool, float]:
        x = np.asarray(chunk, dtype=np.float32).ravel()
        if x.size:
            self._buf = np.concatenate([self._buf, x])[-_BUFFER_KEEP:]
        if self._buf.size < _SILERO_WINDOW:
            return self._last
        window = self._buf[-_SILERO_WINDOW:]
        tensor = self._torch.from_numpy(window).unsqueeze(0)
        with self._torch.no_grad():
            prob = float(self._model(tensor, self.sample_rate).item())
        self._last = (prob >= self.threshold, prob)
        return self._last

    async def health(self) -> dict:
        return {
            "status": "up",
            "provider": self.name,
            "sample_rate": self.sample_rate,
            "threshold": self.threshold,
            "torch": getattr(self._torch, "__version__", "unknown"),
        }
