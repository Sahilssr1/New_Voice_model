"""Agent CRUD service (async SQLAlchemy session).

Model classes live in app.models (owned by another builder); they are
imported defensively so this module stays importable without them.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

try:
    from sqlalchemy import select
except ImportError:  # pragma: no cover - sqlalchemy is a required backend dep
    select = None  # type: ignore[assignment]

log = logging.getLogger(__name__)

try:
    from ..models import Agent
except Exception:  # app.models owned by another agent
    Agent = None  # type: ignore[assignment]

try:
    from ..models import Tool, agent_tools
except Exception:
    Tool = None  # type: ignore[assignment]
    agent_tools = None  # type: ignore[assignment]


def _require_models():
    if Agent is None:
        raise RuntimeError("app.models.Agent is not available")
    if select is None:
        raise RuntimeError("sqlalchemy is required")
    return Agent


def _utcnow():
    return datetime.now(timezone.utc)


async def list_agents(db, owner_id: str) -> list:
    _require_models()
    result = await db.execute(
        select(Agent).where(Agent.user_id == owner_id).order_by(Agent.created_at.desc())
    )
    return list(result.scalars().all())


async def get_agent(db, agent_id: str, owner_id: str | None = None):
    _require_models()
    stmt = select(Agent).where(Agent.id == agent_id)
    if owner_id is not None:
        stmt = stmt.where(Agent.user_id == owner_id)
    result = await db.execute(stmt)
    return result.scalars().first()


async def create_agent(db, owner_id: str, data: dict):
    _require_models()
    agent = Agent(user_id=owner_id, **data)
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent


async def update_agent(db, agent_id: str, owner_id: str, data: dict):
    agent = await get_agent(db, agent_id, owner_id)
    if agent is None:
        return None
    for key, value in (data or {}).items():
        if hasattr(agent, key):
            setattr(agent, key, value)
    agent.updated_at = _utcnow()
    await db.commit()
    await db.refresh(agent)
    return agent


async def delete_agent(db, agent_id: str, owner_id: str) -> bool:
    agent = await get_agent(db, agent_id, owner_id)
    if agent is None:
        return False
    await db.delete(agent)
    await db.commit()
    return True


async def get_agent_tool_names(db, agent_id: str) -> list[str] | None:
    """Return the tool names attached to an agent, or None if unavailable.

    None means "no filtering information" (caller should use all tools).
    """
    if Tool is None or agent_tools is None:
        return None
    try:
        result = await db.execute(
            select(Tool.name)
            .select_from(agent_tools)
            .join(Tool, Tool.id == agent_tools.c.tool_id)
            .where(agent_tools.c.agent_id == agent_id)
        )
        return [row[0] for row in result.all()]
    except Exception as exc:
        log.warning("get_agent_tool_names failed: %s", exc)
        return None
