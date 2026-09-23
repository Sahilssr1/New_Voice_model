"""Async SQLAlchemy engine/session.

Supports both ``sqlite+aiosqlite`` (dev) and ``postgresql+asyncpg`` (docker).
"""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.base import Base


def _engine_kwargs() -> dict:
    if settings.DATABASE_URL.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {}


engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    future=True,
    **_engine_kwargs(),
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    """FastAPI dependency yielding an AsyncSession."""
    async with async_session() as session:
        yield session


async def init_db() -> None:
    """Create all tables (dev convenience; alembic owns migrations in docker)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
