"""Voice catalog schema."""
from pydantic import BaseModel


class VoiceOut(BaseModel):
    voice_id: str
    name: str
    provider: str = "piper"
    language: str
    gender: str
    sample_rate: int = 22050
