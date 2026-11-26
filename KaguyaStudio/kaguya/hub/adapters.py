"""Provider adapters: what Claude Code and Codex have, read from their own official files and read-only listings.

Nothing here writes anything or starts an MCP server. A file that cannot be parsed (being written, broken) is
reported as a problem of that source and its previous items are KEPT by the registry — never "removed" by accident.
Each future provider gets its own adapter; patterns are not assumed to carry over.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from . import redact
from .model import Extension
from .. import procutil

try:
    import tomllib
except ImportError:  # pragma: no cover
    tomllib = None

PAID = {"elevenlabs": "ElevenLabs", "openai": "OpenAI API", "anthropic": "Anthropic API", "replicate": "Replicate",
        "stability": "Stability AI", "runway": "Runway", "heygen": "HeyGen", "suno": "Suno", "deepgram": "Deepgram",
        "assemblyai": "AssemblyAI", "perplexity": "Perplexity API", "firecrawl": "Firecrawl", "serpapi": "SerpAPI"}
APPS = {"blender": "Blender", "blockbench": "Blockbench", "unity": "Unity", "photoshop": "Photoshop", "obsidian": "Obsidian",
        "figma": "Figma", "godot": "Godot", "krita": "Krita", "minecraft": "Minecraft"}


def permissions_for(name: str, command: str, transport: str) -> tuple[list[str], dict]:
    """What it can touch (best effort from name/command; shown to the user as risk, never as proof)."""
    low = f"{name} {command}".lower()
    perms, details = [], {}
    for k, app in APPS.items():
        if k in low:
            perms.append(f"controla o {app} (precisa dele aberto)")
            details["app"] = app
    if re.search(r"file|filesystem|\bfs\b|disk|folder", low):
        perms.append("lê/escreve arquivos")
    if re.search(r"shell|terminal|exec|bash|powershell|cmd\b|command", low):
        perms.append("executa comandos")
    if re.search(r"playwright|puppeteer|browser|chrome|selenium", low):
        perms.append("controla um navegador")
    if re.search(r"github|gitlab|git\b", low):
        perms.append("acessa repositórios/conta Git")
    if re.search(r"slack|gmail|mail|whatsapp|telegram|discord|outlook", low):
        perms.append("lê/envia mensagens de uma conta")
    if transport in ("http", "sse", "ws"):
        perms.append("rede (servidor remoto)")
    for k, svc in PAID.items():
        if k in low:
            details["custo"] = f"usa {svc}: pode consumir créditos/cobrança própria"
            perms.append("envia dados a serviço externo pago")
            break
    return perms, details


def _json(path: Path) -> tuple[dict | list | None, str]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return None, ""
    except OSError as exc:
        return None, f"não foi possível ler: {exc}"
    if not text.strip():
        return None, "arquivo vazio (pode estar sendo gravado)"
    try:
        return json.loads(text), ""
    except ValueError as exc:
        return None, f"JSON inválido ou sendo gravado ({exc.msg}, linha {exc.lineno})"


def _toml(path: Path) -> tuple[dict | None, str]:
    if tomllib is None or not path.is_file():
        return None, ""
    try:
        return tomllib.loads(path.read_text(encoding="utf-8-sig")), ""
    except (OSError, ValueError) as exc:
        return None, f"TOML inválido ou sendo gravado ({str(exc)[:120]})"


def _front(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")[:6000]
    except OSError:
        return {}
    m = re.match(r"\A---\s*\n(.*?)\n---", text, re.S)
    out = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line and not line.startswith((" ", "\t", "-")):
                k, v = line.split(":", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _mcp(provider: str, name: str, spec: dict, scope: str, source: Path, project: str = "", parent: str = "") -> Extension:
    spec = spec if isinstance(spec, dict) else {}
    url = spec.get("url") or spec.get("serverUrl") or ""
    transport = spec.get("type") or spec.get("transport") or ("http" if url else "stdio")
    command = redact.url(url) if url else redact.command_line(spec.get("command", ""), spec.get("args") or [])
    env_keys = sorted((spec.get("env") or {}).keys()) + sorted(f"header:{h}" for h in (spec.get("headers") or {}))
    if spec.get("bearer_token_env_var"):
        env_keys.append(f"token via variável {spec['bearer_token_env_var']}")
    perms, details = permissions_for(name, f"{spec.get('command', '')} {' '.join(map(str, spec.get('args') or []))} {url}",
                                     transport)
    ext = Extension(provider=provider, kind="mcp", name=name, scope=scope, source=str(source), project=project,
                    transport=transport, command=command, env_keys=env_keys, permissions=perms, parent=parent,
                    state="configurado", details=details,
                    evidence=f"configurado em {source.name}")
    if spec.get("enabled") is False or spec.get("disabled") is True:
        ext.flags.append("desabilitado")
    else:
        ext.state = "habilitado"
    return ext


def _markdown_items(provider: str, kind: str, base: Path, scope: str, project: str = "", parent: str = "") -> list[Extension]:
    out = []
    if not base.is_dir():
        return out
    pattern = "SKILL.md" if kind == "skill" else "*.md"
    for f in sorted(base.rglob(pattern)):
        if f.is_symlink() or any(p.startswith(".") for p in f.relative_to(base).parts[:-1]):
            continue
        fm = _front(f)
        name = fm.get("name") or (f.parent.name if kind == "skill" else f.stem)
        rel = f.relative_to(base).parent.as_posix()
        out.append(Extension(provider=provider, kind=kind, name=name, scope=scope, source=str(f), project=project,
                             description=redact.value(fm.get("description", ""))[:400], parent=parent,
                             state="habilitado", evidence=f"arquivo {f.name} (carregado automaticamente pelo cliente)",
                             details={"pasta": rel} if rel not in (".", "") else {}))
    return out


def _which(exe: str | None, name: str) -> str | None:
    return exe if exe and Path(exe).exists() else shutil.which(name)


def _run_json(cmd: list[str], timeout: float = 25):
    """Official read-only listing; returns (data, error)."""
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        p = procutil.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                           creationflags=flags, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"{Path(cmd[0]).name}: {exc}"
    if p.returncode != 0:
        return None, redact.value((p.stderr or p.stdout or "").strip()[-300:])
    try:
        return json.loads(p.stdout), ""
    except ValueError:
        return None, "saída não é JSON"


# --------------------------------------------------------------------------- Claude Code
class ClaudeAdapter:
    provider = "claude"

    def __init__(self, home: Path | None = None, exe: str | None = None, use_cli: bool = True):
        self.home = Path(home or Path.home())
        self.exe = exe
        self.use_cli = use_cli

    def sources(self, projects: list[str]) -> list[Path]:
        h = self.home
        out = [h / ".claude.json", h / ".claude" / "settings.json", h / ".claude" / "plugins" / "installed_plugins.json",
               h / ".claude" / "skills", h / ".claude" / "agents", h / ".claude" / "commands"]
        for p in projects:
            pp = Path(p)
            out += [pp / ".mcp.json", pp / ".claude" / "settings.json", pp / ".claude" / "settings.local.json",
                    pp / ".claude" / "skills", pp / ".claude" / "agents", pp / ".claude" / "commands"]
        return out

    def discover(self, projects: list[str]) -> tuple[list[Extension], list[tuple[str, str]]]:
        items, problems = [], []
        h = self.home
        cfg_path = h / ".claude.json"
        cfg, err = _json(cfg_path)
        if err:
            problems.append((str(cfg_path), err))
        cfg = cfg if isinstance(cfg, dict) else {}
        for name, spec in (cfg.get("mcpServers") or {}).items():
            items.append(_mcp("claude", name, spec, "user", cfg_path))
        user_settings, err = _json(h / ".claude" / "settings.json")
        if err:
            problems.append((str(h / ".claude" / "settings.json"), err))
        user_settings = user_settings if isinstance(user_settings, dict) else {}
        items += self._hooks(user_settings, "user", h / ".claude" / "settings.json")
        for p in projects:
            pp = Path(p)
            pcfg = ((cfg.get("projects") or {}).get(str(pp)) or (cfg.get("projects") or {}).get(pp.as_posix()) or {})
            for name, spec in (pcfg.get("mcpServers") or {}).items():
                items.append(_mcp("claude", name, spec, "local", cfg_path, project=str(pp)))
            local, err = _json(pp / ".claude" / "settings.local.json")
            if err:
                problems.append((str(pp / ".claude" / "settings.local.json"), err))
            local = local if isinstance(local, dict) else {}
            shared, err = _json(pp / ".claude" / "settings.json")
            if err:
                problems.append((str(pp / ".claude" / "settings.json"), err))
            shared = shared if isinstance(shared, dict) else {}
            approved = set(pcfg.get("enabledMcpjsonServers") or []) | set(local.get("enabledMcpjsonServers") or [])
            denied = set(pcfg.get("disabledMcpjsonServers") or []) | set(local.get("disabledMcpjsonServers") or [])
            allow_all = bool(pcfg.get("enableAllProjectMcpServers") or local.get("enableAllProjectMcpServers"))
            pj, err = _json(pp / ".mcp.json")
            if err:
                problems.append((str(pp / ".mcp.json"), err))
            for name, spec in ((pj or {}).get("mcpServers") or {}).items() if isinstance(pj, dict) else []:
                ext = _mcp("claude", name, spec, "project", pp / ".mcp.json", project=str(pp))
                if name in denied:
                    ext.state, ext.flags = "configurado", sorted(set(ext.flags) | {"desabilitado"})
                elif not (allow_all or name in approved):
                    ext.state = "configurado"
                    ext.flags.append("requer_aprovacao")
                    ext.evidence = "servidor do .mcp.json do projeto ainda não aprovado no Claude Code"
                items.append(ext)
            for kind, sub in (("skill", "skills"), ("agent", "agents"), ("command", "commands")):
                items += _markdown_items("claude", kind, pp / ".claude" / sub, "project", project=str(pp))
            items += self._hooks(shared, "project", pp / ".claude" / "settings.json", str(pp))
            items += self._hooks(local, "local", pp / ".claude" / "settings.local.json", str(pp))
        for kind, sub in (("skill", "skills"), ("agent", "agents"), ("command", "commands")):
            items += _markdown_items("claude", kind, h / ".claude" / sub, "user")
        plugins, perr = self._plugins(user_settings)
        items += plugins
        problems += perr
        return items, problems

    def _hooks(self, settings: dict, scope: str, source: Path, project: str = "") -> list[Extension]:
        out = []
        for event, entries in (settings.get("hooks") or {}).items() if isinstance(settings.get("hooks"), dict) else []:
            for entry in entries if isinstance(entries, list) else []:
                matcher = (entry or {}).get("matcher") or "*"
                for hk in (entry or {}).get("hooks") or []:
                    cmd = redact.value(str(hk.get("command", "")))
                    out.append(Extension(provider="claude", kind="hook", name=f"{event} [{matcher}]", scope=scope,
                                         source=str(source), project=project, command=cmd[:300], state="habilitado",
                                         permissions=["executa comandos no seu PC automaticamente"],
                                         evidence=f"definido em {source.name}",
                                         details={"evento": event, "tipo": hk.get("type", "command")}))
        return out

    def _plugins(self, user_settings: dict) -> tuple[list[Extension], list[tuple[str, str]]]:
        items, problems = [], []
        listed = None
        exe = _which(self.exe, "claude") if self.use_cli else None
        if exe:
            listed, err = _run_json([exe, "plugin", "list", "--json"])
            if err:
                problems.append(("claude plugin list --json", err))
        reg_path = self.home / ".claude" / "plugins" / "installed_plugins.json"
        reg, err = _json(reg_path)
        if err:
            problems.append((str(reg_path), err))
        installed = {}
        plugins = (reg or {}).get("plugins", reg) if isinstance(reg, dict) else {}
        for pid, entries in (plugins or {}).items() if isinstance(plugins, dict) else []:
            entry = entries[0] if isinstance(entries, list) and entries else entries if isinstance(entries, dict) else {}
            installed[pid] = entry or {}
        enabled_cfg = user_settings.get("enabledPlugins") or {}
        rows = listed if isinstance(listed, list) else [{"id": pid, "scope": e.get("scope", "user"),
                                                        "version": e.get("version", ""),
                                                        "enabled": enabled_cfg.get(pid, True)}
                                                       for pid, e in installed.items()]
        for row in rows:
            pid = str(row.get("id") or row.get("name") or "")
            if not pid:
                continue
            scope = "builtin" if pid.endswith("@builtin") else str(row.get("scope") or "user")
            entry = installed.get(pid, {})
            ext = Extension(provider="claude", kind="plugin", name=pid, scope=scope,
                            source="claude plugin list --json" if listed is not None else str(reg_path),
                            version=str(row.get("version") or entry.get("version") or ""),
                            state="habilitado" if row.get("enabled", True) else "configurado",
                            evidence=("listado pelo Claude Code (oficial)" if listed is not None
                                      else "arquivo de plugins instalados (CLI indisponível)"),
                            details={"marketplace": pid.split("@", 1)[1] if "@" in pid else ""})
            if not row.get("enabled", True):
                ext.flags.append("desabilitado")
            path = Path(entry.get("installPath", "")) if entry.get("installPath") else None
            if path and path.is_dir():
                manifest, _ = _json(path / ".claude-plugin" / "plugin.json")
                if isinstance(manifest, dict):
                    ext.description = redact.value(str(manifest.get("description", "")))[:400]
                    ext.version = ext.version if ext.version not in ("", "unknown") else str(manifest.get("version", ""))
                    ext.details["autor"] = redact.value(str((manifest.get("author") or {}).get("name", "")
                                                            if isinstance(manifest.get("author"), dict)
                                                            else manifest.get("author", "")))[:80]
                items += self._plugin_children(pid, path, manifest if isinstance(manifest, dict) else {})
            items.append(ext)
        return items, problems

    def _plugin_children(self, pid: str, path: Path, manifest: dict) -> list[Extension]:
        """Components a plugin brings: grouped under it, never counted as separate installs."""
        kids = []
        for kind, sub in (("skill", "skills"), ("agent", "agents"), ("command", "commands")):
            kids += _markdown_items("claude", kind, path / sub, "plugin", parent=pid)
        servers = dict(manifest.get("mcpServers") or {}) if isinstance(manifest.get("mcpServers"), dict) else {}
        pmcp, _ = _json(path / ".mcp.json")
        if isinstance(pmcp, dict):
            servers.update(pmcp.get("mcpServers") or {})
        for name, spec in servers.items():
            kids.append(_mcp("claude", name, spec, "plugin", path / ".mcp.json", parent=pid))
        hooks, _ = _json(path / "hooks" / "hooks.json")
        if isinstance(hooks, dict):
            kids += [Extension(**{**h.__dict__, "scope": "plugin", "parent": pid})
                     for h in self._hooks(hooks, "plugin", path / "hooks" / "hooks.json")]
        return kids


# --------------------------------------------------------------------------- Codex
class CodexAdapter:
    provider = "codex"

    def __init__(self, home: Path | None = None, exe: str | None = None, use_cli: bool = True):
        self.home = Path(home or Path.home())
        self.codex_home = Path(os.environ.get("CODEX_HOME") or self.home / ".codex") if home is None else self.home / ".codex"
        self.exe = exe
        self.use_cli = use_cli

    def sources(self, projects: list[str]) -> list[Path]:
        c = self.codex_home
        out = [c / "config.toml", c / "skills", c / "agents", self.home / ".agents" / "skills"]
        for p in projects:
            out += [Path(p) / ".codex" / "config.toml", Path(p) / ".agents" / "skills", Path(p) / ".codex" / "skills"]
        return out

    def discover(self, projects: list[str]) -> tuple[list[Extension], list[tuple[str, str]]]:
        items, problems = [], []
        c = self.codex_home
        cfg, err = _toml(c / "config.toml")
        if err:
            problems.append((str(c / "config.toml"), err))
        items += self._from_config(cfg or {}, "user", c / "config.toml")
        for p in projects:
            pc, err = _toml(Path(p) / ".codex" / "config.toml")
            if err:
                problems.append((str(Path(p) / ".codex" / "config.toml"), err))
            for ext in self._from_config(pc or {}, "project", Path(p) / ".codex" / "config.toml", str(p)):
                ext.evidence += " (o Codex só usa a configuração do projeto se ele estiver marcado como confiável)"
                items.append(ext)
            for base in (Path(p) / ".agents" / "skills", Path(p) / ".codex" / "skills"):
                items += _markdown_items("codex", "skill", base, "project", project=str(p))
        for base in (c / "skills", self.home / ".agents" / "skills"):
            items += _markdown_items("codex", "skill", base, "user")
        agents = c / "agents"
        if agents.is_dir():
            for f in sorted(agents.glob("*.toml")):
                data, err = _toml(f)
                items.append(Extension(provider="codex", kind="agent", name=(data or {}).get("name") or f.stem,
                                       scope="user", source=str(f), state="habilitado",
                                       description=redact.value(str((data or {}).get("description", "")))[:400],
                                       evidence="arquivo de agente do Codex"))
        exe = _which(self.exe, "codex") if self.use_cli else None
        if exe:
            # official listing adds what the file cannot say: login state and why a server is disabled
            servers, err = _run_json([exe, "mcp", "list", "--json"])
            if err:
                problems.append(("codex mcp list --json", err))
            for row in servers if isinstance(servers, list) else []:
                for ext in items:
                    if ext.kind == "mcp" and ext.scope == "user" and ext.name == row.get("name"):
                        auth = str(row.get("auth_status") or "").lower()
                        if auth in ("not_logged_in", "notloggedin", "logged_out", "required"):
                            ext.flags.append("requer_login")
                        if row.get("enabled") is False:
                            ext.flags = sorted(set(ext.flags) | {"desabilitado"})
                            ext.state = "configurado"
                            if row.get("disabled_reason"):
                                ext.details["motivo"] = redact.value(str(row["disabled_reason"]))[:200]
                        ext.details["login"] = auth or "?"
                        ext.evidence = "listado pelo Codex (oficial): codex mcp list"
            listed, err = _run_json([exe, "plugin", "list", "--json"])
            if err:
                problems.append(("codex plugin list --json", err))
            for row in (listed or {}).get("installed", []) if isinstance(listed, dict) else []:
                name = str(row.get("id") or row.get("name") or "")
                if name:
                    ext = Extension(provider="codex", kind="plugin", name=name, scope=str(row.get("scope") or "user"),
                                    source="codex plugin list --json", version=str(row.get("version") or ""),
                                    description=redact.value(str(row.get("description") or ""))[:400],
                                    state="habilitado" if row.get("enabled", True) else "configurado",
                                    evidence="listado pelo Codex (oficial)")
                    if row.get("enabled") is False:
                        ext.flags.append("desabilitado")
                    items.append(ext)
        return items, problems

    def _from_config(self, cfg: dict, scope: str, source: Path, project: str = "") -> list[Extension]:
        out = []
        for name, spec in (cfg.get("mcp_servers") or {}).items():
            out.append(_mcp("codex", name, spec, scope, source, project=project))
        if cfg.get("notify"):
            out.append(Extension(provider="codex", kind="hook", name="notify", scope=scope, source=str(source),
                                 project=project, command=redact.command_line(*(list(cfg["notify"])[:1] or [""]),
                                                                             list(cfg["notify"])[1:]),
                                 state="habilitado", permissions=["executa um programa ao fim de cada turno"],
                                 evidence="definido em config.toml"))
        return out


# --------------------------------------------------------------------------- web-only (registered by the user)
def web_only(name: str, surface: str, note: str = "") -> Extension:
    """A ChatGPT/Claude web connector or plugin: shown, never offered as usable from the CLI or the Studio."""
    return Extension(provider="web", kind="plugin", name=name, scope="web", source=surface, state="descoberto",
                     flags=["somente_web"], description=note,
                     evidence=f"existe em {surface}; a sessão da CLI não herda conexões da conta web")
