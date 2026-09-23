"""LLM provider interface.

Business logic calls LLMProvider.generate() and never touches a concrete
model client, so Ollama / llama.cpp / vLLM / mock backends are interchangeable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class LLMMessage:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str = ""
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class LLMResult:
    text: str
    tool_calls: list[dict] = field(default_factory=list)  # [{"name":..,"arguments":{}}]
    latency_ms: int = 0
    model: str = ""


class LLMProvider(ABC):
    """Abstract LLM provider with OpenAI-style tool calling."""

    name: str = "base"

    @abstractmethod
    async def generate(
        self,
        messages: list[dict],
        system: str | None = None,
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> LLMResult:
        """Generate a response.

        Args:
            messages: [{"role":..., "content":...}, ...]; a leading
                {"role": "system"} entry is also accepted.
            system: optional system prompt (alternative to a system message).
            tools: optional OpenAI-style tool schemas
                [{"type":"function","function":{...}}].
        """

    @abstractmethod
    async def health(self) -> dict:
        """Return a health dict, e.g. {"status": "up", ...}."""
