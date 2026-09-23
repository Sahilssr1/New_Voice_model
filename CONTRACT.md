# API & WebSocket Contract — voiceagent-platform (frozen)

All builders MUST follow this contract exactly so backend, AI pipeline, and frontend fit together.
Project root: `~/workspace/voiceagent/`

## Global conventions
- Backend base URL (dev): `http://localhost:8000`. Frontend dev server: `http://localhost:5173`.
- REST base path: `/api`. Auth: `Authorization: Bearer <JWT>` on all `/api/*` except `/api/auth/register`, `/api/auth/login`, and `/health*`.
- IDs are UUID strings. Timestamps are ISO-8601 UTC.
- Audio on the wire: mono 16-bit PCM little-endian. Mic capture at 16000 Hz. TTS output at 22050 Hz.
- Language codes: `en`, `hi`, `hinglish` (romanized Hindi), plus `auto` (agent config only = detect per turn).

## Env vars (backend reads via pydantic-settings, `.env` supported)
```
DATABASE_URL=sqlite+aiosqlite:///./voiceagent.db   # dev default; docker: postgresql+asyncpg://voice:voice@postgres:5432/voiceagent
REDIS_URL=redis://localhost:6379/0                 # optional; app must work without it (in-memory fallback)
JWT_SECRET=change-me
JWT_EXPIRE_MINUTES=10080
OLLAMA_BASE_URL=http://localhost:11434
DEFAULT_LLM_MODEL=qwen2.5:1.5b
WHISPER_MODEL=base
WHISPER_DEVICE=cpu
TTS_VOICES_DIR=./voices
CORS_ORIGINS=http://localhost:5173
```

## REST API

### Auth
- `POST /api/auth/register` {email, password, name?} -> {access_token, token_type:"bearer", user:{id,email,name}}
- `POST /api/auth/login` (JSON {email,password} OR OAuth2 form) -> same shape
- `GET /api/auth/me` -> {id,email,name,created_at}

