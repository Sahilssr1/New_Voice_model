"""Application configuration via pydantic-settings.

All values come from environment variables (``.env`` supported).
See CONTRACT.md for the canonical list.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "VoiceAgent Platform"
    APP_VERSION: str = "0.1.0"

    # sqlite+aiosqlite:///./voiceagent.db  (dev default)
    # docker: postgresql+asyncpg://voice:voice@postgres:5432/voiceagent
    DATABASE_URL: str = "sqlite+aiosqlite:///./voiceagent.db"
    REDIS_URL: str = "redis://localhost:6379/0"  # optional; in-memory fallback

    JWT_SECRET: str = "change-me"
    JWT_EXPIRE_MINUTES: int = 10080

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    DEFAULT_LLM_MODEL: str = "qwen2.5:1.5b"

    WHISPER_MODEL: str = "base"
    WHISPER_DEVICE: str = "cpu"

    TTS_VOICES_DIR: str = "./voices"

    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Knowledge base (RAG)
    KB_ENABLED: bool = True
    # Multilingual embeddings: English, Hindi (Devanagari), Hinglish (~420 MB download)
    KB_MODEL: str = "paraphrase-multilingual-MiniLM-L12-v2"  # sentence-transformers id
    KB_CHUNK_SIZE: int = 600
    KB_CHUNK_OVERLAP: int = 100
    KB_TOP_K: int = 3
    KB_MIN_SCORE: float = 0.25
    KB_MAX_FILE_MB: int = 10

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
