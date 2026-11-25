"""The Hub as one object the Studio talks to: scan, watch, check, plan, route."""
from __future__ import annotations

from pathlib import Path
import threading

from .adapters import ClaudeAdapter, CodexAdapter
from .registry import Registry
from .watcher import ChangeDetector


class HubService:
    def __init__(self, data_dir: Path, projects=lambda: [], adapters=None, exes=lambda: {}):
        self.registry = Registry(Path(data_dir) / "hub" / "extensoes.sqlite3")
        self.projects = projects                       # callable → list of project folders the Studio knows
        self.adapters = adapters or {"claude": ClaudeAdapter(), "codex": CodexAdapter()}
        self.exes = exes                               # callable → {"claude": path, "codex": path}
        self.problems: dict[str, list[tuple[str, str]]] = {}
        self.last_scan = ""
        self._lock = threading.Lock()
        self.detector = ChangeDetector(self.sources)
        self.listeners: list = []

    def sources(self) -> list[Path]:
        projects = [str(p) for p in self.projects()]
        out = []
        for a in self.adapters.values():
            out += a.sources(projects)
        return out

    def scan(self) -> list[dict]:
        """Read-only discovery of every provider + reconciliation. Original files are never modified."""
        import time
        with self._lock:
            projects = [str(p) for p in self.projects()]
            events = []
            exes = self.exes() or {}
            for pid, adapter in self.adapters.items():
                if exes.get(pid) and getattr(adapter, "exe", None) is None:
                    adapter.exe = exes[pid]
                found, problems = adapter.discover(projects)
                self.problems[pid] = problems
                events += self.registry.reconcile(pid, found, {src for src, _ in problems})
            self.last_scan = time.strftime("%d/%m %H:%M:%S")
            self.detector.prime()
        for fn in list(self.listeners):
            try:
                fn(events)
            except Exception:
                pass
        return events

    def poll(self) -> list[dict]:
        """Rescan only when a source changed and settled (debounced)."""
        if self.detector.poll():
            return self.scan()
        return []
