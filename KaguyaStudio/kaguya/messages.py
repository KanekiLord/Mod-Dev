"""Chat message intents.

* ``DEPOIS:`` / ``IDEIA:`` go to the queue and **never** reach a running agent, so an idea
  "para depois" cannot make the agents switch tasks.
* ``AGORA:`` is an execute request that asks the UI for confirmation before interrupting.
* ``@codex: / @claude: / @equipe:`` choose the destination.
* ``PARALELO:`` followed by lines ``@codex: ...`` / ``@claude: ...`` describes independent
  sub-tasks that run in separate Git worktrees.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re

_TARGET = re.compile(r"^\s*@\s*(codex|claude|equipe)\s*:?\s*", re.I)
_INTENT = re.compile(r"^\s*(depois|ideia|agora|paralelo)\s*:\s*", re.I)


@dataclass
class Intent:
    kind: str            # execute | later | idea
    target: str          # codex | claude | equipe | paralelo
    text: str
    interrupt: bool = False
    subtasks: list[tuple[str, str]] = field(default_factory=list)


def classify_message(text: str, default_target: str = "equipe") -> Intent:
    value = (text or "").strip()
    if not value:
        raise ValueError("Mensagem vazia")
    kind, target, interrupt, parallel = "execute", default_target, False, False
    if not value.startswith("@"):
        # "Kaguya, olha isso…" → Codex; "Miwa, vê isso…" → Claude Code (the name stays in the text)
        from .live.wake import detect_name
        called, _rest = detect_name(value)
        if called and not re.match(r"^\W*(codex|claude)\b", value, re.I):
            target = called
    for _ in range(4):
        m = _TARGET.match(value)
        if m:
            target = m.group(1).lower()
            value = value[m.end():].strip()
            continue
        m = _INTENT.match(value)
        if m:
            label = m.group(1).lower()
            if label == "depois":
                kind = "later"
            elif label == "ideia":
                kind = "idea"
            elif label == "agora":
                interrupt = True
            else:
                parallel = True
                value = value[m.end():].strip()
                break  # the remaining lines are '@agent: subtask' entries
            value = value[m.end():].strip()
            continue
        break
    if not value:
        raise ValueError("Tarefa vazia")
    if target not in ("codex", "claude", "equipe"):
        raise ValueError("Destino inválido")
    intent = Intent(kind=kind, target=target, text=value, interrupt=interrupt)
    if parallel:
        subtasks = []
        for line in value.splitlines():
            m = re.match(r"^\s*[-*•]?\s*@\s*(codex|claude)\s*:?\s*(.+)$", line, re.I)
            if m and m.group(2).strip():
                subtasks.append((m.group(1).lower(), m.group(2).strip()))
        if len(subtasks) < 2:
            raise ValueError("PARALELO: informe pelo menos duas linhas '@codex: ...' / '@claude: ...' independentes.")
        intent.target = "paralelo"
        intent.subtasks = subtasks
    return intent
