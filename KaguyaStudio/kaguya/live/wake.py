"""Calling an assistant by name: "Kaguya, olha isso…" → Codex; "Miwa, vê isso…" → Claude Code.

Used for typed messages and for the background voice listener. The transcription is local
(faster-whisper); names are matched with the spellings Whisper usually produces in pt-BR.
"""
from __future__ import annotations

import re
import unicodedata

NAMES = {
    "codex": ["kaguya", "kaguia", "caguia", "caguya", "kagu ya", "kagoya", "cagaia", "kaguyah", "codex", "codeks"],
    "claude": ["miwa", "miua", "mi wa", "miva", "mihwa", "miwah", "miuá", "claude", "cloud", "clode"],
}
_GREET = r"(?:ei|ey|hey|oi|ola|olá|e ai|eai|fala)"


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


def detect_name(text: str, anywhere: bool = False) -> tuple[str | None, str]:
    """Return (agent, request without the name). The name must open the sentence (after an optional
    greeting) unless ``anywhere`` is set — avoids triggering on "a Kaguya disse…" in a conversation."""
    n = _norm(text)
    for agent, names in NAMES.items():
        alt = "|".join(re.escape(x) for x in sorted(names, key=len, reverse=True))
        pat = (rf"^\W*(?:{_GREET}\W+)?(?:{alt})\b(?:\s*\((?:codex|claude(?: code)?)\))?[\s,.:;!?-]*" if not anywhere
               else rf"\b(?:{alt})\b[\s,.:;!?-]*")
        m = re.search(pat, n)
        if m:
            # map the match back onto the original text (normalisation keeps the length for pt-BR letters)
            rest = (text[m.end():] if len(n) == len(text) else n[m.end():]).strip()
            return agent, rest
    return None, text.strip()
