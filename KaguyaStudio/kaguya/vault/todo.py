"""Read-only adapter for the vault's official task list (``tasks/todo.md``).

The real format still has to be confirmed on the user's vault, so this module only *reads*
Markdown check-lists (``- [ ]`` / ``- [x]``) grouped by heading. Proposed additions are drafted
as a separate note in the outbox for the user to paste/approve; ``todo.md`` is never edited.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

ITEM = re.compile(r"^(\s*)[-*+]\s+\[( |x|X|/|-)\]\s+(.*)$")
HEAD = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass
class TodoItem:
    text: str
    done: bool
    state: str
    section: str
    line: int
    indent: int


def find_todo(vault: Path) -> Path | None:
    for rel in ("tasks/todo.md", "Tasks/todo.md", "tasks/TODO.md", "todo.md"):
        p = Path(vault) / rel
        if p.is_file():
            return p
    return None


def parse_todo(text: str) -> list[TodoItem]:
    items, section = [], ""
    for n, line in enumerate(text.splitlines(), 1):
        h = HEAD.match(line)
        if h:
            section = h.group(2)
            continue
        m = ITEM.match(line)
        if m:
            mark = m.group(2)
            state = {"x": "feito", "X": "feito", "/": "em andamento", "-": "cancelado"}.get(mark, "aberto")
            items.append(TodoItem(m.group(3).strip(), mark in "xX", state, section, n, len(m.group(1))))
    return items


def read_todo(vault: Path) -> tuple[Path | None, list[TodoItem]]:
    path = find_todo(vault)
    if not path:
        return None, []
    try:
        return path, parse_todo(path.read_text(encoding="utf-8-sig", errors="replace"))
    except OSError:
        return path, []


def proposal_markdown(tasks: list[dict]) -> str:
    """Lines in the same check-list style, for the user to add to todo.md themselves."""
    return "\n".join(f"- [ ] {t['title'].strip()}  <!-- Kaguya #{t['id']} -->" for t in tasks)
