"""Agent, voice catalog, tool, and agent<->tool association models."""
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._common import created_at_col, updated_at_col, uuid_pk

agent_tools = Table(
    "agent_tools",
    Base.metadata,
    Column(
        "agent_id",
        String(36),
        ForeignKey("agents.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tool_id",
        String(36),
        ForeignKey("tools.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="auto")
    voice_gender: Mapped[str] = mapped_column(String(16), nullable=False)
    voice_id: Mapped[str] = mapped_column(String(128), nullable=False)
    tts_provider: Mapped[str] = mapped_column(
        String(32), nullable=False, default="piper"
    )
    llm_model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    greeting: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    max_duration_sec: Mapped[int] = mapped_column(
        Integer, nullable=False, default=600
    )
    silence_timeout_sec: Mapped[int] = mapped_column(
        Integer, nullable=False, default=12
    )
    created_at = created_at_col()
    updated_at = updated_at_col()

    user: Mapped["User"] = relationship(back_populates="agents")
    calls: Mapped[list["Call"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan"
    )
    tools: Mapped[list["Tool"]] = relationship(
        secondary=agent_tools, back_populates="agents"
    )
    knowledge_documents: Mapped[list["KnowledgeDocument"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan"
    )


class AgentVoice(Base):
    """Simple voice catalog table (mirrors TTS provider voice metadata)."""

    __tablename__ = "agent_voices"

    id: Mapped[str] = uuid_pk()
    voice_id: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="piper")
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    gender: Mapped[str] = mapped_column(String(16), nullable=False)
    sample_rate: Mapped[int] = mapped_column(Integer, nullable=False, default=22050)
    created_at = created_at_col()


class Tool(Base):
    __tablename__ = "tools"

    id: Mapped[str] = uuid_pk()
    name: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parameters: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_builtin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    created_at = created_at_col()
    updated_at = updated_at_col()

    agents: Mapped[list["Agent"]] = relationship(
        secondary=agent_tools, back_populates="tools"
    )
