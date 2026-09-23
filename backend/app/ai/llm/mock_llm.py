"""Mock LLM provider for tests and offline development.

Deterministic canned responses: echoes the last user message, and emits a
JSON tool-call block (text fallback format, no native tool_calls) when the
user mentions an "order", so the ToolRegistry.parse_tool_call fallback path
is exercised end to end.
"""

from __future__ import annotations

import time

from .base import LLMProvider, LLMResult

ORDER_TOOL_BLOCK = '```json\n{"tool": "get_order_status", "arguments": {"order_id": "12345"}}\n```'


def _role(m) -> str:
    return m.get("role") if isinstance(m, dict) else getattr(m, "role", "")


def _content(m) -> str:
    return m.get("content") if isinstance(m, dict) else (getattr(m, "content", "") or "")


class MockLLM(LLMProvider):
    name = "mock"

    def __init__(self, model: str = "mock") -> None:
        self.model = model

    async def generate(
        self,
        messages: list[dict],
        system: str | None = None,
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> LLMResult:
        t0 = time.perf_counter()
        last_user = ""
        tool_results: list[str] = []
        for m in messages or []:
            if _role(m) == "user":
                last_user = _content(m)
            elif _role(m) == "tool":
                tool_results.append(_content(m))

        if tool_results:
            text = f"Based on the lookup result: {tool_results[-1][:300]}"
        elif "order" in last_user.lower():
            text = f"I'll check that for you.\n{ORDER_TOOL_BLOCK}"
        elif last_user:
            text = f"Mock reply to: {last_user[:160]}"
        else:
            text = "Hello! This is a mock response."

        return LLMResult(
            text=text,
            tool_calls=[],
            latency_ms=int((time.perf_counter() - t0) * 1000),
            model=self.model,
        )

    async def health(self) -> dict:
        return {"status": "up", "provider": self.name, "model": self.model}
