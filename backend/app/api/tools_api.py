"""Tool catalog endpoints + attach/detach tools to agents.

Also owns the builtin-tool seed list (mock CRM-style tools from the spec)
so ``GET /api/tools`` is useful out of the box.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, get_db
from app.db.database import async_session
from app.models.agent import Agent, Tool
from app.models.user import User
from app.schemas.tool import ToolAttach, ToolOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["tools"])

BUILTIN_TOOLS: list[dict] = [
    {
        "name": "get_order_status",
        "description": "Look up the status of a customer order by order ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "The order identifier, e.g. '12345'",
                }
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "get_customer_details",
        "description": "Fetch customer profile details by customer ID or phone.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "phone": {"type": "string"},
            },
        },
    },
    {
        "name": "create_support_ticket",
        "description": "Open a support ticket for the caller.",
        "parameters": {
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "description": {"type": "string"},
                "priority": {
                    "type": "string",
                    "enum": ["low", "normal", "high"],
                },
            },
            "required": ["subject", "description"],
        },
    },
    {
        "name": "schedule_callback",
        "description": "Schedule a callback from a human agent.",
        "parameters": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "when": {
                    "type": "string",
                    "description": "ISO-8601 datetime for the callback",
                },
                "reason": {"type": "string"},
            },
            "required": ["phone", "when"],
        },
    },
    {
        "name": "transfer_to_human",
        "description": "Hand the call off to a human agent.",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {"type": "string"},
                "department": {"type": "string"},
            },
            "required": ["reason"],
        },
    },
]


async def seed_builtin_tools() -> None:
    """Insert builtin tool rows if the tools table is empty. Idempotent."""
    async with async_session() as db:
        count = (await db.execute(select(Tool).limit(1))).scalar_one_or_none()
        if count is not None:
            return
        for spec in BUILTIN_TOOLS:
            db.add(Tool(is_builtin=True, **spec))
        await db.commit()
        logger.info("seeded %d builtin tools", len(BUILTIN_TOOLS))


@router.get("/tools", response_model=list[ToolOut])
async def list_tools(
    current: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Tool).order_by(Tool.name))
    return result.scalars().all()


async def _get_owned_agent(agent_id: str, user: User, db: AsyncSession) -> Agent:
    agent = (
        await db.execute(
            select(Agent)
            .where(Agent.id == agent_id, Agent.user_id == user.id)
            .options(selectinload(Agent.tools))
        )
    ).scalar_one_or_none()
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )
    return agent


@router.post("/agents/{agent_id}/tools")
async def attach_tool(
    agent_id: str,
    data: ToolAttach,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent = await _get_owned_agent(agent_id, current, db)
    tool = (
        await db.execute(select(Tool).where(Tool.id == data.tool_id))
    ).scalar_one_or_none()
    if tool is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found"
        )
    if tool not in agent.tools:
        agent.tools.append(tool)
        await db.commit()
    return {"ok": True}


@router.delete("/agents/{agent_id}/tools/{tool_id}")
async def detach_tool(
    agent_id: str,
    tool_id: str,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent = await _get_owned_agent(agent_id, current, db)
    tool = (
        await db.execute(select(Tool).where(Tool.id == tool_id))
    ).scalar_one_or_none()
    if tool is None or tool not in agent.tools:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tool not attached to agent",
        )
    agent.tools.remove(tool)
    await db.commit()
    return {"ok": True}
