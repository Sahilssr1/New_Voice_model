"""Realtime voice pipeline (the core of the voice agent).

Pipeline per user turn:
    mic PCM -> VAD -> speech segment -> STT -> language detect ->
    NLP (intent/entities/sentiment) -> memory -> LLM (+tool loop) ->
    response validation -> TTS (streamed) -> audio frames

The pipeline is audio-source agnostic: it consumes raw int16 mono PCM bytes
via on_audio(), so the same class serves the WebSocket gateway and (later) a
telephony provider.

States: listening | thinking | speaking | ended
Events are pushed to the caller through the async ``emit`` callable.
All provider calls are wrapped in try/except: the pipeline degrades
gracefully and never crashes the call on STT/LLM/TTS/DB failures.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
from datetime import datetime, timezone

import numpy as np

from ..ai.nlp.language import detect_text_language
from ..ai.nlp.memory import ConversationMemory
from ..ai.nlp.pipeline import NLPPipeline
from . import agent_service, call_service, conversation_service

log = logging.getLogger(__name__)

_FRAME_SAMPLES = 320  # 20 ms @ 16 kHz
_SPEECH_START_FRAMES = 3  # ~60 ms of speech to open a segment
# Silence that soft-closes a segment. Natural pauses inside a sentence run
# 300-800 ms; 600 ms was splitting sentences at the first pause ("hi" |
# "how are you?"). 900 ms keeps a sentence together without feeling laggy.
_SPEECH_END_SILENCE_FRAMES = max(
    30, int(float(os.environ.get("VAD_END_SILENCE_MS", "900")) / 20)
)
# Extra grace after a soft close: if speech resumes within this window the
# audio is merged into the same utterance instead of starting a new turn.
# Handles deliberate mid-sentence pauses (e.g. "Hi," <pause> "how are you?").
_MERGE_SILENCE_FRAMES = max(
    15, int(float(os.environ.get("VAD_MERGE_SILENCE_MS", "600")) / 20)
)
_HARD_CLOSE_SILENCE_FRAMES = _SPEECH_END_SILENCE_FRAMES + _MERGE_SILENCE_FRAMES
_BARGE_IN_FRAMES = 3  # ~60 ms of speech while speaking -> barge-in
_MIN_UTTERANCE_SAMPLES = int(0.3 * 16000)
_MAX_BUFFER_SAMPLES = 30 * 16000
_LOW_CONFIDENCE = 0.15

_NUDGE_TEXT = "Are you still there?"
_REPROMPT_TEXT = "Sorry, I didn't catch that. Could you please repeat?"
_LLM_FALLBACK_TEXT = (
    "I'm sorry, I'm having trouble thinking right now. Could you try again?"
)


class MemoryCache:
    """Tiny async in-memory cache (used when Redis is unavailable)."""

    def __init__(self) -> None:
        self._store: dict = {}

    async def get(self, key: str):
        return self._store.get(key)

    async def set(self, key: str, value, ttl: int | None = None) -> None:
        self._store[key] = value

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


class VoicePipeline:
    """Realtime voice conversation pipeline for one call."""

    def __init__(
        self,
        call_id: str,
        agent,
        session_factory,
        stt,
        tts,
        llm,
        vad,
        tool_registry,
        emit,
        cache=None,
    ) -> None:
        self._call_id = call_id
        self._agent = agent
        self._session_factory = session_factory
        self._stt = stt
        self._tts = tts
        self._llm = llm
        self._vad = vad
        self._tools = tool_registry
        self._emit_raw = emit
        self._cache = cache or MemoryCache()

        self._memory = ConversationMemory()
        self._nlp = NLPPipeline()

        self._state = "idle"
        self._stopped = False
        self._started = False
        self._turn = 0
        self._reprompted = False
        self._nudged = False
        self._session_id: str | None = None

        # Audio segmentation state
        self._utterance_chunks: list[np.ndarray] = []
        self._utterance_samples = 0
        self._vad_remainder = np.zeros(0, dtype=np.float32)
        self._in_speech = False
        self._soft_closed = False  # end-silence reached, merge window open
        self._mid_turn_speech = False  # user spoke while state != listening
        self._speech_frames = 0
        self._silence_frames = 0
        self._barge_frames = 0

        # Tasks / timing
        self._utterance_task: asyncio.Task | None = None
        self._speak_task: asyncio.Task | None = None
        self._greet_task: asyncio.Task | None = None
        self._watchdog_task: asyncio.Task | None = None
        self._started_at = 0.0
        self._last_voice_activity = 0.0

    # -- helpers -----------------------------------------------------------
    def _ag(self, name: str, default=None):
        if isinstance(self._agent, dict):
            return self._agent.get(name, default)
        return getattr(self._agent, name, default)

    @staticmethod
    def _now() -> float:
        return time.monotonic()

    async def _emit(self, event: dict) -> None:
        try:
            await self._emit_raw(event)
        except Exception as exc:
            log.warning("emit failed: %s", exc)

    def _set_state(self, state: str) -> None:
        self._state = state
        # Fire-and-forget: state events must never block the audio path.
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._emit({"type": "state", "state": state}))
            loop.create_task(self._cache.set(f"call:{self._call_id}:state", state))
        except RuntimeError:
            pass

    async def _log(self, event_type: str, payload: dict | None = None) -> None:
        try:
            async with self._session_factory() as db:
                await call_service.log_event(
                    db, self._call_id, event_type, payload or {}
                )
        except Exception as exc:
            log.warning("log_event(%s) failed: %s", event_type, exc)

    # -- lifecycle ---------------------------------------------------------
    async def start(self) -> None:
        """Start the call: log call_started, play greeting, arm watchdogs."""
        if self._started:
            return
        self._started = True
        self._started_at = self._now()
        self._last_voice_activity = self._started_at

        try:
            async with self._session_factory() as db:
                session = await call_service.get_or_create_session(db, self._call_id)
                self._session_id = getattr(session, "id", None) if session else None
        except Exception as exc:
            log.warning("Could not load conversation session: %s", exc)

        await self._log(
            "call_started",
            {"agent_id": str(self._ag("id", "")), "channel": "browser"},
        )
        self._watchdog_task = asyncio.create_task(
            self._watchdog(), name=f"watchdog-{self._call_id}"
        )

        greeting = (self._ag("greeting") or "").strip()
        if greeting:
            self._greet_task = asyncio.create_task(
                self._play_greeting(greeting), name=f"greet-{self._call_id}"
            )
        else:
            self._set_state("listening")

    async def _play_greeting(self, greeting: str) -> None:
        try:
            await self._speak(greeting, turn=0)
        except asyncio.CancelledError:
            pass  # barge-in handled inside _speak
        except Exception as exc:
            log.warning("Greeting failed: %s", exc)
        if not self._stopped:
            self._set_state("listening")
            self._reset_silence()

    def _dominant_language(self) -> str | None:
        """Most common language across user messages (for call.language)."""
        counts: dict[str, int] = {}
        for m in self._memory.messages:
            if m.get("role") == "user" and m.get("language"):
                lang = m["language"]
                counts[lang] = counts.get(lang, 0) + 1
        if not counts:
            return None
        return max(counts, key=counts.get)

    async def stop(self, reason: str = "user_hangup") -> None:
        """End the call cleanly: cancel tasks, persist summary, emit call_ended."""
        if self._stopped:
            return
        self._stopped = True
        self._state = "ended"

        current = asyncio.current_task()
        for task in (
            self._watchdog_task,
            self._greet_task,
            self._utterance_task,
            self._speak_task,
        ):
            if task is not None and task is not current and not task.done():
                task.cancel()

        summary = await self._build_summary()
        status = (
            "completed"
            if reason in ("user_hangup", "disconnect", "max_duration", "silence")
            else "failed"
        )
        duration_sec = 0
        message_count = len(self._memory.messages)
        # Extract durable facts on the way out (best effort).
        try:
            if self._memory.messages:
                await self._memory.extract_facts(self._llm)
        except Exception as exc:
            log.warning("Fact extraction on stop failed: %s", exc)
        try:
            async with self._session_factory() as db:
                call = await call_service.end_call(
                    db,
                    self._call_id,
                    status=status,
                    summary=summary,
                    facts=self._memory.facts or None,
                    language=self._dominant_language(),
                )
                if call is not None:
                    duration_sec = int(getattr(call, "duration_sec", 0) or 0)
                    message_count = int(
                        getattr(call, "message_count", 0) or message_count
                    )
                if self._session_id:
                    await call_service.update_session_summary(
                        db, self._session_id, self._memory.summary, self._memory.facts
                    )
        except Exception as exc:
            log.warning("end_call persistence failed: %s", exc)
        if not duration_sec:
            duration_sec = int(self._now() - self._started_at)

        await self._log("call_ended", {"reason": reason, "status": status})
        await self._emit(
            {
                "type": "call_ended",
                "call_id": self._call_id,
                "duration_sec": duration_sec,
                "message_count": message_count,
            }
        )

    async def _build_summary(self) -> str:
        try:
            if len(self._memory.messages) >= 4:
                summary = await self._memory.summarize(self._llm)
                if summary:
                    return summary
        except Exception as exc:
            log.warning("Call summary failed: %s", exc)
        # Fallback: first user utterance + last assistant reply.
        first_user = next(
            (m["text"] for m in self._memory.messages if m["role"] == "user"), ""
        )
        last_ai = next(
            (m["text"] for m in reversed(self._memory.messages) if m["role"] == "assistant"),
            "",
        )
        bits = []
        if first_user:
            bits.append(f"User asked: {first_user[:200]}")
        if last_ai:
            bits.append(f"Assistant replied: {last_ai[:200]}")
        return " ".join(bits) or "No conversation."

    # -- inbound audio -----------------------------------------------------
    async def on_audio(self, pcm_bytes: bytes) -> None:
        """Handle one chunk of int16 LE mono 16 kHz mic audio."""
        if self._stopped or self._state in ("idle", "ended"):
            return
        if not pcm_bytes:
            return
        try:
            samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
            samples /= 32768.0
        except Exception:
            return
        if samples.size == 0:
            return

        self._append_utterance(samples)
        self._vad_remainder = np.concatenate([self._vad_remainder, samples])
        while self._vad_remainder.size >= _FRAME_SAMPLES:
            frame = self._vad_remainder[:_FRAME_SAMPLES]
            self._vad_remainder = self._vad_remainder[_FRAME_SAMPLES:]
            await self._handle_frame(frame)

    def _append_utterance(self, samples: np.ndarray) -> None:
        self._utterance_chunks.append(samples)
        self._utterance_samples += samples.size
        # Bound memory: drop oldest chunks beyond ~30 s.
        while self._utterance_samples > _MAX_BUFFER_SAMPLES and self._utterance_chunks:
            dropped = self._utterance_chunks.pop(0)
            self._utterance_samples -= dropped.size

    def _take_utterance(self) -> np.ndarray | None:
        if not self._utterance_chunks:
            return None
        audio = np.concatenate(self._utterance_chunks)
        self._reset_utterance_buffer()
        return audio

    def _reset_utterance_buffer(self) -> None:
        self._utterance_chunks = []
        self._utterance_samples = 0
        self._in_speech = False
        self._soft_closed = False
        self._mid_turn_speech = False
        self._speech_frames = 0

    def _trim_buffer_to_last_speech(self) -> None:
        """Trim the utterance buffer to the most recent speech onset.

        While the pipeline was busy (thinking/speaking), raw audio kept
        accumulating. The buffer may hold tens of seconds of silence around
        a short user utterance. Scan it with the VAD, keep from ~200 ms
        before the last speech region, and mark the segmenter as in-speech
        so new frames continue (rather than restart) the utterance.
        """
        if not self._utterance_chunks:
            return
        audio = np.concatenate(self._utterance_chunks).astype(np.float32)
        # VAD expects float32 in [-1, 1]; buffer is int16 PCM.
        if audio.size and np.abs(audio).max() > 1.0:
            audio = audio / 32768.0
        frame_len = _FRAME_SAMPLES
        # Collect speech regions, merging onsets <1s apart into one region,
        # so a pause inside an utterance doesn't split it.
        regions: list[list[int]] = []
        in_region = False
        for i in range(0, audio.size - frame_len + 1, frame_len):
            try:
                is_speech, _ = self._vad.is_speech(audio[i:i + frame_len])
            except Exception:
                is_speech = False
            if is_speech:
                if not in_region:
                    if regions and i - regions[-1][1] < 16000:
                        pass  # continues the previous region
                    else:
                        regions.append([i, i])
                    in_region = True
                if regions:
                    regions[-1][1] = i
            else:
                in_region = False
        if not regions:
            self._reset_utterance_buffer()
            return
        # Keep from 200 ms before the last region's start; drop stale audio.
        # Buffer chunks are float32 in [-1, 1] (see _on_audio).
        start = max(0, regions[-1][0] - int(0.2 * 16000))
        trimmed = audio[start:].astype(np.float32)
        self._utterance_chunks = [trimmed]
        self._utterance_samples = trimmed.size
        self._in_speech = True
        self._soft_closed = False
        self._speech_frames = _SPEECH_START_FRAMES
        self._silence_frames = 0
        self._silence_frames = 0
        self._barge_frames = 0
        # VADs with internal state (e.g. Silero's LSTM) must not leak
        # acoustic context across utterance boundaries.
        reset = getattr(self._vad, "reset", None)
        if callable(reset):
            try:
                reset()
            except Exception as exc:
                log.warning("VAD reset failed: %s", exc)
        # VADs with internal state (e.g. Silero's LSTM) must not leak
        # acoustic context across utterance boundaries.
        reset = getattr(self._vad, "reset", None)
        if callable(reset):
            try:
                reset()
            except Exception as exc:
                log.warning("VAD reset failed: %s", exc)

    def _reset_silence(self) -> None:
        self._last_voice_activity = self._now()

    async def _handle_frame(self, frame: np.ndarray) -> None:
        try:
            speech, _prob = self._vad.is_speech(frame)
        except Exception as exc:
            log.warning("VAD failed: %s", exc)
            speech = False

        # Barge-in: user speaks while the agent is speaking.
        if self._state == "speaking":
            if speech:
                self._barge_frames += 1
                if self._barge_frames >= _BARGE_IN_FRAMES:
                    self._barge_frames = 0
                    task = self._speak_task
                    self._speak_task = None
                    if task is not None and not task.done():
                        task.cancel()
                    # _speak's CancelledError handler runs _on_barge_in().
            else:
                self._barge_frames = 0
            return

        if self._state != "listening":
            # Thinking: note speech so the turn-end logic can continue the
            # user's utterance instead of silently dropping it.
            if speech:
                self._mid_turn_speech = True
            return

        if speech:
            self._last_voice_activity = self._now()
            self._speech_frames += 1
            self._silence_frames = 0
            if self._soft_closed:
                # Speech resumed inside the merge window: same utterance,
                # no new speech_started event.
                self._soft_closed = False
            if not self._in_speech and self._speech_frames >= _SPEECH_START_FRAMES:
                self._in_speech = True
                await self._log("speech_started", {})
        else:
            self._silence_frames += 1
            self._speech_frames = 0
            if not self._in_speech:
                pass
            elif not self._soft_closed and self._silence_frames >= _SPEECH_END_SILENCE_FRAMES:
                # Soft close: end-silence reached, but keep buffering in
                # case the user resumes within the merge window (mid-
                # sentence pauses). Nothing is dispatched yet.
                self._soft_closed = True
            elif self._soft_closed and self._silence_frames >= _HARD_CLOSE_SILENCE_FRAMES:
                # Hard close: the pause outlasted the merge window, the
                # utterance is really over.
                self._in_speech = False
                self._soft_closed = False
                audio = self._take_utterance()
                if audio is not None and audio.size >= _MIN_UTTERANCE_SAMPLES:
                    await self._log(
                        "speech_ended",
                        {"duration_ms": int(audio.size / 16)},
                    )
                    if self._utterance_task is None or self._utterance_task.done():
                        self._utterance_task = asyncio.create_task(
                            self._process_utterance(audio),
                            name=f"utterance-{self._call_id}-{self._turn + 1}",
                        )
                    else:
                        log.warning(
                            "Dropped utterance: previous turn still processing"
                        )

    async def _on_barge_in(self) -> None:
        """User interrupted the agent: stop TTS and switch to listening."""
        await self._log("agent_interrupted", {"turn": self._turn})
        await self._emit({"type": "interrupted"})
        # Discard pre-interruption audio; treat the ongoing speech as a new
        # segment so the user's utterance is captured from here.
        self._reset_utterance_buffer()
        self._in_speech = True
        self._speech_frames = _SPEECH_START_FRAMES
        self._silence_frames = 0
        self._last_voice_activity = self._now()
        await self._log("speech_started", {"barge_in": True})
        self._set_state("listening")

    # -- utterance processing ----------------------------------------------
    def _resolve_language(self, text: str, stt_language: str | None) -> str:
        configured = (self._ag("language") or "auto").strip().lower()
        if configured != "auto":
            return configured
        detected = detect_text_language(text)
        if detected == "en" and stt_language and stt_language not in ("en",):
            return stt_language
        return detected

    async def _process_utterance(self, audio: np.ndarray) -> None:
        self._turn += 1
        turn = self._turn
        try:
            await self._run_turn(audio, turn)
        except asyncio.CancelledError:
            # Barge-in during TTS: _speak already ran _on_barge_in(); a
            # stop() during processing just ends the task quietly.
            if self._stopped:
                raise
            return
        except Exception as exc:
            log.exception("Utterance processing failed: %s", exc)
            await self._log("error", {"stage": "utterance", "error": str(exc), "turn": turn})
            await self._emit(
                {"type": "error", "code": "utterance_failed", "message": "Processing failed"}
            )
            if not self._stopped:
                self._reset_utterance_buffer()
                self._set_state("listening")
                self._reset_silence()

    async def _run_turn(self, audio: np.ndarray, turn: int) -> None:
        self._set_state("thinking")
        self._mid_turn_speech = False
        t_start = self._now()

        # -- STT ------------------------------------------------------------
        await self._log("stt_started", {"turn": turn})
        try:
            # Pass the agent's configured language as a hint so Whisper does
            # not misdetect (e.g. Hindi as Thai on small models). "auto"
            # means no hint -> full auto-detection.
            configured = (self._ag("language") or "auto").strip().lower()
            stt_hint = None if configured == "auto" else configured
            stt_result = await self._stt.transcribe(audio, 16000, language=stt_hint)
            stt_ms = int((self._now() - t_start) * 1000)
            await self._log(
                "stt_completed",
                {
                    "turn": turn,
                    "text": (stt_result.text or "")[:200],
                    "language": stt_result.language,
                    "latency_ms": stt_ms,
                },
            )
        except Exception as exc:
            await self._log("error", {"stage": "stt", "error": str(exc), "turn": turn})
            await self._emit(
                {"type": "error", "code": "stt_failed", "message": "Speech recognition failed"}
            )
            # Recover: apologize via TTS, then keep listening.
            await self._speak(_REPROMPT_TEXT, turn=turn)
            self._set_state("listening")
            self._reset_silence()
            return

        text = (stt_result.text or "").strip()
        if not text or stt_result.confidence < _LOW_CONFIDENCE:
            if not self._reprompted:
                self._reprompted = True
                await self._speak(_REPROMPT_TEXT, turn=turn)
            self._set_state("listening")
            self._reset_silence()
            return
        self._reprompted = False

        language = self._resolve_language(text, stt_result.language)
        await self._emit(
            {"type": "transcript", "role": "user", "text": text, "language": language, "turn": turn}
        )

        # -- NLP: intent / entities / sentiment ------------------------------
        nlp = {"intent": "general", "entities": {}, "sentiment": "neutral"}
        try:
            nlp = await self._nlp.process_turn(text, language, self._llm)
        except Exception as exc:
            log.warning("NLP step failed: %s", exc)
        self._memory.add_message(
            "user", text, language=language,
            intent=nlp.get("intent"), entities=nlp.get("entities"),
        )
        await self._save_message("user", text, language, nlp, None)

        # -- KB retrieval ---------------------------------------------------
        kb_context = None
        try:
            from . import knowledge_service

            kb_context = await knowledge_service.retrieve_context(
                self._session_factory, str(self._ag("id", "")), text
            )
            if kb_context:
                await self._log(
                    "kb_retrieved",
                    {"turn": turn, "chars": len(kb_context)},
                )
        except Exception as exc:
            log.warning("KB retrieval failed: %s", exc)

        # -- LLM (+ tools) ----------------------------------------------------
        await self._log("llm_started", {"turn": turn})
        llm_ms = 0
        try:
            messages = conversation_service.build_llm_messages(
                self._agent, self._memory, kb_context=kb_context
            )
            temperature = self._ag("temperature", 0.7) or 0.7
            reply, llm_ms, tool_events = await conversation_service.run_tool_loop(
                self._llm, messages, self._tools, temperature=float(temperature)
            )
            for ev in tool_events:
                await self._log("tool_called", {"turn": turn, **ev})
            await self._log("llm_completed", {"turn": turn, "latency_ms": llm_ms})
        except Exception as exc:
            await self._log("error", {"stage": "llm", "error": str(exc), "turn": turn})
            await self._emit(
                {"type": "error", "code": "llm_failed", "message": "Response generation failed"}
            )
            reply = _LLM_FALLBACK_TEXT

        reply = self._nlp.validate_response(reply)
        self._memory.add_message("assistant", reply, language=language, latency_ms=llm_ms)
        await self._save_message("assistant", reply, language, None, llm_ms)

        # Summarize + extract facts when history grows long (best effort).
        if self._memory.needs_summary():
            try:
                await self._memory.summarize(self._llm)
                await self._memory.extract_facts(self._llm)
                if self._session_id:
                    async with self._session_factory() as db:
                        await call_service.update_session_summary(
                            db, self._session_id, self._memory.summary, self._memory.facts
                        )
            except Exception as exc:
                log.warning("Memory maintenance failed: %s", exc)

        await self._emit(
            {
                "type": "transcript",
                "role": "assistant",
                "text": reply,
                "language": language,
                "turn": turn,
            }
        )

        # -- TTS (streamed) ----------------------------------------------------
        t_tts = self._now()
        await self._log("tts_started", {"turn": turn})
        try:
            await self._speak(reply, turn=turn)
            tts_ms = int((self._now() - t_tts) * 1000)
            await self._log("tts_completed", {"turn": turn, "latency_ms": tts_ms})
        except asyncio.CancelledError:
            raise  # barge-in: handled in _speak
        except Exception as exc:
            await self._log("error", {"stage": "tts", "error": str(exc), "turn": turn})
            await self._emit(
                {"type": "error", "code": "tts_failed", "message": "Speech synthesis failed"}
            )
            tts_ms = 0

        total_ms = int((self._now() - t_start) * 1000)
        await self._emit(
            {
                "type": "latency",
                "stt_ms": stt_ms,
                "llm_ms": llm_ms,
                "tts_ms": tts_ms,
                "total_ms": total_ms,
                "turn": turn,
            }
        )
        if not self._stopped:
            # If the user kept speaking during this turn, keep their audio
            # and let segmentation finish it as the next turn instead of
            # dropping their words. Trim the buffer to the most recent
            # speech onset so we don't send minutes of stale silence to STT.
            user_speaking = (
                self._utterance_samples >= _MIN_UTTERANCE_SAMPLES
                and (self._in_speech or self._soft_closed or self._mid_turn_speech)
            )
            if not user_speaking:
                self._reset_utterance_buffer()  # drop audio captured mid-turn
            else:
                self._trim_buffer_to_last_speech()
            self._set_state("listening")
            self._reset_silence()

    async def _save_message(self, role, text, language, nlp, latency_ms) -> None:
        try:
            async with self._session_factory() as db:
                await call_service.add_message(
                    db,
                    call_id=self._call_id,
                    session_id=self._session_id,
                    role=role,
                    text=text,
                    language=language,
                    intent=(nlp or {}).get("intent"),
                    entities=(nlp or {}).get("entities"),
                    latency_ms=latency_ms,
                )
        except Exception as exc:
            log.warning("Persisting message failed: %s", exc)

    # -- speech output -------------------------------------------------------
    async def _speak(self, text: str, turn: int) -> None:
        """Stream TTS audio frames for text. Cancellable (barge-in / stop)."""
        self._speak_task = asyncio.current_task()
        self._set_state("speaking")
        gen = None
        try:
            voice_id = self._ag("voice_id") or "en_US-amy-medium"
            language = (self._ag("language") or "auto").strip().lower()
            gen = self._tts.synthesize(
                text, voice_id=voice_id,
                language=None if language == "auto" else language,
                speed=1.0,
            )
            chunk = 0
            async for pcm, sample_rate in gen:
                if self._stopped:
                    break
                await self._emit(
                    {
                        "type": "audio",
                        "data": base64.b64encode(pcm).decode("ascii"),
                        "sample_rate": sample_rate,
                        "chunk": chunk,
                        "turn": turn,
                    }
                )
                chunk += 1
            await self._emit({"type": "audio_end", "turn": turn})
        except asyncio.CancelledError:
            if gen is not None:
                aclose = getattr(gen, "aclose", None)
                if aclose is not None:
                    try:
                        await aclose()
                    except Exception:
                        pass
            if not self._stopped:
                await self._on_barge_in()
            raise
        except Exception as exc:
            # TTS failed: still surface the text so the conversation continues.
            log.warning("TTS synthesize failed: %s", exc)
            await self._emit({"type": "audio_end", "turn": turn})
            raise
        finally:
            if self._speak_task is asyncio.current_task():
                self._speak_task = None

    # -- watchdogs -----------------------------------------------------------
    def _silence_timeout(self) -> float:
        try:
            return float(self._ag("silence_timeout_sec", 12) or 12)
        except (TypeError, ValueError):
            return 12.0

    def _max_duration(self) -> float:
        try:
            return float(self._ag("max_duration_sec", 600) or 600)
        except (TypeError, ValueError):
            return 600.0

    async def _watchdog(self) -> None:
        """Silence nudge + max-duration enforcement."""
        try:
            while not self._stopped:
                await asyncio.sleep(0.5)
                now = self._now()
                if (now - self._started_at) >= self._max_duration():
                    await self.stop("max_duration")
                    return
                if self._state == "listening":
                    if (now - self._last_voice_activity) >= self._silence_timeout():
                        if not self._nudged:
                            self._nudged = True
                            self._reset_silence()
                            try:
                                await self._speak(_NUDGE_TEXT, turn=self._turn)
                            except asyncio.CancelledError:
                                pass  # barge-in during nudge
                            except Exception as exc:
                                log.warning("Nudge failed: %s", exc)
                            if not self._stopped and self._state == "speaking":
                                self._set_state("listening")
                        else:
                            await self.stop("silence")
                            return
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            log.warning("Watchdog failed: %s", exc)

    # -- introspection ---------------------------------------------------------
    @property
    def state(self) -> str:
        return self._state

    @property
    def turn(self) -> int:
        return self._turn
