"""Shared model helpers."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import mapped_column


def uuid_pk():
    return mapped_column(
        String(36), primary_key=True, default=lambda: uuid.uuid4().hex
    )


def utcnow():
    return datetime.now(timezone.utc)


def created_at_col():
    return mapped_column(DateTime(), nullable=False, default=utcnow)


def updated_at_col():
    return mapped_column(DateTime(), nullable=False, default=utcnow, onupdate=utcnow)
