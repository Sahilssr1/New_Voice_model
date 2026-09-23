"""Ollama LLM provider.

Talks to a local Ollama server via POST {OLLAMA_BASE_URL}/api/chat.
Parses native Ollama tool_calls and additionally supports the JSON-in-text
fallback via ToolRegistry.parse_tool_call (imported lazily to avoid cycles).
"""

from __future__ import annotations

import logging
import os
import time

try:
    import httpx
except ImportError:  # optional dep; factory falls back to MockLLM
    httpx = None  # type: ignore[assignment]

from .base import LLMProvider, LLMResult

log = logging.getLogger(__name__)


def _default_llm_model() -> str:
    """Resolve the default Ollama model.

    Precedence: ``OLLAMA_MODEL`` env (set by run-local scripts) >
    ``DEFAULT_LLM_MODEL`` env > app settings > ``"qwen2.5:3b"``.
    """
    for var in ("OLLAMA_MODEL", "DEFAULT_LLM_MODEL"):
        val = os.environ.get(var)
        if val:
            return val
    try:
        from app.core.config import settings

        return settings.DEFAULT_LLM_MODEL or "qwen2.5:3b"
    except Exception:
        return "qwen2.5:3b"


def _make_client(timeout: float):
    """Create an httpx client that ignores proxy env vars.

    Ollama is a local service; proxy env vars must not apply. This also
    avoids a crash when NO_PROXY contains bracketed IPv6 literals
    (e.g. "[::1]"), which httpx cannot parse.
    """
    return httpx.AsyncClient(timeout=timeout, trust_env=False)


def _as_dicts(messages: list) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        if isinstance(m, dict):
            out.append(m)
        else:  # LLMMessage dataclass
            d = {"role": m.role, "content": m.content or ""}
            if m.tool_calls:
                d["tool_calls"] = m.tool_calls
            if m.tool_call_id:
                d["tool_call_id"] = m.tool_call_id
            if m.name:
                d["name"] = m.name
            out.append(d)
    return out


def _extract_tool_calls(message: dict) -> list[dict]:
    calls: list[dict] = []
    for tc in message.get("tool_calls") or []:
        fn = tc.get("function") or {}
        name = fn.get("name") or tc.get("name")
        args = fn.get("arguments") or tc.get("arguments") or {}
        if name:
            calls.append({"name": name, "arguments": args if isinstance(args, dict) else {}})
    return calls


class OllamaLLM(LLMProvider):
    name = "ollama"

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        if httpx is None:
            raise ImportError("httpx is not installed; OllamaLLM unavailable")
        self.base_url = (base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.model = model or _default_llm_model()
        self.timeout = timeout

    async def generate(
        self,
        messages: list[dict],
        system: str | None = None,
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> LLMResult:
        msgs = _as_dicts(messages)
        if system and not (msgs and msgs[0].get("role") == "system"):
            msgs = [{"role": "system", "content": system}] + msgs

        payload: dict = {
            "model": self.model,
            "messages": msgs,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if tools:
            payload["tools"] = tools

        t0 = time.perf_counter()
        try:
            async with _make_client(self.timeout) as client:
                resp = await client.post(f"{self.base_url}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            raise RuntimeError(f"Ollama request failed: {exc}") from exc
        latency_ms = int((time.perf_counter() - t0) * 1000)

        message = data.get("message") or {}
        text = message.get("content") or ""
        tool_calls = _extract_tool_calls(message)

        # Fallback: model emitted a JSON tool call inside the text.
        if not tool_calls and text:
            try:
                from ...tools.registry import ToolRegistry

                parsed = ToolRegistry.parse_tool_call(text)
                if parsed:
                    tool_calls.append(parsed)
            except Exception:
                pass

        return LLMResult(
            text=text,
            tool_calls=tool_calls,
            latency_ms=latency_ms,
            model=data.get("model") or self.model,
        )

    async def health(self) -> dict:
        try:
            async with _make_client(5.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                resp.raise_for_status()
                data = resp.json()
            models = [m.get("name") for m in data.get("models", [])]
            return {
                "status": "up",
                "provider": self.name,
                "base_url": self.base_url,
                "model": self.model,
                "models_available": models,
            }
        except Exception as exc:
            return {
                "status": "down",
                "provider": self.name,
                "base_url": self.base_url,
                "model": self.model,
                "detail": str(exc)[:300],
            }