### Agents
- `GET /api/agents` -> [{agent...}] (owner's agents)
- `POST /api/agents` {name, description?, system_prompt, language:"auto|en|hi|hinglish|es|fr|de|pt|it|ja|zh", voice_gender:"female|male", voice_id, tts_provider:"piper", llm_model?, temperature?:0.7, greeting?, max_duration_sec?:600, silence_timeout_sec?:12} -> agent
- `GET /api/agents/{id}` -> agent (with `tools` list)
- `PATCH /api/agents/{id}` -> agent
- `DELETE /api/agents/{id}` -> {ok:true}
- Agent object: {id, name, description, system_prompt, language, voice_gender, voice_id, tts_provider, llm_model, temperature, greeting, max_duration_sec, silence_timeout_sec, created_at, updated_at}

### Voices
- `GET /api/voices?provider=piper&language=en&gender=female` -> [{voice_id, name, provider, language, gender, sample_rate}]

### Calls
- `GET /api/calls?agent_id=` -> [{id, agent_id, agent_name, status, started_at, ended_at, duration_sec, language, message_count, summary}]
- `GET /api/calls/{id}` -> {call..., agent:{...}, messages:[{id,role,text,language,intent,entities,latency_ms,created_at}], events:[{event_type,payload,created_at}]}
- `DELETE /api/calls/{id}` -> {ok:true}

### Tools
- `GET /api/tools` -> [{id, name, description, parameters, is_builtin}]
- `POST /api/agents/{id}/tools` {tool_id} -> {ok:true}
- `DELETE /api/agents/{id}/tools/{tool_id}` -> {ok:true}

### Health
- `GET /health` -> {status:"ok|degraded", version, services:{database,redis,stt,tts,llm}}
- `GET /health/ai` -> {stt:{...}, tts:{...}, llm:{...}, vad:{...}}
- `GET /health/stt|tts|llm|database|redis` -> {status, detail}

### Dashboard
- `GET /api/dashboard` -> {total_agents, total_calls, total_duration_sec, successful_calls, failed_calls, languages:{en:3,...}, recent_calls:[...]}

## WebSocket voice gateway — `ws://localhost:8000/ws/voice`

Client -> server (JSON text frames):
- `{"type":"start_call","agent_id":"<uuid>","token":"<jwt>"}` (auth inside first frame)
- `{"type":"audio","data":"<base64 int16 LE mono 16kHz>","seq":123}`
- `{"type":"end_call"}`
- `{"type":"ping"}`

Server -> client (JSON text frames):
- `{"type":"call_started","call_id":"...","agent":{"id","name","voice_gender","language"}}`
- `{"type":"state","state":"listening|thinking|speaking"}`
- `{"type":"transcript","role":"user|assistant","text":"...","language":"en","turn":3}`
- `{"type":"audio","data":"<base64 int16 LE>","sample_rate":22050,"chunk":7,"turn":3}` (many per turn)
- `{"type":"audio_end","turn":3}`
- `{"type":"interrupted"}` — server stopped TTS because user barged in
- `{"type":"latency","stt_ms":..,"llm_ms":..,"tts_ms":..,"total_ms":..,"turn":3}`
- `{"type":"call_ended","call_id":"...","duration_sec":..,"message_count":..}`
- `{"type":"error","code":"auth_failed|agent_not_found|stt_failed|...","message":"..."}`
- `{"type":"pong"}`

Behavior:
- On `start_call`: create call row, send `call_started`, speak agent greeting via TTS (audio frames + audio_end), state=speaking, then state=listening.
- VAD segments mic audio server-side. On speech end: STT -> transcript(user) -> thinking -> LLM (+tools) -> transcript(assistant) -> TTS chunks -> audio_end -> listening.
- Barge-in: if VAD detects speech while speaking, cancel TTS, send `interrupted`, go to listening and process the new utterance.
- Silence: if no speech for `silence_timeout_sec` after greeting/first prompt, speak a nudge once ("Are you still there?"); if still silent for another timeout, end call with reason.
- `end_call` or disconnect: finalize call (status completed), persist summary.

## Python provider interfaces (backend/app/ai/*/base.py)

```python
class STTResult: text: str; language: str; confidence: float; duration_ms: int
class SpeechToTextProvider(ABC):
    name: str
    async def transcribe(self, audio: np.ndarray, sample_rate: int, language: str | None = None) -> STTResult
    async def detect_language(self, audio: np.ndarray, sample_rate: int) -> str
    async def health(self) -> dict

class VoiceMeta: voice_id, name, provider, language, gender, sample_rate
class TextToSpeechProvider(ABC):
    name: str
    async def list_voices(self) -> list[VoiceMeta]
    async def synthesize(self, text: str, voice_id: str, language: str | None = None,
                         speed: float = 1.0) -> AsyncIterator[tuple[bytes, int]]  # (pcm16le chunk, sample_rate)
    async def health(self) -> dict

class LLMMessage: role, content (+ optional tool_calls / tool_call_id)
class LLMResult: text: str; tool_calls: list[dict]; latency_ms: int; model: str
class LLMProvider(ABC):
    name: str
    async def generate(self, messages: list[dict], system: str | None = None,
                       tools: list[dict] | None = None, temperature: float = 0.7,
                       max_tokens: int = 512) -> LLMResult
    async def health(self) -> dict

class VADProvider(ABC):
    name: str
    sample_rate: int = 16000
    def is_speech(self, chunk: np.ndarray) -> tuple[bool, float]  # (speech, probability)
    async def health(self) -> dict
```

- Tool calling: LLM may return `tool_calls=[{"name":..., "arguments":{...}}]`. If the model emits JSON tool calls in text (fallback), `ToolRegistry.parse_tool_call(text)` extracts them. Backend executes via registry, appends tool result as `role:"tool"` message, and calls LLM once more (max 2 tool rounds).
- NLP pipeline order per user turn: VAD -> STT -> detect_language -> intent/entities via LLM JSON (`{"intent":..., "entities":{...}, "sentiment":...}`) -> memory (last 10 msgs + summary + facts) -> LLM -> validate response (length/safety) -> TTS.
- Conversation memory: keep last N=10 messages verbatim; when > 20 messages, summarize older into `summary` via LLM; extract durable facts (name, order ids) via LLM JSON into `facts` dict stored on the call/session.
- Observability: every call logs CallEvent rows: call_started, speech_started, speech_ended, stt_started, stt_completed, llm_started, llm_completed, tts_started, tts_completed, agent_interrupted, tool_called, call_ended, error. Latency per turn stored on assistant message.

## Telephony stub
`backend/app/telephony/base.py` with `TelephonyProvider` ABC (place_call, answer, hangup, send_audio, on_audio) and `NoopTelephonyProvider`. Voice gateway must accept audio from EITHER websocket OR a telephony provider via the same `VoicePipeline` class.

## Tests (pytest, backend/tests)
- test_auth.py, test_agents.py, test_calls_api.py, test_health.py
- test_stt.py (synth audio via TTS or numpy tone -> whisper tiny smoke; skip if model missing)
- test_tts.py (synthesize short text, assert PCM bytes)
- test_llm.py (mock provider + ollama if reachable)
- test_vad.py (silence vs speech energy)
- test_nlp.py (language detect on sample texts, memory window/summary logic with mock LLM)
- test_tools.py (registry execute, parse_tool_call)
- test_voice_gateway.py (websocket: start_call with mock providers -> greeting audio; send fake speech audio -> transcript flow; barge-in cancels TTS)
- Use dependency overrides / monkeypatching so tests don't need real models by default; mark slow model tests.

## Frontend (Vite + React, JS, react-router-dom)
Routes: /login, /dashboard, /agents, /agents/new, /agents/:id, /calls, /calls/:id, /settings.
- api/client.js: fetch wrapper with JWT in localStorage (`va_token`), functions for all REST above + getVoices.
- hooks/useVoiceCall.js: manages WebSocket to /ws/voice, AudioWorklet mic capture (16kHz int16), playback queue of 22050Hz PCM with interrupt(), exposes {status, state, transcript[], latency, connect(agentId), disconnect(), muted, toggleMute, micState, connected}.
- components/VoiceOrb.jsx: animated orb reacting to state (listening=blue pulse, thinking=amber spin, speaking=green waveform bars).
- pages/CallPage.jsx (route /calls/live/:agentId or modal from agent page): orb, agent name, state label, live transcript list, controls (Mute, End Call), mic permission + connection + latency indicators.
- pages/Dashboard.jsx: stat cards + service status (from /health) + recent calls table.
- pages/Agents.jsx, AgentForm.jsx (all agent fields incl. voice picker fed by /api/voices), AgentDetail.jsx (info + Test Agent button -> /calls/live/:id).
- pages/Calls.jsx, CallDetail.jsx (transcript + events timeline + latencies).
- pages/Settings.jsx: service status cards, env info (LLM model, whisper model), "test" buttons hitting /health/*.
- Dark SaaS styling, single styles.css. No UI framework dependency required (custom CSS) to keep build light.

## Docker (still ship it)
docker-compose.yml: postgres:16, redis:7, backend (build ./backend), frontend (build ./frontend, nginx), ollama (ollama/ollama). Backend Dockerfile installs python deps + downloads piper voices at build. .env.example documents all vars.
