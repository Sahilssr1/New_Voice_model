# Open-Source AI Voice Calling Platform

A complete, runnable, end-to-end **open-source AI voice calling platform**.
Talk to an AI agent from your browser: microphone → realtime voice pipeline
(VAD → STT → LLM → TTS) → speaker. No OpenAI, ElevenLabs, Google, Azure, or
AWS required — every AI provider in the core path is open-source and runs
locally.

## Architecture

```
Browser (React) ──WebSocket /ws/voice──▶ FastAPI backend
   │  mic: PCM16 16kHz base64 frames         │
   │  spk: PCM16 22.05kHz audio frames       ▼
   │                                   VoicePipeline
   │                                   ┌──────────────┐
   └──────────────────────────────────▶│ VAD (Silero/ │
                                       │  Energy)     │
                                       ├──────────────┤
                                       │ STT (faster- │
                                       │  whisper)    │
                                       ├──────────────┤
                                       │ NLP (lang    │
                                       │ detect/intent│
                                       │ /sentiment)  │
                                       ├──────────────┤
                                       │ Memory (window│
                                       │ + summary +  │
                                       │  facts)      │
                                       ├──────────────┤
                                       │ Tools (5 demo│
                                       │  built-ins)  │
                                       ├──────────────┤
                                       │ LLM (Ollama/ │
                                       │  Qwen / mock)│
                                       ├──────────────┤
                                       │ TTS (Piper / │
                                       │  NullTTS)    │
                                       └──────────────┘
                                              │
                        ┌─────────────────────┼─────────────────────┐
                        ▼                     ▼                     ▼
                   PostgreSQL            Redis (sessions,       Telephony ABC
                   (users, agents,       realtime state;        (no-op now;
                   calls, messages,      optional locally)      SIP/Asterisk
                   events, tools)                              compatible)
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design, provider
contracts, WebSocket protocol, and call-flow diagrams.

## Stack

| Layer      | Technology (open-source)                              |
|------------|-------------------------------------------------------|
| Backend    | FastAPI, Uvicorn, SQLAlchemy (async), Alembic, PyJWT  |
| STT        | faster-whisper (CPU int8, `tiny`/`base`)              |
| TTS        | Piper (`en_US-amy-medium`, `en_US-lessac-medium`, `hi_IN-priyamvada-medium`) |
| LLM        | Ollama + `qwen2.5:3b` (mock LLM for tests)          |
| VAD        | Silero (optional) / adaptive EnergyVAD                |
| Languages  | English, Hindi, Hinglish (+ auto-detect, extensible)  |
| Database   | PostgreSQL (prod) / SQLite (local dev)                |
| Realtime   | Redis (prod) / in-process fallback (local)            |
| Frontend   | React + Vite, dark SaaS UI, AudioWorklet mic capture  |
| Deploy     | Docker Compose (postgres, redis, ollama, backend, frontend) |

## Quick start (local, no Docker)

Prerequisites: Python 3.12, Node 24, FFmpeg. ~3 GB free for models.

```bash
# 1. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Models (one-time downloads)
export WHISPER_MODEL=small         # or 'base'/'tiny' (faster, weaker Hindi)
python -m piper.download_voices --download-dir ./voices \
  en_US-amy-medium en_US-lessac-medium hi_IN-priyamvada-medium

# 3. LLM — install Ollama (https://ollama.com), then:
ollama serve &
ollama pull qwen2.5:3b

