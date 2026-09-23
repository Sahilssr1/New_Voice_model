"""WebSocket voice gateway: ws://<host>/ws/voice.

Protocol (see CONTRACT.md):
  client -> server: start_call {agent_id, token}, audio {data, seq}, end_call, ping
  server -> client: call_started, state, transcript, audio, audio_end,
                   interrupted, latency, call_ended, error, pong

The first frame must be start_call carrying the JWT; the agent is loaded and
ownership is checked before any audio is accepted. Every pipeline event is
forwarded to the socket via pipeline.emit. The handler never leaks
tracebacks to the client.
"""

from __future__ import annotations

import base64
import binascii
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..ai.factory import get_llm, get_stt, get_tts, get_vad
from ..services import agent_service, call_service
from ..services.voice_pipeline import VoicePipeline
from ..tools import get_registry

log = logging.getLogger(__name__)

router = APIRouter()


def _decode_token(token: str) -> str:
    """Validate JWT and return the user id. Raises on failure."""
    from ..core.security import decode_token  # owned by another agent

    payload = decode_token(token)
    if isinstance(payload, dict):
        for key in ("sub", "user_id", "id"):
            if payload.get(key):
                return str(payload[key])
    raise ValueError("Invalid token payload")


def _session_factory():
    """Resolve the async session factory from app.db.database."""
    from ..db import database as dbmod  # owned by another agent

    for name in (
        "async_session",  # this project's actual factory name
        "async_session_factory",
        "AsyncSessionLocal",
        "session_factory",
        "SessionLocal",
    ):
        factory = getattr(dbmod, name, None)
        if callable(factory):
            return factory
    raise RuntimeError("No async session factory found in app.db.database")


def _resolve_llm(agent):
    """LLM for this call: per-agent model override, else the shared singleton."""
    model_override = getattr(agent, "llm_model", None) if not isinstance(agent, dict) else agent.get("llm_model")
    if model_override:
        try:
            from ..ai.llm.ollama_llm import OllamaLLM

            return OllamaLLM(model=model_override)
        except Exception as exc:
            log.warning("Per-agent OllamaLLM failed, using shared LLM: %s", exc)
    return get_llm()


@router.websocket("/ws/voice")
async def voice_gateway(websocket: WebSocket):
    await websocket.accept()
    pipeline: VoicePipeline | None = None

    async def _send_error(code: str, message: str) -> None:
        try:
            await websocket.send_json({"type": "error", "code": code, "message": message})
        except Exception:
            pass

    try:
        # -- handshake: first frame must be start_call ----------------------
        first = await websocket.receive_json()
        if not isinstance(first, dict) or first.get("type") != "start_call":
            await _send_error("protocol", "First frame must be start_call")
            await websocket.close(code=4400)
            return

        token = first.get("token") or ""
        agent_id = first.get("agent_id") or ""
        try:
            user_id = _decode_token(token)
        except Exception:
            await _send_error("auth_failed", "Invalid or expired token")
            await websocket.close(code=4401)
            return
        if not agent_id:
            await _send_error("agent_not_found", "agent_id is required")
            await websocket.close(code=4400)
            return

        try:
            session_factory = _session_factory()
        except Exception as exc:
            log.error("Session factory unavailable: %s", exc)
            await _send_error("internal", "Service temporarily unavailable")
            await websocket.close(code=4411)
            return

        try:
            async with session_factory() as db:
                agent = await agent_service.get_agent(db, agent_id, owner_id=user_id)
        except Exception as exc:
            log.error("Agent lookup failed: %s", exc)
            await _send_error("internal", "Service temporarily unavailable")
            await websocket.close(code=4411)
            return
        if agent is None:
            await _send_error("agent_not_found", "Agent not found")
            await websocket.close(code=4404)
            return

        try:
            async with session_factory() as db:
                call = await call_service.create_call(
                    db, agent_id=str(getattr(agent, "id", agent_id)), user_id=user_id
                )
                tool_names = await agent_service.get_agent_tool_names(
                    db, str(getattr(agent, "id", agent_id))
                )
        except Exception as exc:
            log.error("Call creation failed: %s", exc)
            await _send_error("internal", "Could not start call")
            await websocket.close(code=4411)
            return
        call_id = str(call.id)

        # -- pipeline --------------------------------------------------------
        async def emit(event: dict) -> None:
            try:
                await websocket.send_json(event)
            except Exception:
                pass  # socket gone; pipeline keeps running until stop()

        registry = get_registry(tool_names)
        pipeline = VoicePipeline(
            call_id=call_id,
            agent=agent,
            session_factory=session_factory,
            stt=get_stt(),
            tts=get_tts(),
            llm=_resolve_llm(agent),
            vad=get_vad(),
            tool_registry=registry,
            emit=emit,
        )

        agent_id_str = str(getattr(agent, "id", agent_id))
        await websocket.send_json(
            {
                "type": "call_started",
                "call_id": call_id,
                "agent": {
                    "id": agent_id_str,
                    "name": getattr(agent, "name", "Agent"),
                    "voice_gender": getattr(agent, "voice_gender", "female"),
                    "language": getattr(agent, "language", "auto"),
                },
            }
        )
        await pipeline.start()

        # -- frame loop ------------------------------------------------------
        while True:
            try:
                message = await websocket.receive_json()
            except WebSocketDisconnect:
                raise
            if not isinstance(message, dict):
                continue
            mtype = message.get("type")

            if mtype == "audio":
                data = message.get("data") or ""
                try:
                    pcm = base64.b64decode(data, validate=True)
                except (binascii.Error, ValueError):
                    await _send_error("bad_audio", "Invalid base64 audio frame")
                    continue
                # Decode errors inside the pipeline are swallowed safely.
                await pipeline.on_audio(pcm)
            elif mtype == "end_call":
                await pipeline.stop("user_hangup")
                break
            elif mtype == "ping":
                try:
                    await websocket.send_json({"type": "pong"})
                except Exception:
                    break
            else:
                await _send_error("protocol", f"Unknown frame type: {mtype}")

    except WebSocketDisconnect:
        log.info("WebSocket disconnected")
    except Exception as exc:
        # Never leak tracebacks to the client.
        log.exception("Voice gateway error: %s", exc)
        await _send_error("internal", "Internal error")
    finally:
        if pipeline is not None:
            try:
                await pipeline.stop("disconnect")
            except Exception as exc:
                log.warning("pipeline.stop failed: %s", exc)
        try:
            await websocket.close()
        except Exception:
            pass
