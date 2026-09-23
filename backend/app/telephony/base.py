"""Telephony provider interface.

Future: Phone -> SIP -> Asterisk/FreeSWITCH -> Voice Gateway -> AI Agent.
The voice pipeline is audio-source agnostic: a telephony provider feeds raw
int16 mono PCM into VoicePipeline.on_audio() exactly like the WebSocket
gateway does, and consumes PCM from the pipeline's emit callback.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

log = logging.getLogger(__name__)


class TelephonyProvider(ABC):
    """Abstract telephony provider (SIP/PSTN bridge)."""

    name: str = "base"

    @abstractmethod
    async def place_call(
        self, to_number: str, *, agent_id: str | None = None, metadata: dict | None = None
    ) -> str:
        """Place an outbound call; returns a provider call id."""

    @abstractmethod
    async def answer_call(self, call_id: str) -> None:
        """Answer an inbound call."""

    @abstractmethod
    async def hangup(self, call_id: str) -> None:
        """Hang up a call."""

    @abstractmethod
    async def send_audio(
        self, call_id: str, pcm_bytes: bytes, sample_rate: int = 22050
    ) -> None:
        """Send agent audio (int16 LE mono PCM) toward the caller."""

    @abstractmethod
    def on_audio(self, callback) -> None:
        """Register ``callback(call_id, pcm16le_16k_bytes)`` for inbound audio."""


class NoopTelephonyProvider(TelephonyProvider):
    """No-op provider used until a real SIP stack is wired in."""

    name = "noop"

    def __init__(self) -> None:
        self._callback = None

    async def place_call(self, to_number: str, *, agent_id=None, metadata=None) -> str:
        log.info("NoopTelephonyProvider.place_call to=%s (noop)", to_number)
        return f"noop-{to_number}"

    async def answer_call(self, call_id: str) -> None:
        log.info("NoopTelephonyProvider.answer_call %s (noop)", call_id)

    async def hangup(self, call_id: str) -> None:
        log.info("NoopTelephonyProvider.hangup %s (noop)", call_id)

    async def send_audio(self, call_id: str, pcm_bytes: bytes, sample_rate: int = 22050) -> None:
        log.debug("NoopTelephonyProvider.send_audio %s %d bytes (noop)", call_id, len(pcm_bytes))

    def on_audio(self, callback) -> None:
        self._callback = callback