# 4. Run backend (SQLite for local dev)
DATABASE_URL="sqlite+aiosqlite:///./voiceagent.db" \
JWT_SECRET="change-me-to-32-bytes-minimum" \
WHISPER_MODEL=tiny TTS_VOICES_DIR=./voices \
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 5. Frontend (new terminal)
cd ../frontend
npm install
npm run dev        # http://127.0.0.1:5173
```

Open http://127.0.0.1:5173, register, create an agent (pick language and
voice gender), then start a live call from the agent page. Allow microphone
access when prompted.

## Docker Compose

```bash
docker compose up --build
# frontend: http://localhost:3000, backend: http://localhost:8000
# first boot pulls the Ollama model (qwen2.5:3b) — takes a few minutes
```

Services: `postgres`, `redis`, `ollama`, `backend`, `frontend` (nginx).

## API overview

- `POST /api/auth/register|login` → JWT (`Authorization: Bearer`)
- `GET/POST/PATCH/DELETE /api/agents`, `/api/agents/{id}/voices`, `/api/agents/{id}/tools`
- `GET /api/calls`, `GET /api/calls/{id}` (transcript, events, latency)
- `GET /api/dashboard/stats`
- `GET /health`, `/health/ai|stt|tts|llm|database|redis`
- `WS /ws/voice` — realtime call protocol (see CONTRACT.md)

### WebSocket call flow (client → server)

`start_call {agent_id, token}` → `call_started` → greeting `audio…`/`audio_end`
→ mic `audio` frames → `state` (listening/thinking/speaking) →
`transcript` (user) → `transcript` (assistant) → `audio…`/`audio_end` →
`latency` → … → `end_call` → `call_ended`. Send `audio` while the agent is
speaking to barge in; server emits `interrupted` and yields the floor.

## Languages & voices

- Agent `language`: `en`, `hi`, or `auto` (Hinglish works via `auto`/Hindi
  voices; text language detection routes replies).
- STT gets the agent's configured language as a hint (fixes small-model
  misdetection, e.g. Hindi→Thai on `tiny`); `auto` = full auto-detect.
- Voices carry `{id, language, gender}` metadata — male/female selection is
  metadata-driven, not hard-coded. Bundled: English female/male, Hindi female.

## Tools

Five built-in demo tools, attachable per agent: `get_order_status`,
`get_customer_details`, `create_support_ticket`, `schedule_callback`,
`transfer_to_human`. The LLM can invoke them via native tool calls or a JSON
fallback block; results are spoken back to the caller. Add your own in
`backend/app/tools/builtin.py`.

## Knowledge base (RAG)

Give an agent its own knowledge: open the agent page → **Knowledge base** →
upload TXT, Markdown, or PDF files. Each turn, the backend embeds the caller's
question (local multilingual `sentence-transformers` model, ~420 MB downloaded
once) and injects the most relevant excerpts into the LLM prompt, so the agent
answers from *your* documents instead of guessing. English, Hindi (Devanagari)
and Hinglish documents all work out of the box. A **Test retrieval** box on
the same page shows exactly what the agent would see for any query.

> Switching `KB_MODEL` after documents were uploaded? Re-upload them — chunks
> embedded with a different model are never mixed into search results.

API: `POST /api/agents/{id}/kb/documents` (multipart upload),
`GET /api/agents/{id}/kb/documents`, `DELETE .../{doc_id}`,
`POST /api/agents/{id}/kb/search` (`{query, top_k}`).

| Env var            | Default              | Notes                                    |
|--------------------|----------------------|------------------------------------------|
| `KB_ENABLED`       | `true`               | set `false` to disable retrieval         |
| `KB_MODEL`         | `paraphrase-multilingual-MiniLM-L12-v2` | any sentence-transformers id; default handles EN/HI/Hinglish |
| `KB_TOP_K`         | `3`                  | excerpts injected per turn               |
| `KB_MIN_SCORE`     | `0.25`               | cosine similarity threshold              |
| `KB_CHUNK_SIZE`    | `600`                | chars per chunk                          |
| `KB_MAX_FILE_MB`   | `10`                 | upload size cap                          |

## Configuration

| Env var            | Default              | Notes                                    |
|--------------------|----------------------|------------------------------------------|
| `DATABASE_URL`     | sqlite dev file      | `postgresql+asyncpg://…` in production   |
| `JWT_SECRET`       | (required)           | ≥32 bytes                                |
| `WHISPER_MODEL`    | `small`              | `tiny`/`base` for low-RAM CPUs            |
| `TTS_VOICES_DIR`   | `./voices`           | Piper `.onnx` voices                     |
| `OLLAMA_HOST`      | `http://localhost:11434` | LLM endpoint                         |
| `OLLAMA_MODEL`     | `qwen2.5:3b`       | any Ollama model tag                     |
| `REDIS_URL`        | —                    | optional locally; required in Compose    |

## Testing

```bash
cd backend
WHISPER_MODEL=tiny .venv/bin/python -m pytest tests/ -q
# 23 passed — REST API, AI units, real-model STT/TTS/LLM, WebSocket gateway
# (barge-in, STT-failure recovery, auth, persistence)
```

End-to-end scripts (live server + real models, Piper-synthesized "callers"):
`EN+male`, `HI+female`, `Hinglish+female`, barge-in `interrupted` frame,
multi-turn memory, transcript persistence — all verified 2026-09-22.

## Limitations

- CPU-only realtime: turn latency ~10–15 s on 2 vCPUs (`small`+`qwen2.5:3b`);
  a GPU or larger CPU budget is needed for the 2–3 s target.
- `tiny`/`base` Whisper mis-transcribe Hindi; `small` is the default for
  reliable Hindi/Hinglish. `qwen2.5:1.5b` is faster but its Hindi/Hinglish
  output is poor — use `OLLAMA_MODEL=qwen2.5:1.5b` only for English-only agents.
- Telephony (SIP/Asterisk/FreeSWITCH) is architected (`TelephonyProvider`
  ABC) but only the browser channel is implemented.
- No Docker on the dev VM — Compose files are provided but were validated by
  inspection, not by running.

## Next steps

1. GPU-enabled deployment for 2–3 s turn latency.
2. SIP trunk integration via the `TelephonyProvider` interface.
3. More Piper voices/languages; per-agent voice cloning hooks.
4. Production hardening: Postgres migrations in CI, Redis Streams for events,
   rate limiting, and call recording storage.
