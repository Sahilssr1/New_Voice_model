# run-local.ps1 — start the whole VoiceAgent stack on Windows.
# Run from the repo root:  powershell -ExecutionPolicy Bypass -File run-local.ps1
# (or right-click -> "Run with PowerShell").
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

function Need($cmd, $hint) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
    Write-Host "MISSING: $cmd — $hint" -ForegroundColor Red
    exit 1
  }
}

Need python "Install Python 3.12 from https://www.python.org/downloads/ (tick 'Add to PATH')"
Need node   "Install Node.js LTS from https://nodejs.org"
Need ollama "Install Ollama from https://ollama.com/download"

# Ollama daemon
try { ollama list | Out-Null } catch { Start-Process ollama -ArgumentList 'serve' -WindowStyle Hidden }
ollama pull qwen2.5:1.5b | Out-Null

# Backend venv (create once)
$venvPy = Join-Path $root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
  Write-Host 'Creating backend venv + installing deps (first run takes a few minutes)...'
  Push-Location (Join-Path $root 'backend')
  python -m venv .venv
  & .\.venv\Scripts\python.exe -m pip install -r requirements.txt
  Pop-Location
}

# Frontend deps (install once)
if (-not (Test-Path (Join-Path $root 'frontend\node_modules'))) {
  Write-Host 'Installing frontend deps (first run)...'
  Push-Location (Join-Path $root 'frontend')
  npm install
  Pop-Location
}

$envBlock = '$env:DATABASE_URL="sqlite+aiosqlite:///./voiceagent.db"; ' +
            '$env:JWT_SECRET="dev-secret-key-min-32-bytes-long-ok"; ' +
            '$env:WHISPER_MODEL="base"; ' +
            '$env:TTS_VOICES_DIR="./voices"; ' +
            '$env:OLLAMA_MODEL="qwen2.5:1.5b"; '

$backendCmd = "cd '$root\backend'; " + $envBlock + ".\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
Start-Process powershell -ArgumentList '-NoExit', '-Command', $backendCmd

$frontendCmd = "cd '$root\frontend'; npm run dev"
Start-Process powershell -ArgumentList '-NoExit', '-Command', $frontendCmd

Write-Host ''
Write-Host 'VoiceAgent is starting.' -ForegroundColor Green
Write-Host 'Open http://127.0.0.1:5173 in Chrome/Edge, register, create an agent, start a live call.'
Write-Host 'Backend health: http://127.0.0.1:8000/health'
