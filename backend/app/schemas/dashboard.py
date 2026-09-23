"""Dashboard schema."""
from pydantic import BaseModel

from app.schemas.call import CallOut


class DashboardOut(BaseModel):
    total_agents: int
    total_calls: int
    total_duration_sec: float
    successful_calls: int
    failed_calls: int
    languages: dict[str, int]
    recent_calls: list[CallOut]
