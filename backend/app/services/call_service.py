"""Call lifecycle service: calls, sessions, messages, events.

Writes are defensive: model fields are filtered against actual table columns
so minor schema differences don't crash the realtime pipeline. Every public
write helper never raises for logging-type operations (log_event,
add_message); lifecycle operations (create_call, end_call) raise only when
the models themselves are missing.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

try:
    from sqlalchemy import func, select
except ImportError:  # pragma: no cover - sqlalchemy is a required backend dep
    func = select = None  # type: ignore[assignment]

log = logging.getLogger(__name__)

try:
    from ..models import Call, CallEvent, ConversationMessage

    ConversationSession = None  # no ConversationSession table in this schema
except Exception:  # app.models owned by another agent
    Call = CallEvent = ConversationMessage = ConversationSession = None  # type: ignore[assignment]


def _utcnow():
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


def _kwargs(model_cls, **kw) -> dict:
    """Filter kwargs to columns that actually exist on the model."""
    cols = {c.name for c in model_cls.__table__.columns}
    return {k: v for k, v in kw.items() if k in cols}


# -- calls -----------------------------------------------------------------
async def create_call(db, agent_id: str, user_id: str | None = None, channel: str = "browser"):
    if Call is None:
        raise RuntimeError("app.models.Call is not available")
    call = Call(
        **_kwargs(
            Call,
            id=_new_id(),
            agent_id=agent_id,
            user_id=user_id,
            channel=channel,
            status="active",
            started_at=_utcnow(),
        )
    )
    db.add(call)
    await db.commit()
    await db.refresh(call)
    # Best-effort conversation session row for message FK.
    try:
        if ConversationSession is not None:
            session = ConversationSession(
                **_kwargs(
                    ConversationSession,
                    id=_new_id(),
                    call_id=call.id,
                    facts={},
                    created_at=_utcnow(),
                )
            )
            db.add(session)
            await db.commit()
    except Exception as exc:
        log.warning("Could not create conversation session: %s", exc)
        await db.rollback()
    return call


async def get_call(db, call_id: str, owner_id: str | None = None):
    if Call is None:
        raise RuntimeError("app.models.Call is not available")
    stmt = select(Call).where(Call.id == call_id)
    if owner_id is not None and hasattr(Call, "user_id"):
        stmt = stmt.where(Call.user_id == owner_id)
    result = await db.execute(stmt)
    return result.scalars().first()


async def list_calls(db, agent_id: str | None = None, owner_id: str | None = None) -> list:
    if Call is None:
        raise RuntimeError("app.models.Call is not available")
    stmt = select(Call)
    if agent_id is not None:
        stmt = stmt.where(Call.agent_id == agent_id)
    if owner_id is not None and hasattr(Call, "user_id"):
        stmt = stmt.where(Call.user_id == owner_id)
    stmt = stmt.order_by(Call.started_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def end_call(
    db,
    call_id: str,
    status: str = "completed",
    summary: str | None = None,
    facts: dict | None = None,
    language: str | None = None,
):
    """Finalize a call: status, ended_at, duration, message count, summary."""
    call = await get_call(db, call_id)
    if call is None:
        return None
    ended_at = _utcnow()
    started_at = getattr(call, "started_at", None)
    duration_sec = 0
    if started_at is not None:
        try:
            duration_sec = int((ended_at - started_at).total_seconds())
        except Exception:
            duration_sec = 0
    message_count = await _count_messages(db, call_id)
    for key, value in _kwargs(
        Call,
        status=status,
        ended_at=ended_at,
        duration_sec=max(0, duration_sec),
        message_count=message_count,
        summary=summary,
        facts=facts or {},
        language=language,
    ).items():
        setattr(call, key, value)
    await db.commit()
    await db.refresh(call)
    return call


async def _count_messages(db, call_id: str) -> int:
    try:
        if ConversationMessage is None:
            return 0
        cols = {c.name for c in ConversationMessage.__table__.columns}
        stmt = select(func.count()).select_from(ConversationMessage)
        if "call_id" in cols:
            stmt = stmt.where(ConversationMessage.call_id == call_id)
        elif "session_id" in cols:
            session = await get_session(db, call_id)
            if session is None:
                return 0
            stmt = stmt.where(ConversationMessage.session_id == session.id)
        else:
            return 0
        return int((await db.execute(stmt)).scalar() or 0)
    except Exception as exc:
        log.warning("Message count failed: %s", exc)
        return 0


# -- sessions --------------------------------------------------------------
async def get_session(db, call_id: str):
    if ConversationSession is None:
        return None
    result = await db.execute(
        select(ConversationSession).where(ConversationSession.call_id == call_id)
    )
    return result.scalars().first()


async def get_or_create_session(db, call_id: str):
    session = await get_session(db, call_id)
    if session is not None or ConversationSession is None:
        return session
    try:
        session = ConversationSession(
            **_kwargs(
                ConversationSession,
                id=_new_id(),
                call_id=call_id,
                facts={},
                created_at=_utcnow(),
            )
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
    except Exception as exc:
        log.warning("get_or_create_session failed: %s", exc)
        await db.rollback()
        return None
    return session


async def update_session_summary(db, session_id: str, summary: str | None, facts: dict | None) -> None:
    """Persist memory summary/facts on the session row (best effort)."""
    try:
        if ConversationSession is None:
            return
        result = await db.execute(
            select(ConversationSession).where(ConversationSession.id == session_id)
        )
        session = result.scalars().first()
        if session is None:
            return
        for key, value in _kwargs(
            ConversationSession, summary=summary, facts=facts or {}
        ).items():
            setattr(session, key, value)
        await db.commit()
    except Exception as exc:
        log.warning("update_session_summary failed: %s", exc)
        await db.rollback()


# -- messages --------------------------------------------------------------
async def add_message(
    db,
    call_id: str,
    role: str,
    text: str,
    language: str | None = None,
    intent: str | None = None,
    entities: dict | None = None,
    latency_ms: int | None = None,
    session_id: str | None = None,
):
    """Persist one conversation message. Never raises."""
    try:
        if ConversationMessage is None:
            return None
        if session_id is None:
            session = await get_or_create_session(db, call_id)
            session_id = getattr(session, "id", None) if session else None
        msg = ConversationMessage(
            **_kwargs(
                ConversationMessage,
                id=_new_id(),
                session_id=session_id,
                call_id=call_id,
                role=role,
                text=text,
                language=language,
                intent=intent,
                entities=entities or {},
                latency_ms=latency_ms,
                created_at=_utcnow(),
            )
        )
        db.add(msg)
        await db.commit()
        return msg
    except Exception as exc:
        log.warning("add_message failed: %s", exc)
        await db.rollback()
        return None


async def list_messages(db, call_id: str, session_id: str | None = None) -> list:
    if ConversationMessage is None:
        return []
    cols = {c.name for c in ConversationMessage.__table__.columns}
    stmt = select(ConversationMessage)
    if "call_id" in cols:
        stmt = stmt.where(ConversationMessage.call_id == call_id)
    elif "session_id" in cols:
        if session_id is None:
            session = await get_session(db, call_id)
            session_id = getattr(session, "id", None) if session else None
        if session_id is None:
            return []
        stmt = stmt.where(ConversationMessage.session_id == session_id)
    if "created_at" in cols:
        stmt = stmt.order_by(ConversationMessage.created_at.asc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


# -- events ----------------------------------------------------------------
async def log_event(db, call_id: str, event_type: str, payload: dict | None = None):
    """Append a CallEvent row. Never raises (observability must not break calls)."""
    try:
        if CallEvent is None:
            return None
        event = CallEvent(
            **_kwargs(
                CallEvent,
                id=_new_id(),
                call_id=call_id,
                event_type=event_type,
                payload=payload or {},
                created_at=_utcnow(),
            )
        )
        db.add(event)
        await db.commit()
        return event
    except Exception as exc:
        log.warning("log_event(%s) failed: %s", event_type, exc)
        await db.rollback()
        return None


async def list_events(db, call_id: str) -> list:
    if CallEvent is None:
        return []
    stmt = select(CallEvent).where(CallEvent.call_id == call_id)
    if hasattr(CallEvent, "created_at"):
        stmt = stmt.order_by(CallEvent.created_at.asc())
    result = await db.execute(stmt)
    return list(result.scalars().all())
