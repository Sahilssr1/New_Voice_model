"""Call / message / event schemas."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.agent import AgentOut


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    text: str
    language: str | None
    intent: str | None
    entities: dict | None
    latency_ms: int | None
    created_at: datetime


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_type: str
    payload: dict | None
    created_at: datetime


class CallOut(BaseModel):
    id: str
    agent_id: str
    agent_name: str
    status: str
    started_at: datetime
    ended_at: datetime | None
    duration_sec: float | None
    language: str | None
    message_count: int
    summary: str | None


class CallDetail(BaseModel):
    id: str
    user_id: str
    agent_id: str
    agent: AgentOut
    status: str
    started_at: datetime
    ended_at: datetime | None
    duration_sec: float | None
    language: str | None
    summary: str | None
    facts: dict | None
    message_count: int
    created_at: datetime
    updated_at: datetime
    messages: list[MessageOut] = []
    events: list[EventOut] = []
