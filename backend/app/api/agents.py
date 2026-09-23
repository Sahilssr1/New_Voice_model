"""Agent CRUD + voice catalog endpoints."""
import inspect
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, get_db
from app.models.agent import Agent
from app.models.user import User
from app.schemas.agent import AgentCreate, AgentDetail, AgentOut, AgentUpdate
from app.schemas.voice import VoiceOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["agents"])

# Static fallback so the core never hard-crashes when the AI package
# (app.ai.factory, owned by another agent) is unavailable.
FALLBACK_VOICES: list[dict] = [
    {
        "voice_id": "en_US-amy-medium",
        "name": "Amy — English (US) Female",
        "provider": "piper",
        "language": "en",
        "gender": "female",
        "sample_rate": 22050,
    },
    {
        "voice_id": "en_US-ryan-medium",
        "name": "Ryan — English (US) Male",
        "provider": "piper",
        "language": "en",
        "gender": "male",
        "sample_rate": 22050,
    },
    {
        "voice_id": "en_GB-alan-medium",
        "name": "Alan — English (GB) Male",
        "provider": "piper",
        "language": "en",
        "gender": "male",
        "sample_rate": 22050,
    },
    {
        "voice_id": "hi_IN-priyamvada-medium",
        "name": "Priyamvada — Hindi Female",
        "provider": "piper",
        "language": "hi",
        "gender": "female",
        "sample_rate": 22050,
    },
    {
        "voice_id": "hi_IN-rohan-medium",
        "name": "Rohan — Hindi Male",
        "provider": "piper",
        "language": "hi",
        "gender": "male",
        "sample_rate": 22050,
    },
]


async def _get_voice_catalog() -> list[dict]:
    """Load the voice catalog from the TTS provider factory if available."""
    try:
        from app.ai.factory import get_voice_catalog as factory_fn
    except Exception:
        factory_fn = None
    if factory_fn is not None:
        try:
            result = factory_fn()
            if inspect.isawaitable(result):
                result = await result
            normalized = []
            for v in result or []:
                if isinstance(v, dict):
                    normalized.append(v)
                else:  # VoiceMeta-like object
                    normalized.append(
                        {
                            "voice_id": getattr(v, "voice_id", ""),
                            "name": getattr(v, "name", ""),
                            "provider": getattr(v, "provider", "piper"),
                            "language": getattr(v, "language", ""),
                            "gender": getattr(v, "gender", ""),
                            "sample_rate": getattr(v, "sample_rate", 22050),
                        }
                    )
            return normalized
        except Exception:
            logger.warning("get_voice_catalog() failed; using fallback list", exc_info=True)
    return [dict(v) for v in FALLBACK_VOICES]


@router.get("/voices", response_model=list[VoiceOut])
async def list_voices(
    provider: str | None = Query(default=None),
    language: str | None = Query(default=None),
    gender: str | None = Query(default=None),
):
    voices = await _get_voice_catalog()
    if provider:
        voices = [v for v in voices if v.get("provider") == provider]
    if language:
        voices = [v for v in voices if v.get("language") == language]
    if gender:
        voices = [v for v in voices if v.get("gender") == gender]
    return [VoiceOut(**v) for v in voices]


async def _get_owned_agent(
    agent_id: str, user: User, db: AsyncSession, with_tools: bool = False
) -> Agent:
    stmt = select(Agent).where(Agent.id == agent_id, Agent.user_id == user.id)
    if with_tools:
        stmt = stmt.options(selectinload(Agent.tools))
    agent = (await db.execute(stmt)).scalar_one_or_none()
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )
    return agent


@router.get("/agents", response_model=list[AgentOut])
async def list_agents(
    current: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Agent)
        .where(Agent.user_id == current.id)
        .order_by(Agent.created_at.desc())
    )
    return result.scalars().all()


@router.post("/agents", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
async def create_agent(
    data: AgentCreate,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent = Agent(user_id=current.id, **data.model_dump())
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent


@router.get("/agents/{agent_id}", response_model=AgentDetail)
async def get_agent(
    agent_id: str,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_owned_agent(agent_id, current, db, with_tools=True)


@router.patch("/agents/{agent_id}", response_model=AgentOut)
async def update_agent(
    agent_id: str,
    data: AgentUpdate,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent = await _get_owned_agent(agent_id, current, db)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(agent, field, value)
    await db.commit()
    await db.refresh(agent)
    return agent


@router.delete("/agents/{agent_id}")
async def delete_agent(
    agent_id: str,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent = await _get_owned_agent(agent_id, current, db)
    await db.delete(agent)
    await db.commit()
    return {"ok": True}
