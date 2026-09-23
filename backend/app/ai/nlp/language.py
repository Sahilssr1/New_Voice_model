"""Lightweight text language detection: en | hi | hinglish.

Rules (no ML model required):
- Devanagari script present -> "hi".
- Romanized Hindi (Hinglish) vocabulary present -> "hinglish".
- Otherwise -> "en".

This is intentionally simple and dependency-free; a dedicated language-ID
model can replace it later behind the same function signature.
"""

from __future__ import annotations

import re

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")

# Distinctive romanized-Hindi tokens (strong indicators of Hinglish).
_STRONG_HINGLISH = {
    "mera", "meri", "mere", "tera", "teri", "tere", "tumhara", "tumhari",
    "aapka", "aapki", "aapke", "hamara", "hamari",
    "kya", "kyun", "kyon", "kaise", "kab", "kahan", "kaha", "kaun",
    "nahi", "nahin", "naheen",
    "chahiye", "batao", "bataiye", "batayein", "karo", "kijiye",
    "accha", "achha", "theek", "bahut", "thoda", "zyada",
    "mujhe", "mujhko", "tujhe", "aapko", "humko",
    "sakta", "sakti", "sakte", "hoga", "hogi", "honge",
    "gaya", "gayi", "gaye", "wala", "wali", "wale",
    "liye", "wahan", "yahan", "waha", "yaha", "phir",
    "aur", "lekin", "kyunki", "matlab",
}

# Common Hindi particles; only count toward Hinglish when >= 2 are present.
_WEAK_HINGLISH = {
    "hai", "hain", "ho", "hun", "hu", "tha", "thi", "the",
    "mein", "main", "me", "ne", "ko", "ka", "ki", "ke", "se",
    "par", "tak", "bhi", "toh", "to", "ab", "nah", "ji",
}

_TOKEN_RE = re.compile(r"[a-zA-Z]+")


def detect_text_language(text: str) -> str:
    """Return "en", "hi", or "hinglish" for the given text."""
    if not text:
        return "en"
    if _DEVANAGARI_RE.search(text):
        return "hi"
    tokens = [t.lower() for t in _TOKEN_RE.findall(text)]
    if not tokens:
        return "en"
    strong = sum(1 for t in tokens if t in _STRONG_HINGLISH)
    weak = sum(1 for t in tokens if t in _WEAK_HINGLISH)
    if strong >= 1 or weak >= 2:
        return "hinglish"
    return "en"
