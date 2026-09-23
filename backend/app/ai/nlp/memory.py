"""Short-term conversation memory.

Keeps the last N messages verbatim; when the history grows beyond a
threshold, older turns are summarized via the LLM and durable facts are
extracted into a dict. Facts/summary are persisted on the conversation
session by the voice pipeline.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

log = logging.getLogger(__name__)

WINDOW_SIZE = 10
SUMMARY_THRESHOLD = 20


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_json(text: str) -> dict:
    if not text:
        return {}
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidates = [m.group(1)] if m else []
    m2 = re.search(r"\{.*\}", text, re.S)
    if m2:
        candidates.append(m2.group(0))
    for cand in candidates:
        try:
            data = json.loads(cand)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            continue
    return {}


class ConversationMemory:
    """Per-call short-term memory."""

    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.summary: str = ""
        self.facts: dict = {}

    def add_message(
        self,
        role: str,
        text: str,
        language: str | None = None,
        intent: str | None = None,
        entities: dict | None = None,
        latency_ms: int | None = None,
    ) -> dict:
        msg = {
            "role": role,
            "text": text,
            "language": language,
            "intent": intent,
            "entities": entities or {},
            "latency_ms": latency_ms,
            "timestamp": _utcnow_iso(),
        }
        self.messages.append(msg)
        return msg

    def get_window(self, n: int = WINDOW_SIZE) -> list[dict]:
        """Return the last n messages verbatim."""
        return self.messages[-n:]

    def needs_summary(self) -> bool:
        """True when history is long and no summary exists yet."""
        return len(self.messages) > SUMMARY_THRESHOLD and not self.summary

    def _older_text(self) -> str:
        older = self.messages[:-WINDOW_SIZE]
        lines = [f"{m['role']}: {m['text']}" for m in older]
        return "\n".join(lines)

    async def summarize(self, llm) -> str:
        """Summarize older turns via the LLM; stores and returns the summary."""
        older_text = self._older_text()
        if not older_text.strip():
            return self.summary
        prompt = (
            "Summarize the following conversation between a user and a voice "
            "assistant in 3-5 sentences. Keep names, order numbers, dates and "
            "decisions.\n\n" + older_text
        )
        try:
            result = await llm.generate(
                [{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=256,
            )
            summary = (result.text or "").strip()
            if summary:
                self.summary = summary
        except Exception as exc:
            log.warning("Memory summarization failed: %s", exc)
        return self.summary

    async def extract_facts(self, llm) -> dict:
        """Extract durable facts (names, order ids, preferences) via the LLM."""
        recent = "\n".join(
            f"{m['role']}: {m['text']}" for m in self.get_window(SUMMARY_THRESHOLD)
        )
        prompt = (
            "Extract durable facts about the user from this conversation "
            "(name, order ids, phone numbers, preferences). Respond with ONLY "
            'a JSON object like {"name": "...", "order_ids": ["..."]}. '
            'Use {} if there are no durable facts.\n\n' + recent
        )
        try:
            result = await llm.generate(
                [{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=256,
            )
            data = _extract_json(result.text or "")
            if data:
                self.facts.update(data)
        except Exception as exc:
            log.warning("Fact extraction failed: %s", exc)
        return self.facts

    def to_dict(self) -> dict:
        return {
            "messages": self.messages,
            "summary": self.summary,
            "facts": self.facts,
        }
