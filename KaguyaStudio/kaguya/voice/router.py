"""What to do with a spoken sentence while agents may be working (Phase B).

Spoken input never cancels a running job. It becomes one of:
* ``status``  – "como está?", "status", "o que vocês estão fazendo" → spoken summary;
* ``later``   – "depois ...", "para depois ...", "anota ..." → DEPOIS queue;
* ``idea``    – "ideia ..." → IDEIA;
* ``stop``    – "parar de falar", "silêncio" → stops TTS only (never the job);
* ``message`` – anything else → queued as a normal message (runs after the current task).
"""
from __future__ import annotations

import re
import unicodedata


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    return "".join(c for c in t if not unicodedata.combining(c)).lower().strip()


STATUS = re.compile(r"^(qual (e )?o )?status\b|^como (esta|vai|anda)|^o que (voces|vcs|voce) (estao|esta) fazendo|^andamento\b")
LATER = re.compile(r"^(para |pra )?depois[,:]?\s+|^anota[r]?[,:]?\s+|^lembra(r)?[,:]? (de )?")
IDEA = re.compile(r"^ideia[,:]?\s+")
STOP = re.compile(r"^(pare|para|parar) de falar|^(silencio|cala a boca|chega de falar)\b")


def route(text: str) -> tuple[str, str]:
    raw = (text or "").strip()
    n = _norm(raw)
    if not n:
        return "none", ""
    if STOP.search(n):
        return "stop", ""
    if STATUS.search(n):
        return "status", ""
    m = IDEA.match(n)
    if m:
        return "idea", raw[m.end():].strip() or raw
    m = LATER.match(n)
    if m:
        return "later", raw[m.end():].strip() or raw
    return "message", raw
