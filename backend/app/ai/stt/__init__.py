"""Speech-to-text provider abstraction."""

from .base import SpeechToTextProvider, STTResult
from .faster_whisper import FasterWhisperSTT

__all__ = ["SpeechToTextProvider", "STTResult", "FasterWhisperSTT"]
