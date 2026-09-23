"""Health check endpoints.

GET /health            -> overall status + per-service statuses
GET /health/ai         -> {stt, tts, llm, vad} provider health
GET /health/stt|tts|llm|database|redis -> individual service health

This router is mounted WITHOUT a prefix (paths are /health* per contract);
app/main.py decides the final mount point. Redis is optional: the app works
without it and reports {"status": "down"} instead of crashing.
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter

from ..ai.factory import get_ai_health, get_llm, get_stt, get_tts, get_vad

log = logging.getLogger(__name__)

router = APIRouter()

VERSION = "0.1.0"


async def _check_database() -> dict:
    try:
        from ..db import database as dbmod  # owned by another agent
    except Exception as exc:
        return {"status": "down", "detail": f"db module unavailable: {exc}"[:200]}
    engine = getattr(dbmod, "engine", None)
    if engine is None:
        return {"status": "down", "detail": "no engine in app.db.database"}
    try:
        from sqlalchemy import text

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "up"}
    except Exception as exc:
        return {"status": "down", "detail": str(exc)[:200]}


async def _check_redis() -> dict:
    try:
        import redis.asyncio as redis
    except ImportError:
        return {"status": "down", "detail": "redis package not installed"}
    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        client = redis.from_url(url, socket_connect_timeout=2.0)
        try:
            await client.ping()
        finally:
            try:
                await client.aclose()
            except Exception:
                pass
        return {"status": "up"}
    except Exception as exc:
        return {"status": "down", "detail": str(exc)[:200]}


async def _provider_health(getter, key: str) -> dict:
    try:
        return await getter().health()
    except Exception as exc:
        return {"status": "down", "provider": key, "detail": str(exc)[:200]}


@router.get("/health")
async def health():
    ai = await get_ai_health()
    database = await _check_database()
    redis_status = await _check_redis()
    services = {
        "database": database.get("status", "down"),
        "redis": redis_status.get("status", "down"),
        "stt": ai.get("stt", {}).get("status", "down"),
        "tts": ai.get("tts", {}).get("status", "down"),
        "llm": ai.get("llm", {}).get("status", "down"),
    }
    # Redis is optional: degraded only if a REQUIRED service is down.
    required = {k: v for k, v in services.items() if k != "redis"}
    status = "ok" if all(v == "up" for v in required.values()) else "degraded"
    return {"status": status, "version": VERSION, "services": services}


@router.get("/health/ai")
async def health_ai():
    return await get_ai_health()


@router.get("/health/stt")
async def health_stt():
    return await _provider_health(get_stt, "stt")


@router.get("/health/tts")
async def health_tts():
    return await _provider_health(get_tts, "tts")


@router.get("/health/llm")
async def health_llm():
    return await _provider_health(get_llm, "llm")


@router.get("/health/database")
async def health_database():
    return await _check_database()


@router.get("/health/redis")
async def health_redis():
    return await _check_redis()
