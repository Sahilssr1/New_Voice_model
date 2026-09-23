# Run VoiceAgent on your own computer (Windows)

Everything is 100% open-source and runs locally — no API keys, no cloud.
Talk to the AI agent from your browser: microphone → local Whisper →
local Qwen LLM → local Piper voice → your speakers.

## 1. Install prerequisites (one time)

| Tool | Get it here | Check with |
|---|---|---|
| Python 3.12 | https://www.python.org/downloads/ — tick **"Add python.exe to PATH"** | `python --version` |
| Node.js 20+ | https://nodejs.org (LTS) | `node --version` |
| Ollama | https://ollama.com/download (Windows installer) | `ollama --version` |
| A browser | Chrome or Edge (for microphone access) | — |

Then pull the LLM model (one time, ~1 GB):

```powershell
ollama pull qwen2.5:3b
```

> The speech models are already in this bundle: 3 Piper voices live in
> `backend\voices\`. The Whisper `tiny` model (~75 MB) downloads itself
> automatically on the first call. The knowledge-base embedding model
> (~420 MB, multilingual for English/Hindi/Hinglish) downloads itself on the
> first document upload or KB search.

## 2. Start everything

Easiest — double-click / right-click → *Run with PowerShell*:

```
run-local.ps1
```

It starts Ollama (if needed), the backend API (port 8000) and the
frontend (port 5173) in separate windows.

Manual alternative (two PowerShell windows):

```powershell
# Window 1 — backend
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1        # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
# Recommended on CPU-only machines (much smaller torch download):
# pip install --index-url https://download.pytorch.org/whl/cpu torch
$env:DATABASE_URL="sqlite+aiosqlite:///./voiceagent.db"
$env:JWT_SECRET="dev-secret-key-min-32-bytes-long-ok"
$env:WHISPER_MODEL="small"
$env:TTS_VOICES_DIR="./voices"
$env:OLLAMA_MODEL="qwen2.5:3b"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
# Window 2 — frontend
cd frontend
npm install
npm run dev
```

## 3. Make a call

1. Open **http://127.0.0.1:5173** in Chrome/Edge.
2. **Register** a user (any email/password).
3. **Agents → New agent**: name it, pick language (English / Hindi / Hinglish)
   and voice gender — the voice is chosen from real voice metadata.
4. **Start live call** from the agent page, allow **microphone access**.
5. Speak. You should see: *Listening → Thinking → Speaking*, a live
   transcript, and hear the reply.

### Try the knowledge base

1. On the agent page, scroll to **Knowledge base** and upload a TXT or PDF
   (e.g. a price list or FAQ). Hindi documents work too — the default
   embedding model is multilingual.
2. Use **Test retrieval** to see which excerpts match a question.
3. Start a live call and ask about the document's content — the agent now
   answers from your file. Each turn with a KB hit is logged as a
   `kb_retrieved` event on the call detail page.

Sanity checks:

- `http://127.0.0.1:8000/health` → all services `up`
  (`redis: down` is fine locally — SQLite + in-process state are used).
- First reply is the slowest (models load into memory); later turns are faster.
- On CPU expect roughly 3–6 s per turn with `small` (recommended — reliable
  Hindi); use `WHISPER_MODEL=base` or `tiny` for speed at the cost of Hindi quality.

## 4. Troubleshooting

- **Port already in use** — close the other window running it, or change the port.
- **Ollama connection refused** — run `ollama serve` in its own window first.
- **Login page says "could not reach"** — the backend isn't running; start Window 1.
- **Mic denied** — click the lock icon in the address bar → allow microphone → reload.
- **No voice download needed** — voices ship in `backend\voices\`; if you add
  more, run `python -m piper.download_voices --download-dir ./voices <voice-id>`
  from inside `backend\`.

## 5. What's inside

- `backend/` — FastAPI: auth, agents, calls, tools, WebSocket voice gateway,
  faster-whisper STT, Piper TTS, Ollama LLM, SQLite (dev) / PostgreSQL (prod).
- `frontend/` — React + Vite dark SaaS UI with the live-call page.
- `docker-compose.yml` — production topology (Postgres, Redis, Ollama,
  backend, frontend via nginx).
- `CONTRACT.md` — the API/WebSocket contract. `ARCHITECTURE.md` — design notes.
