"""Tool schemas."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ToolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    parameters: dict | None
    is_builtin: bool
    created_at: datetime


class ToolAttach(BaseModel):
    tool_id: str = Field(min_length=1)
