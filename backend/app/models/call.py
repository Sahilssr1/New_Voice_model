"""Call model."""
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._common import created_at_col, updated_at_col, uuid_pk


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # active | completed | failed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    started_at = created_at_col()
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(), nullable=True)
    duration_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    facts: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at = created_at_col()
    updated_at = updated_at_col()

    user: Mapped["User"] = relationship(back_populates="calls")
    agent: Mapped["Agent"] = relationship(back_populates="calls")
    messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="call", cascade="all, delete-orphan"
    )
    events: Mapped[list["CallEvent"]] = relationship(
        back_populates="call", cascade="all, delete-orphan"
    )
