"""Discover the agents, skills, plugins and MCP servers that are *really* installed and
reconcile them with the historical catalogue of 72 agents.

Read-only. Only names/descriptions/model/tools are read from front-matter; MCP and plugin
files are reduced to server/plugin *names* (env, headers, args and tokens are never read
out). A catalogued agent counts as available only when its file is found.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
import json
import os
from pathlib import Path
import re

try:
    import tomllib
except ImportError:  # Python < 3.11
    tomllib = None


@dataclass
class AgentInfo:
    name: str
    scope: str          # projeto | global | vault | codex
    path: str
    description: str = ""
    model: str = ""
    tools: str = ""
    catalog_project: str = ""
    catalog_group: str = ""
    catalog_parent: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Inventory:
    agents: list[AgentInfo] = field(default_factory=list)
    skills: list[dict] = field(default_factory=list)
    plugins: list[str] = field(default_factory=list)
    mcp_servers: list[dict] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)
    catalog_total: int = 0
    catalog_found: list[str] = field(default_factory=list)
    catalog_missing: list[str] = field(default_factory=list)
    not_in_catalog: list[str] = field(default_factory=list)
    scanned: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["agents"] = [a.to_dict() for a in self.agents]
        return data


FM = re.compile(r"^---\s*\n(.*?)\n---", re.S)


def _front_matter(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")[:6000]
    except OSError:
        return {}
    m = FM.match(text)
    if not m:
        return {}
    data = {}
    for line in m.group(1).splitlines():
        mm = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", line)
        if mm:
            data[mm.group(1).lower()] = mm.group(2).strip().strip('"').strip("'")
    return data


def load_catalog(path: Path) -> list[dict]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return [x for x in data if isinstance(x, dict) and x.get("nome")]
    except (OSError, ValueError):
        return []


def _agent_dirs(project: Path | None, vault: Path | None, home: Path) -> list[tuple[str, Path]]:
    dirs = []
    if project:
        dirs.append(("projeto", project / ".claude" / "agents"))
    if vault:
        dirs.append(("vault", vault / ".claude" / "agents"))
    dirs.append(("global", home / ".claude" / "agents"))
    return dirs


def _mcp_names(file: Path, scope: str) -> list[dict]:
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(servers, dict):
        return []
    return [{"name": n, "scope": scope, "type": (v or {}).get("type", "stdio") if isinstance(v, dict) else "?"}
            for n, v in servers.items()]


def scan(project: Path | None, vault: Path | None, catalog: Path, home: Path | None = None) -> Inventory:
    home = Path(home or Path.home())
    inv = Inventory()
    cat = load_catalog(catalog)
    by_name = {c["nome"]: c for c in cat}
    inv.catalog_total = len(cat)
    seen = set()
    for scope, d in _agent_dirs(Path(project) if project else None, Path(vault) if vault else None, home):
        inv.scanned.append(str(d))
        if not d.is_dir():
            continue
        for f in sorted(d.rglob("*.md")):
            if f.is_symlink():
                continue
            fm = _front_matter(f)
            name = fm.get("name") or f.stem
            key = (scope, name)
            if key in seen:
                continue
            seen.add(key)
            c = by_name.get(name, {})
            inv.agents.append(AgentInfo(name=name, scope=scope, path=str(f), description=fm.get("description", "")[:300],
                                        model=fm.get("model", ""), tools=fm.get("tools", "")[:200],
                                        catalog_project=c.get("projeto", ""), catalog_group=c.get("grupo", ""),
                                        catalog_parent=c.get("pai", "")))
    codex_agents = home / ".codex" / "agents"
    if codex_agents.is_dir():
        for f in sorted(codex_agents.glob("*.toml")):
            inv.agents.append(AgentInfo(name=f.stem, scope="codex", path=str(f)))
    names = {a.name for a in inv.agents}
    inv.catalog_found = sorted(n for n in by_name if n in names)
    inv.catalog_missing = sorted(n for n in by_name if n not in names)
    inv.not_in_catalog = sorted(n for n in names if n not in by_name)
    # skills
    skill_dirs = []
    if project:
        skill_dirs += [("projeto", Path(project) / ".claude" / "skills"), ("projeto/agents", Path(project) / ".agents" / "skills")]
    if vault:
        skill_dirs.append(("vault", Path(vault) / ".claude" / "skills"))
    skill_dirs += [("global", home / ".claude" / "skills"), ("codex", home / ".codex" / "skills")]
    for scope, d in skill_dirs:
        if not d.is_dir():
            continue
        for sk in sorted(p for p in d.iterdir() if p.is_dir()):
            md = sk / "SKILL.md"
            if md.is_file():
                fm = _front_matter(md)
                inv.skills.append({"name": fm.get("name") or sk.name, "scope": scope,
                                   "description": fm.get("description", "")[:240], "path": str(md)})
    # plugins (names only)
    reg = home / ".claude" / "plugins" / "installed_plugins.json"
    if reg.is_file():
        try:
            data = json.loads(reg.read_text(encoding="utf-8"))
            plugins = data.get("plugins", data) if isinstance(data, dict) else {}
            inv.plugins = sorted(str(k) for k in plugins)[:300] if isinstance(plugins, dict) else []
        except (OSError, ValueError):
            pass
    # MCP servers (names only)
    if project:
        inv.mcp_servers += _mcp_names(Path(project) / ".mcp.json", "projeto")
    inv.mcp_servers += _mcp_names(home / ".claude.json", "global")
    codex_cfg = home / ".codex" / "config.toml"
    if tomllib and codex_cfg.is_file():
        try:
            cfg = tomllib.loads(codex_cfg.read_text(encoding="utf-8"))
            for n in (cfg.get("mcp_servers") or {}):
                inv.mcp_servers.append({"name": n, "scope": "codex", "type": "config.toml"})
        except (OSError, ValueError):
            pass
    for base, label in ((project, "projeto"), (vault, "vault")):
        if base:
            for fname in ("CLAUDE.md", "AGENTS.md", "MEMORY.md"):
                if (Path(base) / fname).is_file():
                    inv.instructions.append(f"{label}/{fname}")
    return inv


ROLE_KEYWORDS = {
    "explorar": ("explorador", "explorer", "auxiliar-logs", "deps-analista"),
    "revisar": ("revisor", "reviewer", "caca-erros", "deps-api"),
    "julgar": ("juiz", "judge"),
    "pesquisar": ("pesquisa", "curador", "research"),
    "registrar": ("registro", "integrador-cerebro", "categorizador", "memoria"),
    "planejar": ("planejamento", "coordenador"),
}


def suggest_agents(inv: Inventory, roles: list[str], project_hint: str = "", limit: int = 4) -> list[str]:
    """Pick at most ``limit`` *installed* agents for the requested roles (economy first)."""
    chosen = []
    hint = project_hint.lower().replace(" ", "")
    pool = sorted(inv.agents, key=lambda a: (0 if hint and hint in (a.name + a.catalog_project).lower().replace(" ", "") else 1,
                                             a.name))
    for role in roles:
        for a in pool:
            if a.name in chosen:
                continue
            if any(k in a.name.lower() for k in ROLE_KEYWORDS.get(role, ())):
                chosen.append(a.name)
                break
        if len(chosen) >= limit:
            break
    return chosen
