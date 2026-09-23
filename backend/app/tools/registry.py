"""Tool abstraction: ToolRegistry.

Tools are registered with an OpenAI-style JSON schema. The LLM requests a
tool either via native tool_calls or by emitting a JSON block in text, which
parse_tool_call() extracts. Backend executes via registry.execute().
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re

log = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)
# Shallow match for a raw {"tool": "...", ...} / {"name": "...", ...} object.
_RAW_TOOL_RE = re.compile(r"\{[^{}]*\"(?:tool|name)\"\s*:[^{}]*\}")


class ToolDefinition:
    def __init__(self, name: str, description: str, parameters: dict, func) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters or {"type": "object", "properties": {}}
        self.func = func


class ToolRegistry:
    """Registry of callable tools with JSON schemas."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    # -- registration ------------------------------------------------------
    def register(self, name: str, description: str, parameters: dict, func) -> None:
        self._tools[name] = ToolDefinition(name, description, parameters, func)

    def tool(self, name: str, description: str, parameters: dict):
        """Decorator form of register()."""

        def _decorator(func):
            self.register(name, description, parameters, func)
            return func

        return _decorator

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def schemas(self, names: list[str] | None = None) -> list[dict]:
        """OpenAI-style function schemas, optionally filtered by name."""
        wanted = set(names) if names else None
        out = []
        for name, tool in self._tools.items():
            if wanted is not None and name not in wanted:
                continue
            out.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
            )
        return out

    def subset(self, names: list[str] | None) -> "ToolRegistry":
        """Return a new registry containing only the named tools."""
        new = ToolRegistry()
        if names is None:
            names = self.names()
        for name in names:
            if name in self._tools:
                t = self._tools[name]
                new.register(t.name, t.description, t.parameters, t.func)
        return new

    # -- parsing -----------------------------------------------------------
    @staticmethod
    def parse_tool_call(text: str) -> dict | None:
        """Extract {"name", "arguments"} from text.

        Handles ```json fenced blocks, whole-text JSON, and raw inline
        {"tool": ...} / {"name": ...} objects.
        """
        if not text:
            return None
        candidates: list[str] = []
        candidates.extend(_FENCE_RE.findall(text))
        stripped = text.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            candidates.append(stripped)
        candidates.extend(_RAW_TOOL_RE.findall(text))
        for cand in candidates:
            try:
                data = json.loads(cand)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            name = data.get("tool") or data.get("name")
            args = (
                data.get("arguments")
                or data.get("args")
                or data.get("parameters")
                or {}
            )
            if name and isinstance(args, dict):
                return {"name": str(name), "arguments": args}
        return None

    # -- execution ---------------------------------------------------------
    def _validate_args(self, tool: ToolDefinition, args: dict) -> None:
        required = (tool.parameters or {}).get("required") or []
        missing = [r for r in required if r not in (args or {})]
        if missing:
            raise ValueError(
                f"Missing required arguments for tool '{tool.name}': {missing}"
            )

    async def execute(self, name: str, args: dict | None) -> dict:
        """Execute a tool; returns {"ok": True, "result": ...}.

        Raises KeyError for unknown tools and ValueError for bad arguments.
        """
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"Unknown tool: {name}")
        args = dict(args or {})
        self._validate_args(tool, args)
        try:
            result = tool.func(**args)
        except TypeError as exc:
            raise ValueError(f"Invalid arguments for tool '{name}': {exc}") from exc
        if inspect.isawaitable(result):
            result = await result
        return {"ok": True, "result": result}
