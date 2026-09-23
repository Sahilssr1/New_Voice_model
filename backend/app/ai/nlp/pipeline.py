"""NLP pipeline around the LLM.

Per user turn: intent/entity/sentiment extraction via a small LLM JSON call
(with regex fallback), and response validation/cleanup before TTS.

Dedicated NLP models can be plugged in later behind these method signatures;
for the MVP the LLM performs the analysis reliably.
"""

from __future__ import annotations

import json
import logging
import re

log = logging.getLogger(__name__)

MAX_RESPONSE_CHARS = 600

_FENCE_RE = re.compile(r"```.*?```", re.S)
# Trailing raw JSON tool-call object (fallback format) at end of a response.
_TRAILING_TOOL_JSON_RE = re.compile(
    r'\{\s*"(?:tool|name)"\s*:\s*"[^"]+"\s*,.*\}\s*$', re.S
)
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


def _extract_json(text: str) -> dict:
    if not text:
        return {}
    m = _JSON_BLOCK_RE.search(text)
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


class NLPPipeline:
    """Turn-level NLP: intent/entities/sentiment + response validation."""

    async def process_turn(
        self, text: str, language: str, llm
    ) -> dict:
        """Extract {"intent", "entities", "sentiment"} for a user utterance."""
        fallback = {"intent": "general", "entities": {}, "sentiment": "neutral"}
        if not (text or "").strip():
            return fallback
        prompt = (
            "Analyze this user message for a voice assistant. "
            'Respond with ONLY a JSON object: {"intent": "<short_snake_case_intent>", '
            '"entities": {"<key>": "<value>"}, "sentiment": "positive|neutral|negative"}. '
            "Extract order ids, names, phone numbers, dates as entities when present.\n"
            f"User language: {language}\n"
            f'User message: """{text.strip()}"""'
        )
        try:
            result = await llm.generate(
                [{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=160,
            )
            data = _extract_json(result.text or "")
            intent = data.get("intent") or "general"
            entities = data.get("entities") or {}
            sentiment = data.get("sentiment") or "neutral"
            if sentiment not in ("positive", "neutral", "negative"):
                sentiment = "neutral"
            return {
                "intent": str(intent)[:64],
                "entities": entities if isinstance(entities, dict) else {},
                "sentiment": sentiment,
            }
        except Exception as exc:
            log.warning("NLP process_turn failed, using fallback: %s", exc)
            return fallback

    def validate_response(self, text: str) -> str:
        """Clean an LLM response for speech output.

        Strips code fences and JSON tool-call blocks, collapses whitespace,
        and clamps length so TTS stays snappy.
        """
        t = text or ""
        t = _FENCE_RE.sub(" ", t)
        t = _TRAILING_TOOL_JSON_RE.sub(" ", t)
        t = re.sub(r"\s+", " ", t).strip()
        if len(t) > MAX_RESPONSE_CHARS:
            t = t[: MAX_RESPONSE_CHARS - 3].rstrip() + "..."
        return t or "I'm sorry, I couldn't come up with a response."
