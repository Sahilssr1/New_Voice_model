"""Call history endpoints: list / detail / delete."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, get_db
from app.models.agent import Agent
from app.models.call import Call
from app.models.user import User
from app.schemas.call import CallDetail, CallOut, EventOut, MessageOut

router = APIRouter(prefix="/api", tags=["calls"])


def _to_call_out(call: Call, agent_name: str) -> CallOut:
    return CallOut(
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


@router.get("/calls", response_model=list[CallOut])
async def list_calls(
    agent_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Call, Agent.name)
        .join(Agent, Call.agent_id == Agent.id)
        .where(Call.user_id == current.id)
    )
    if agent_id:
        stmt = stmt.where(Call.agent_id == agent_id)
    stmt = stmt.order_by(Call.created_at.desc()).limit(limit)
    rows = (await db.execute(stmt)).all()
    return [_to_call_out(call, agent_name) for call, agent_name in rows]


async def _get_owned_call(call_id: str, user: User, db: AsyncSession) -> Call:
    stmt = (
        select(Call)
        .where(Call.id == call_id, Call.user_id == user.id)
        .options(
            selectinload(Call.agent),
            selectinload(Call.messages),
            selectinload(Call.events),
        )
    )
    call = (await db.execute(stmt)).scalar_one_or_none()
    if call is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Call not found"
        )
    return call


@router.get("/calls/{call_id}", response_model=CallDetail)
async def get_call(
    call_id: str,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    call = await _get_owned_call(call_id, current, db)
    messages = sorted(call.messages, key=lambda m: m.created_at)
    events = sorted(call.events, key=lambda e: e.created_at)
    return CallDetail(
        id=call.id,
        user_id=call.user_id,
        agent_id=call.agent_id,
        agent=call.agent,
        status=call.status,
        started_at=call.started_at,
        ended_at=call.ended_at,
        duration_sec=call.duration_sec,
        language=call.language,
        summary=call.summary,
        facts=call.facts,
        message_count=call.message_count,
        created_at=call.created_at,
        updated_at=call.updated_at,
        messages=[MessageOut.model_validate(m) for m in messages],
        events=[EventOut.model_validate(e) for e in events],
    )


@router.delete("/calls/{call_id}", status_code=status.HTTP_200_OK)
async def delete_call(
    call_id: str,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    call = await _get_owned_call(call_id, current, db)
    await db.delete(call)
    await db.commit()
    return {"ok": True}
