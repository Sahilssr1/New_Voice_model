"""Agent schemas."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.tool import ToolOut

ALLOWED_LANGUAGES = {
    "auto",
    "en",
    "hi",
    "hinglish",
    "es",
    "fr",
    "de",
    "pt",
    "it",
    "ja",
    "zh",
}
ALLOWED_GENDERS = {"female", "male"}


class AgentBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    system_prompt: str = Field(min_length=1)
    language: str = "auto"
    voice_gender: str
    voice_id: str = Field(min_length=1, max_length=128)
    tts_provider: str = "piper"
    llm_model: str | None = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    greeting: str | None = None
    max_duration_sec: int = Field(default=600, gt=0)
    silence_timeout_sec: int = Field(default=12, gt=0)

    @field_validator("language")
    @classmethod
    def _validate_language(cls, v: str) -> str:
        if v not in ALLOWED_LANGUAGES:
            raise ValueError(f"language must be one of {sorted(ALLOWED_LANGUAGES)}")
        return v

    @field_validator("voice_gender")
    @classmethod
    def _validate_gender(cls, v: str) -> str:
        if v not in ALLOWED_GENDERS:
            raise ValueError("voice_gender must be 'female' or 'male'")
        return v


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    system_prompt: str | None = Field(default=None, min_length=1)
    language: str | None = None
    voice_gender: str | None = None
    voice_id: str | None = Field(default=None, min_length=1, max_length=128)
    tts_provider: str | None = None
    llm_model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    greeting: str | None = None
    max_duration_sec: int | None = Field(default=None, gt=0)
    silence_timeout_sec: int | None = Field(default=None, gt=0)

    @field_validator("language")
    @classmethod
    def _validate_language(cls, v: str | None) -> str | None:
        if v is not None and v not in ALLOWED_LANGUAGES:
            raise ValueError(f"language must be one of {sorted(ALLOWED_LANGUAGES)}")
        return v

    @field_validator("voice_gender")
    @classmethod
    def _validate_gender(cls, v: str | None) -> str | None:
        if v is not None and v not in ALLOWED_GENDERS:
            raise ValueError("voice_gender must be 'female' or 'male'")
        return v


class AgentOut(AgentBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime


class AgentDetail(AgentOut):
    tools: list[ToolOut] = []
