"""Change detection without extra dependencies: periodic stat snapshots with debounce.

A source is only re-read after its snapshot stayed identical for ``settle`` seconds, so a file in the middle of being
written is never parsed. Works the same on Windows/Linux, survives sleep, network drives and editors that replace files.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import time

MAX_ENTRIES = 6000


def stamp(path: Path) -> str:
    """Cheap fingerprint of a file or a folder tree (names, sizes, mtimes — never contents)."""
    p = Path(path)
    try:
        if p.is_file():
            st = p.stat()
            return f"f{st.st_mtime_ns}:{st.st_size}"
        if p.is_dir():
            h = hashlib.sha1()
            n = 0
            for base, dirs, files in os.walk(p):
                dirs[:] = sorted(d for d in dirs if not d.startswith((".git", "node_modules", "__pycache__")))
                rel = os.path.relpath(base, p)
                if rel.count(os.sep) > 5:
                    dirs[:] = []
                for f in sorted(files):
                    try:
                        st = os.stat(os.path.join(base, f))
                    except OSError:
                        continue
                    h.update(f"{rel}/{f}:{st.st_mtime_ns}:{st.st_size};".encode("utf-8", "replace"))
                    n += 1
                    if n > MAX_ENTRIES:
                        return "d" + h.hexdigest() + "+"
            return "d" + h.hexdigest()
    except OSError:
        return "?"
    return "-"


class ChangeDetector:
    def __init__(self, sources, settle: float = 1.5, clock=time.monotonic):
        self.sources = sources              # callable → list[Path]
        self.settle, self.clock = settle, clock
        self.stable: dict[str, str] = {}
        self._pending: dict[str, tuple[str, float]] = {}

    def prime(self):
        self.stable = {str(p): stamp(p) for p in self.sources()}
        self._pending.clear()

    def poll(self) -> list[str]:
        """Sources whose change has settled since the last call (empty when nothing to do)."""
        now = self.clock()
        current = {str(p): stamp(p) for p in self.sources()}
        ready = []
        for src, st in current.items():
            if self.stable.get(src) == st:
                self._pending.pop(src, None)
                continue
            seen = self._pending.get(src)
            if seen is None or seen[0] != st:
                self._pending[src] = (st, now)          # still changing: wait until it holds still
            elif now - seen[1] >= self.settle:
                ready.append(src)
                self.stable[src] = st
                self._pending.pop(src, None)
        for src in list(self.stable):
            if src not in current:
                self.stable.pop(src)
                ready.append(src)
        return ready
