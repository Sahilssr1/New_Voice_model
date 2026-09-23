"""Conversation service: LLM message building + tool-calling loop.

build_llm_messages() composes the system prompt, conversation summary,
durable facts, and the recent message window. run_tool_loop() drives the
LLM -> tool -> LLM cycle (max 2 tool rounds per the contract).
"""

from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)


def _agent_get(agent, name: str, default=None):
    if isinstance(agent, dict):
        return agent.get(name, default)
    return getattr(agent, name, default)


def build_llm_messages(agent, memory, kb_context: str | None = None) -> list[dict]:
    """Build the chat message list for the LLM.

    Layout: [system, *last_10_messages]. The system block carries the agent
    persona, language instruction, running summary, extracted facts, and
    (when provided) knowledge-base excerpts relevant to the current turn.
    """
    parts: list[str] = []
    system_prompt = _agent_get(agent, "system_prompt") or (
        "You are a helpful, friendly voice assistant. "
        "Speak naturally and concisely."
    )
    parts.append(system_prompt)

    language = _agent_get(agent, "language", "auto") or "auto"
    if language != "auto":
        parts.append(f"Always respond in the '{language}' language.")
        if language == "hi":
            # Piper's Hindi voice is trained on Devanagari text; Whisper
            # often transcribes Hindi speech in Roman script, and the LLM
            # mirrors the input script. Force Devanagari so TTS pronounces
            # correctly.
            parts.append(
                "Always write your reply in Devanagari script "
                "(\u0926\u0947\u0935\u0928\u093e\u0917\u0930\u0940). Never use Roman or Latin "
                "script, even if the user message is in Roman Hindi."
            )
    else:
        parts.append(
            "Detect the user's language from their message and always "
            "respond in that same language."
        )
    parts.append(
        "Keep responses short and conversational (1-3 sentences), suitable "
        "for spoken output. Never include code blocks, JSON, or tool-call "
        "syntax in your spoken reply. Always understand the user's full "
        "message and intent before answering; never answer based on a "
        "single keyword."
    )

    summary = getattr(memory, "summary", "") or ""
    if summary:
        parts.append(f"Conversation summary so far: {summary}")
    facts = getattr(memory, "facts", None) or {}
    if facts:
        try:
            parts.append("Known facts: " + json.dumps(facts, ensure_ascii=False))
        except (TypeError, ValueError):
            pass

    if kb_context:
        parts.append(
            "Knowledge base excerpts relevant to the user's question:\n"
            f"{kb_context}\n"
            "Use these excerpts to answer when they are relevant. If they do "
            "not cover the question, say so briefly and answer from general "
            "knowledge instead of inventing details."
        )

    messages: list[dict] = [{"role": "system", "content": "\n".join(parts)}]
    window = memory.get_window(10) if hasattr(memory, "get_window") else []
    for m in window:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        messages.append({"role": role, "content": m.get("text") or ""})
    return messages


async def run_tool_loop(
    llm,
    messages: list[dict],
    registry,
    tool_names: list[str] | None = None,
    temperature: float = 0.7,
    max_tokens: int = 512,
    max_rounds: int = 2,
) -> tuple[str, int, list[dict]]:
    """Run the LLM with tool support.

    Returns (final_text, total_llm_latency_ms, tool_events). The LLM may
    request tools via native tool_calls or via a JSON block in text
    (parsed with ToolRegistry.parse_tool_call). Tool results are appended
    as role:"tool" messages and the LLM is called again, up to max_rounds
    tool rounds plus one final answer pass.
    """
    tools = registry.schemas(tool_names) if registry is not None else []
    msgs = list(messages or [])
    system = None
    if msgs and msgs[0].get("role") == "system":
        system = msgs[0].get("content")
        msgs = msgs[1:]

    total_latency = 0
    tool_events: list[dict] = []

    for _ in range(max_rounds + 1):
        result = await llm.generate(
            msgs,
            system=system,
            tools=tools or None,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        total_latency += result.latency_ms or 0

        calls = list(result.tool_calls or [])
        if not calls and result.text and registry is not None:
            parsed = registry.parse_tool_call(result.text)
            if parsed:
                calls.append(parsed)
        if not calls:
            return result.text or "", total_latency, tool_events

        # Announce this assistant turn once (with its tool calls), then
        # append each tool's result as a role:"tool" message.
        msgs.append(
            {
                "role": "assistant",
                "content": result.text or "",
                "tool_calls": [
                    {"name": c.get("name"), "arguments": c.get("arguments") or {}}
                    for c in calls
                ],
            }
        )
        for call in calls:
            name = call.get("name")
            args = call.get("arguments") or {}
            try:
                if registry is None:
                    raise KeyError(f"Unknown tool: {name}")
                outcome = await registry.execute(name, args)
                tool_events.append({"tool": name, "arguments": args, "ok": True})
                content = json.dumps(outcome.get("result"), ensure_ascii=False, default=str)
            except Exception as exc:
                tool_events.append(
                    {"tool": name, "arguments": args, "ok": False, "error": str(exc)}
                )
                content = json.dumps({"ok": False, "error": str(exc)})
                log.warning("Tool '%s' failed: %s", name, exc)
            msgs.append({"role": "tool", "name": name, "content": content})

    # Out of tool rounds: one final answer without tools.
    result = await llm.generate(
        msgs, system=system, temperature=temperature, max_tokens=max_tokens
    )
    total_latency += result.latency_ms or 0
    return result.text or "", total_latency, tool_events
