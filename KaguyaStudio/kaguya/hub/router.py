"""Who really has what — and how Kaguya and Miwa share it without copying plugins between clients.

* ``route``      — a request that needs a capability goes to the assistant that has it (verified first).
* ``context``    — a short list for the prompt (not every skill: contextual skills stay with each client).
* delegation     — an assistant writes ``[[DELEGAR:kaguya|miwa: pedido]]``; the Studio queues it for the other one.
* ``ResourceLocks`` — one writer per 3D file / app at a time, with a backup before the task starts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import re
import shutil
import threading

from .model import STATES

AGENTS = {"codex": "Kaguya", "claude": "Miwa"}
BY_NAME = {"kaguya": "codex", "codex": "codex", "miwa": "claude", "claude": "claude"}
KEYWORDS = {"blender": ("blender", ".blend"), "blockbench": ("blockbench", ".bbmodel", "bbmodel"),
            "elevenlabs": ("elevenlabs", "eleven labs"), "github": ("github", "pull request"),
            "playwright": ("playwright",), "figma": ("figma",), "obsidian": ("obsidian",), "unity": ("unity",)}
DELEGATE = re.compile(r"\[\[\s*DELEGAR\s*:\s*(kaguya|miwa|codex|claude)\s*:\s*(.+?)\]\]", re.I | re.S)
APP_FILES = {".blend": "Blender", ".bbmodel": "Blockbench"}


@dataclass
class Route:
    capability: str = ""
    agent: str = ""                       # who should do it
    requested: str = ""
    reason: str = ""
    verified: bool = False
    alternatives: list[str] = field(default_factory=list)

    @property
    def redirect(self) -> bool:
        return bool(self.agent and self.requested and self.agent != self.requested)


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def holders(registry, capability: str) -> dict[str, list]:
    """{agent: [extensions providing it]} — MCPs and plugins only, enabled, not removed."""
    out: dict[str, list] = {}
    cap = _key(capability)
    for e in registry.all(include_removed=False):
        if e.provider not in AGENTS or e.kind not in ("mcp", "plugin"):
            continue
        if set(e.flags) & {"desabilitado", "removido", "somente_web", "incompativel"}:
            continue
        if cap in _key(e.name) or cap in _key(e.parent) or any(cap in _key(t) for t in e.tools):
            out.setdefault(e.provider, []).append(e)
    return out


def mentioned(text: str, registry) -> list[str]:
    low = (text or "").lower()
    caps = [c for c, words in KEYWORDS.items() if any(w in low for w in words)]
    for e in registry.all(include_removed=False):
        if e.kind == "mcp" and e.provider in AGENTS and len(e.name) >= 4 and e.name.lower() in low and e.name not in caps:
            caps.append(e.name)
    return caps


def _rank(exts) -> tuple[int, bool]:
    best = max((STATES.index(e.state) if e.state in STATES else 0) for e in exts)
    verified = any(e.usable() for e in exts)
    return (best + (10 if verified else 0)), verified


def route(registry, text: str, requested: str = "") -> Route | None:
    caps = mentioned(text, registry)
    if not caps:
        return None
    cap = caps[0]
    who = holders(registry, cap)
    r = Route(capability=cap, requested=requested if requested in AGENTS else "")
    if not who:
        r.reason = (f"Nenhuma IA tem “{cap}” configurado no Codex ou no Claude Code. Peça a instalação no Hub "
                    "(Extensões › Solicitar instalação).")
        return r
    ranked = sorted(who, key=lambda a: _rank(who[a]), reverse=True)
    anyone_verified = any(_rank(who[a])[1] for a in who)
    if r.requested in who and (_rank(who[r.requested])[1] or not anyone_verified):
        r.agent = r.requested            # the one asked has it (verified, or nobody verified it yet)
    else:
        r.agent = ranked[0]              # the best-proven holder
    r.verified = _rank(who[r.agent])[1]
    r.alternatives = [a for a in ranked if a != r.agent]
    ext = who[r.agent][0]
    status = "verificado" if r.verified else f"{ext.state.replace('_', ' ')} (ainda não testado)"
    r.reason = f"{AGENTS[r.agent]} tem “{ext.name}” ({ext.kind}, {status})."
    if r.redirect:
        r.reason += f" {AGENTS[r.requested]} não tem — a tarefa pode ir para {AGENTS[r.agent]}."
    return r


def context(registry, agent: str, limit: int = 12) -> str:
    """Short capability list for the prompt: what this assistant and the other one really have."""
    lines = []
    for a, label in AGENTS.items():
        exts = [e for e in registry.all(include_removed=False) if e.provider == a and e.kind == "mcp"
                and not set(e.flags) & {"desabilitado", "removido", "requer_aprovacao"}]
        exts.sort(key=lambda e: -e.level())
        if not exts:
            continue
        items = []
        for e in exts[:limit]:
            st = "verificado" if e.usable() else "configurado, não testado" if e.level() < 4 else e.state.replace("_", " ")
            if "requer_login" in e.flags:
                st = "precisa de login"
            items.append(f"{e.name} ({st})")
        who = "VOCÊ" if a == agent else label
        lines.append(f"- {who} ({'Codex' if a == 'codex' else 'Claude Code'}): " + ", ".join(items))
    if not lines:
        return ""
    other = AGENTS["claude" if agent == "codex" else "codex"]
    return ("FERRAMENTAS EXTRAS (MCPs) DETECTADAS PELO KAGUYA STUDIO — só use as suas; não invente ferramentas:\n"
            + "\n".join(lines)
            + f"\nSe precisar de uma que só {other} tem, NÃO tente usá-la: escreva no fim da resposta "
              f"[[DELEGAR:{other.lower()}: o que ela deve fazer, com arquivos e critérios]] e o Studio repassa o pedido.")


def delegations(text: str) -> list[tuple[str, str]]:
    return [(BY_NAME[m.group(1).lower()], " ".join(m.group(2).split())[:2000]) for m in DELEGATE.finditer(text or "")]


# --------------------------------------------------------------------------- shared resources (3D files, apps)
class ResourceLocks:
    def __init__(self):
        self._held: dict[str, str] = {}
        self._lock = threading.Lock()

    def acquire(self, resources: list[str], owner: str) -> str | None:
        """Take all or none. Returns the conflicting resource (and its owner) when busy."""
        with self._lock:
            for r in resources:
                if self._held.get(r) not in (None, owner):
                    return f"{r} (em uso por {self._held[r]})"
            for r in resources:
                self._held[r] = owner
        return None

    def release(self, owner: str):
        with self._lock:
            for r in [r for r, o in self._held.items() if o == owner]:
                self._held.pop(r)

    def held(self) -> dict[str, str]:
        with self._lock:
            return dict(self._held)


def resources_for(text: str, project_dir: str, registry=None) -> tuple[list[str], list[Path]]:
    """(lock keys, existing 3D files to back up) mentioned by a task."""
    keys, files = [], []
    found = re.findall(r'"([^"\n]+\.(?:blend|bbmodel))"', text or "", re.I)        # quoted (may have spaces)
    found += re.findall(r'(?<!["\w])((?:[A-Za-z]:)?[\w\-./\\]+\.(?:blend|bbmodel))\b', text or "", re.I)
    for raw in found:
        raw = raw.strip()
        p = Path(raw) if Path(raw).is_absolute() else Path(project_dir) / raw
        try:
            p = p.resolve()
        except OSError:
            continue
        keys.append("arquivo:" + str(p).lower())
        if p.is_file():
            files.append(p)
    if registry is not None:
        for cap in mentioned(text, registry):
            app = {"blender": "Blender", "blockbench": "Blockbench"}.get(cap)
            if app:
                keys.append("app:" + app)
    for ext, app in APP_FILES.items():
        if any(k.endswith(ext) for k in keys):
            keys.append("app:" + app)
    return sorted(set(keys)), files


def backup(files: list[Path], dest_root: Path) -> list[Path]:
    out = []
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for f in files:
        d = Path(dest_root) / stamp
        d.mkdir(parents=True, exist_ok=True)
        target = d / f.name
        shutil.copy2(f, target)
        out.append(target)
    return out
