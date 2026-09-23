# ARCHITECTURE.md

## 1. System overview

A realtime, browser-first AI voice calling platform. A user speaks into the
browser; audio streams over a WebSocket to a Python voice pipeline
(VAD → STT → NLP → memory → tools → LLM → TTS); synthesized speech streams
back for in-browser playback. All AI runs on open-source models locally —
no proprietary AI APIs in the core path.

```
┌─────────────────────────────┐         WebSocket /ws/voice          ┌──────────────────────────┐
│  Browser (React + Vite)     │ ◀──────────────────────────────────▶ │  FastAPI backend         │
│  - AudioWorklet mic capture │   PCM16 16kHz up / PCM16 22.05kHz     │  - /ws/voice gateway     │
│    (16 kHz resample, b64)   │   down, JSON frames                   │  - VoicePipeline         │
│  - PCM playback queue       │                                       │  - REST: auth, agents,   │
│  - VoiceOrb + call states   │   REST /api/*                         │    calls, tools, dash    │
│  - transcript + latency UI  │ ◀──────────────────────────────────▶ │  - health endpoints      │
└─────────────────────────────┘                                       └──────────┬───────────────┘
                                                                                 │
                                              ┌──────────────────┬───────────────┼───────────────┬──────────────────┐
                                              ▼                  ▼               ▼               ▼                  ▼
                                        faster-whisper      Piper TTS      Ollama/Qwen      Silero/Energy     ToolRegistry
                                        (STT, CPU int8)    (chunked)      (LLM + tools)    (VAD)             (5 built-ins)
                                              │                  │               │               │                  │
                                              └──────────────────┴───────────────┴───────────────┴──────────────────┘
                                                                                 │
                                                        ┌────────────────────────┼────────────────────────┐
                                                        ▼                        ▼                        ▼
                                                   PostgreSQL                 Redis                  TelephonyProvider
                                                   (prod RDBMS)          (sessions/realtime)          (ABC; no-op impl)
                                                   SQLite (local dev)    (optional locally)
```

## 2. Realtime call flow (single turn)

1. Client sends `start_call {agent_id, token}`. Gateway authenticates,
   verifies agent ownership, creates the `Call` row, and builds the
   `VoicePipeline` with provider singletons from `app.ai.factory`.
2. Pipeline plays the agent greeting via TTS (`state=speaking`), then goes
   `listening`.
3. Mic `audio` frames (20 ms PCM16 @16 kHz) feed the VAD. ≥3 speech frames
   open a segment; ≥30 silence frames (~600 ms) close it.
4. Segment → **STT** (`faster-whisper`, agent language passed as hint) →
   `transcript{role=user}` + language.
5. **NLP**: text language detection (en/hi/hinglish), intent/entities/
   sentiment extraction, response validation.
6. **Memory**: recent-window messages + rolling summary + extracted facts are
   injected into the LLM context.
7. **LLM** (`OllamaLLM` → Qwen, or `MockLLM`): generates the reply; may emit
   native tool calls or a JSON fallback block parsed by `ToolRegistry`.
   Tool results are fed back for a final answer.
8. Reply → `transcript{role=assistant}` → **TTS** (`PiperTTS`, chunked
   ~0.5 s PCM frames @22.05 kHz) → `audio…`/`audio_end`, `state=speaking`.
9. `latency{stt_ms, llm_ms, tts_ms, total_ms}` is emitted per turn.
10. `end_call` (or watchdog: silence timeout / max duration) → pipeline
    stops, persists summary + call status, emits `call_ended`.

**Barge-in:** while `state=speaking`, ≥3 consecutive VAD speech frames cancel
the TTS task; `_on_barge_in()` emits `interrupted`, discards pre-interruption
audio, and the user's speech becomes a fresh segment.

**Failure handling:** STT/LLM/TTS exceptions are caught per stage — the
caller hears a spoken reprompt/apology and the call continues. Provider
singletons degrade (`NullTTS`, `MockLLM`) so a missing model never kills the
gateway. `/health/*` reports per-service status.

## 3. Provider abstractions

All in `backend/app/ai/*`, constructed via `app/ai/factory.py`:

| ABC | Implementations | Notes |
|---|---|---|
| `SpeechToTextProvider` | `FasterWhisperSTT` | lazy load; `WHISPER_MODEL` (`tiny`/`base`); int8 CPU |
| `TextToSpeechProvider` | `PiperTTS`, `NullTTS` | chunked async gen; `speed`→`length_scale`; catalog with `{id, language, gender}` |
| `LLMProvider.generate()` | `OllamaLLM`, `MockLLM` | `LLMResult(text, tool_calls, latency_ms)`; `trust_env=False` httpx |
| `VADProvider` | `SileroVAD`, `EnergyVAD` | 20 ms frames; adaptive energy fallback |
| `TelephonyProvider` | `NoOpTelephony` | ABC ready for SIP/Asterisk/FreeSWITCH |
| `ToolRegistry` | 5 built-in tools | `parse_tool_call` (JSON fallback) + `execute` |

Language support: `app/ai/nlp/language.py` detects en/hi/hinglish from text;
agent `language` ∈ {en, hi, auto}. Voices are metadata-driven.

## 4. Data model (PostgreSQL / SQLite)

`users` → `agents` → `agent_voices` (metadata incl. gender/language),
`agent_tools` (M2M to `tools`); `calls` → `conversation_messages`,
`call_events` (state/latency/tool/error audit trail). Summaries/facts live
on the call/session row. Alembic migration `0001_initial.py`.

## 5. Frontend

React + Vite (`frontend/`): `/login`, `/dashboard`, `/agents`, `/agents/new`,
`/agents/:id`, `/calls`, `/calls/live/:agentId`, `/calls/:id`, `/settings`.
`useVoiceCall` hook: AudioWorklet mic → 16 kHz PCM16 → WebSocket; PCM
playback queue; cancels playback on `interrupted`; shows
Listening/Thinking/Speaking, transcripts, and per-turn latency. JWT in
`localStorage` (`va_token`).

## 6. Deployment

`docker-compose.yml`: `postgres`, `redis`, `ollama` (pulls `qwen2.5:1.5b`),
`backend` (uvicorn), `frontend` (nginx). Local dev: SQLite + optional Redis,
`npm run dev` + uvicorn directly (see README).

## 7. Verified behavior (2026-09-22, CPU-only VM)

- `pytest tests/`: **23 passed** — REST/auth, AI units, real faster-whisper
  tiny STT, real Piper EN/HI TTS, real Ollama generation, WebSocket gateway
  (auth, full call, STT-failure recovery).
- Live E2E with real models (Piper-synthesized callers over `/ws/voice`):
  EN+male voice turn (13.5 s), HI+female 2-turn call with language hint
  (STT `[hi]` correct), Hinglish 2-turn call (4 messages persisted),
  barge-in → `interrupted` frame, graceful `end_call` → `call_ended`,
  transcript persistence + dashboard stats.
- Known limits: turn latency 7–13 s on 2 vCPUs; `tiny` needs the STT language
  hint for Hindi; telephony channel not yet implemented.
