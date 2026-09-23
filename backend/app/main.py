"""VoiceAgent Platform backend — FastAPI application entrypoint."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.database import init_db

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Dev convenience: ensure tables exist (docker/postgres relies on alembic,
    # but create_all is a harmless fallback thanks to checkfirst).
    await init_db()
    try:
        from app.api.tools_api import seed_builtin_tools

        await seed_builtin_tools()
    except Exception:
        logger.warning("builtin tool seeding skipped", exc_info=True)
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST routers (owned by backend-core agent)
from app.api import auth, agents, calls, dashboard, knowledge, tools_api  # noqa: E402

app.include_router(auth.router)
app.include_router(agents.router)
app.include_router(calls.router)
app.include_router(dashboard.router)
app.include_router(knowledge.router)
app.include_router(tools_api.router)

# Health router is owned by the AI-pipeline agent; mount when it lands.
try:
    from app.api import health as health_api  # noqa: E402

    app.include_router(health_api.router)
    logger.info("health router mounted")
except ImportError:
    logger.warning("app.api.health not available yet; skipping")

# WebSocket voice gateway is owned by the realtime agent; mount when it lands.
try:
    from app.websocket.voice_gateway import router as voice_router  # noqa: E402

    app.include_router(voice_router)
    logger.info("voice gateway router mounted at /ws/voice")
except ImportError:
    logger.warning("websocket voice gateway not available yet; skipping")


@app.get("/", tags=["root"])
async def root():
    return {"name": settings.APP_NAME, "version": settings.APP_VERSION, "docs": "/docs"}
