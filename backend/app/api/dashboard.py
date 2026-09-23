"""Dashboard stats endpoint."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.agent import Agent
from app.models.call import Call
from app.models.user import User
from app.schemas.call import CallOut
from app.schemas.dashboard import DashboardOut

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardOut)
async def dashboard(
    current: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    total_agents = (
        await db.execute(
            select(func.count()).select_from(Agent).where(Agent.user_id == current.id)
        )
    ).scalar() or 0

    total_calls = (
        await db.execute(
            select(func.count()).select_from(Call).where(Call.user_id == current.id)
        )
    ).scalar() or 0

    total_duration = (
        await db.execute(
            select(func.coalesce(func.sum(Call.duration_sec), 0)).where(
                Call.user_id == current.id
            )
        )
    ).scalar() or 0

    successful_calls = (
        await db.execute(
            select(func.count())
            .select_from(Call)
            .where(Call.user_id == current.id, Call.status == "completed")
        )
    ).scalar() or 0

    failed_calls = (
        await db.execute(
            select(func.count())
            .select_from(Call)
            .where(Call.user_id == current.id, Call.status == "failed")
        )
    ).scalar() or 0

    lang_rows = (
        await db.execute(
            select(Call.language, func.count())
            .where(Call.user_id == current.id, Call.language.isnot(None))
            .group_by(Call.language)
        )
    ).all()
    languages = {lang: count for lang, count in lang_rows}

    recent_rows = (
        await db.execute(
            select(Call, Agent.name)
            .join(Agent, Call.agent_id == Agent.id)
            .where(Call.user_id == current.id)
            .order_by(Call.created_at.desc())
            .limit(5)
        )
    ).all()
    recent_calls = [
        CallOut(
            id=call.id,
            agent_id=call.agent_id,
            agent_name=agent_name,
            status=call.status,
            started_at=call.started_at,
            ended_at=call.ended_at,
            duration_sec=call.duration_sec,
            language=call.language,
            message_count=call.message_count,
            summary=call.summary,
        )
        for call, agent_name in recent_rows
    ]

    return DashboardOut(
        total_agents=total_agents,
        total_calls=total_calls,
        total_duration_sec=float(total_duration),
        successful_calls=successful_calls,
        failed_calls=failed_calls,
        languages=languages,
        recent_calls=recent_calls,
    )
