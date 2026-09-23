"""Conversation message and call event models.

Messages and events belong directly to a Call (``calls`` table); there is no
separate conversation_sessions table in this schema.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._common import uuid_pk


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[str] = uuid_pk()
    call_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("calls.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # user | assistant | tool | system
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    intent: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    entities: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), nullable=False, default=_utcnow
    )

    call: Mapped["Call"] = relationship(back_populates="messages")


class CallEvent(Base):
    __tablename__ = "call_events"

    id: Mapped[str] = uuid_pk()
    call_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("calls.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), nullable=False, default=_utcnow
    )

    call: Mapped["Call"] = relationship(back_populates="events")
