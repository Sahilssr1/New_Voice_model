"""Silero VAD provider (torch).

Loads the open-source Silero VAD TorchScript model. Preferred source is the
``silero-vad`` PyPI package data (``silero_vad/data/silero_vad.jit``), loaded
directly with ``torch.jit.load`` -- no ``torch.hub`` download and no
``torchaudio`` required. Falls back to ``torch.hub.load`` when the package is
absent. Raises on init when torch is unavailable or no model file can be
found -- the factory in app.ai.factory catches this and falls back to
EnergyVAD.

The model is stateful (LSTM); feed it consecutive non-overlapping 512-sample
windows and call :meth:`reset` at utterance/call boundaries.
"""

from __future__ import annotations

import logging
import os

import numpy as np

from .base import VADProvider

log = logging.getLogger(__name__)

# Silero VAD expects 512-sample windows at 16 kHz.
_SILERO_WINDOW = 512


def _find_model_file() -> str | None:
    """Locate silero_vad.jit without any network access.

    Note: importing the ``silero_vad`` package itself is avoided -- its
    ``__init__`` pulls in torchaudio, whose native lib may fail to load on
    minimal systems. The TorchScript model file is found by path instead.
    """
    # 1. Explicit override (e.g. a vendored copy shipped with the app).
    env = os.environ.get("SILERO_VAD_MODEL")
    if env and os.path.isfile(env):
        return env
    # 2. The silero-vad PyPI package bundles the TorchScript model at
    #    <site-packages>/silero_vad/data/silero_vad.jit.
    import sys

    for sp in sys.path:
        candidate = os.path.join(sp, "silero_vad", "data", "silero_vad.jit")
        if os.path.isfile(candidate):
            return candidate
    return None


class SileroVAD(VADProvider):
    name = "silero"

    def __init__(self, sample_rate: int = 16000, threshold: float = 0.5) -> None:
        try:
            import torch
        except ImportError as exc:
            raise ImportError("torch is required for SileroVAD") from exc
        self._torch = torch
        self.sample_rate = sample_rate
        self.threshold = float(os.environ.get("VAD_THRESHOLD", threshold))
        self._buf = np.zeros(0, dtype=np.float32)
        self._last: tuple[bool, float] = (False, 0.0)

        model_file = _find_model_file()
        if model_file is not None:
            log.info("Loading Silero VAD TorchScript model from %s", model_file)
            model = torch.jit.load(model_file, map_location="cpu")
        else:
            # Legacy path: download via torch.hub (needs network + torchaudio).
            log.info("No local Silero model file; trying torch.hub download")
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
        self.reset()

    def reset(self) -> None:
        """Clear the LSTM state and any buffered audio (call boundaries)."""
        self._buf = np.zeros(0, dtype=np.float32)
        self._last = (False, 0.0)
        reset_states = getattr(self._model, "reset_states", None)
        if callable(reset_states):
            try:
                reset_states()
            except Exception as exc:
                log.warning("Silero reset_states failed: %s", exc)

    def is_speech(self, chunk: np.ndarray) -> tuple[bool, float]:
        x = np.asarray(chunk, dtype=np.float32).ravel()
        if x.size:
            self._buf = np.concatenate([self._buf, x])
        # Feed the stateful model consecutive non-overlapping windows.
        while self._buf.size >= _SILERO_WINDOW:
            window = self._buf[:_SILERO_WINDOW]
            self._buf = self._buf[_SILERO_WINDOW:]
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
