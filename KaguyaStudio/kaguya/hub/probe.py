"""Capability checks through official means, with minimal permissions and no tool ever executed.

* Claude Code MCP  → ``claude mcp get <name>`` (the official health check), in the project folder for project/local
  servers. Its output prints env values in clear text: only the status line is kept.
* Codex MCP / tool list → MCP handshake (initialize + tools/list) with the command the client itself is configured to
  run. Metadata only: tools are LISTED, never CALLED. Env values are read from the client's file at that moment, passed
  to the child process and never stored or shown.
* Claude plugin → ``claude plugin details <id>`` (components: skills, agents, hooks, MCPs).
* Real sessions (Registry.record_session) are the strongest evidence and need no extra call.
If the CLI is missing, the answer says so — never a false success.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time

from . import redact
from .adapters import _json, _toml
from .model import Extension

FLAGS_WIN = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _run(cmd: list[str], cwd: str | None = None, timeout: float = 60) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                           cwd=cwd if cwd and Path(cwd).is_dir() else None, creationflags=FLAGS_WIN,
                           stdin=subprocess.DEVNULL)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return -1, "tempo esgotado"
    except OSError as exc:
        return -2, str(exc)


def parse_status(text: str) -> str:
    m = re.search(r"Status:\s*(.+)", text or "")
    s = (m.group(1) if m else text or "").lower()
    if "connected" in s and "not" not in s and "fail" not in s:
        return "connected"
    if "auth" in s:
        return "needs-auth"
    if "pending" in s or "approval" in s:
        return "pending"
    if "disabled" in s:
        return "disabled"
    if "fail" in s or "error" in s or "✗" in s:
        return "failed"
    return "unknown"


def raw_mcp_spec(ext: Extension) -> dict | None:
    """Re-read the server definition from the client's own file, only for the duration of a check."""
    src = Path(ext.source)
    if src.suffix == ".toml":
        data, _ = _toml(src)
        return ((data or {}).get("mcp_servers") or {}).get(ext.name)
    data, _ = _json(src)
    if not isinstance(data, dict):
        return None
    if ext.scope == "local":
        proj = (data.get("projects") or {}).get(ext.project) or {}
        return (proj.get("mcpServers") or {}).get(ext.name)
    return (data.get("mcpServers") or {}).get(ext.name)


def handshake(spec: dict, timeout: float = 25, cwd: str | None = None) -> dict:
    """initialize + tools/list over stdio. Returns {"ok", "server", "tools", "error"}; never calls a tool."""
    if not spec or not spec.get("command"):
        return {"ok": False, "error": "sem comando local (servidor remoto: use o teste oficial do cliente)"}
    cmd = [shutil.which(spec["command"]) or spec["command"], *[str(a) for a in spec.get("args") or []]]
    env = dict(os.environ)
    env.update({str(k): str(v) for k, v in (spec.get("env") or {}).items()})
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, encoding="utf-8", errors="replace", env=env, creationflags=FLAGS_WIN,
                                cwd=spec.get("cwd") or (cwd if cwd and Path(cwd).is_dir() else None))
    except OSError as exc:
        return {"ok": False, "error": f"não foi possível iniciar: {exc}"}
    replies: dict = {}

    def reader():
        for line in proc.stdout:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if isinstance(msg, dict) and msg.get("id") is not None:
                replies[msg["id"]] = msg
    t = threading.Thread(target=reader, daemon=True)
    t.start()
    try:
        def send(obj):
            proc.stdin.write(json.dumps(obj) + "\n")
            proc.stdin.flush()
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "kaguya-studio-hub", "version": "1"}}})
        end = time.monotonic() + timeout
        while 1 not in replies and time.monotonic() < end and proc.poll() is None:
            time.sleep(0.05)
        if 1 not in replies:
            return {"ok": False, "error": "o servidor não respondeu ao initialize" if proc.poll() is None
                    else f"o servidor encerrou (código {proc.returncode})"}
        init = replies[1]
        if "error" in init:
            return {"ok": False, "error": redact.value(str(init["error"]))[:200]}
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        while 2 not in replies and time.monotonic() < end:
            time.sleep(0.05)
        info = (init.get("result") or {}).get("serverInfo") or {}
        tools = [str(t.get("name")) for t in ((replies.get(2) or {}).get("result") or {}).get("tools", [])
                 if isinstance(t, dict)]
        return {"ok": True, "server": f"{info.get('name', '?')} {info.get('version', '')}".strip(), "tools": tools,
                "listed": 2 in replies}
    finally:
        try:
            proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(3)
        try:
            proc.stdout.close()
        except OSError:
            pass


class Prober:
    def __init__(self, registry, exes=lambda: {}):
        self.registry = registry
        self.exes = exes

    def _exe(self, provider: str) -> str | None:
        return (self.exes() or {}).get(provider) or shutil.which(provider)

    def test(self, ext_id: str, list_tools: bool = False) -> dict:
        ext = self.registry.get(ext_id)
        if ext is None:
            return {"ok": False, "evidence": "extensão não encontrada"}
        if "removido" in ext.flags:
            return {"ok": False, "evidence": "removida da configuração do cliente"}
        if ext.provider == "web":
            self.registry.update_checked(ext.id, None, add_flags={"somente_web"},
                                         evidence="só existe na web: a CLI e o Studio não têm acesso a ela")
            return {"ok": False, "evidence": "só na web"}
        if ext.kind == "mcp":
            return self._mcp(ext, list_tools)
        if ext.kind == "plugin" and ext.provider == "claude":
            return self._claude_plugin(ext)
        if ext.kind in ("skill", "agent", "command"):
            ok = Path(ext.source).is_file()
            ev = "arquivo presente e legível; o cliente carrega ao abrir a sessão" if ok else "arquivo não encontrado"
            self.registry.update_checked(ext.id, None, add_flags=set() if ok else {"falha"},
                                         drop_flags={"falha"} if ok else set(), evidence=ev)
            return {"ok": ok, "evidence": ev}
        if ext.kind == "hook":
            ev = "hooks não são executados pelo Hub (eles rodam comandos no seu PC); revise o comando mostrado"
            self.registry.update_checked(ext.id, None, evidence=ev)
            return {"ok": True, "evidence": ev}
        return {"ok": False, "evidence": "sem teste disponível para este tipo"}

    def _mcp(self, ext: Extension, list_tools: bool) -> dict:
        if ext.provider == "claude" and ext.scope != "plugin":
            exe = self._exe("claude")
            if not exe:
                self.registry.update_checked(ext.id, None, add_flags={"indisponivel"},
                                             evidence="Claude Code não encontrado neste PC: não foi possível testar")
                return {"ok": False, "evidence": "Claude Code não encontrado"}
            code, out = _run([exe, "mcp", "get", ext.name], cwd=ext.project or None)
            status = parse_status(out)
            line = next((l.strip() for l in out.splitlines() if "Status:" in l), status)
            when = time.strftime("%d/%m %H:%M")
            if status == "connected":
                result = {"ok": True, "evidence": f"claude mcp get ({when}): {line}"}
                state, add, drop = "conectado", set(), {"falha", "requer_login", "indisponivel", "requer_aprovacao"}
            elif status == "needs-auth":
                result = {"ok": False, "evidence": f"claude mcp get ({when}): precisa de login — rode “claude mcp login "
                                                   f"{ext.name}” (o Hub não toca em credenciais)"}
                state, add, drop = None, {"requer_login"}, {"indisponivel"}
            elif status == "pending":
                result = {"ok": False, "evidence": f"claude mcp get ({when}): aguardando sua aprovação no Claude Code"}
                state, add, drop = None, {"requer_aprovacao"}, set()
            else:
                result = {"ok": False, "evidence": f"claude mcp get ({when}): {redact.value(line)[:160] or 'falhou'}"}
                state, add, drop = None, {"falha"}, {"indisponivel"}
            tools = None
            if result["ok"] and list_tools:
                hs = handshake(raw_mcp_spec(ext) or {}, cwd=ext.project or None)
                if hs.get("ok"):
                    tools = hs["tools"]
                    state = "capacidade_verificada" if tools else state
                    result["evidence"] += f"; {len(tools)} ferramenta(s) listadas pelo próprio servidor (nenhuma executada)"
            self.registry.update_checked(ext.id, state, add_flags=add, drop_flags=drop, tools=tools,
                                         evidence=result["evidence"])
            result["tools"] = tools or ext.tools
            return result
        spec = raw_mcp_spec(ext)
        if spec is None and ext.scope == "plugin":
            return {"ok": False, "evidence": "servidor de plugin: verificado pela sessão real do cliente"}
        if spec and not spec.get("command"):
            ev = "servidor remoto: o teste precisa do login do próprio cliente; abra uma sessão para confirmar"
            self.registry.update_checked(ext.id, None, evidence=ev)
            return {"ok": False, "evidence": ev}
        hs = handshake(spec or {}, cwd=ext.project or None)
        when = time.strftime("%d/%m %H:%M")
        if hs.get("ok"):
            tools = hs.get("tools") or []
            ev = (f"handshake MCP ({when}): {hs.get('server')} respondeu; {len(tools)} ferramenta(s) listadas "
                  "(nenhuma executada)")
            self.registry.update_checked(ext.id, "capacidade_verificada" if tools else "conectado",
                                         drop_flags={"falha", "indisponivel"}, tools=tools, evidence=ev)
            return {"ok": True, "evidence": ev, "tools": tools}
        ev = f"handshake MCP ({when}): {hs.get('error')}"
        self.registry.update_checked(ext.id, None, add_flags={"falha"}, evidence=ev)
        return {"ok": False, "evidence": ev}

    def _claude_plugin(self, ext: Extension) -> dict:
        exe = self._exe("claude")
        if not exe:
            self.registry.update_checked(ext.id, None, add_flags={"indisponivel"},
                                         evidence="Claude Code não encontrado: não foi possível consultar o plugin")
            return {"ok": False, "evidence": "Claude Code não encontrado"}
        code, out = _run([exe, "plugin", "details", ext.name])
        if code != 0:
            ev = f"claude plugin details: {redact.value(out.strip())[-160:]}"
            self.registry.update_checked(ext.id, None, add_flags={"falha"}, evidence=ev)
            return {"ok": False, "evidence": ev}
        comps = dict(re.findall(r"^\s+(Skills|Agents|Hooks|MCP servers|LSP servers)\s+\((\d+)\)", out, re.M))
        names = re.findall(r"^\s+Skills \(\d+\)\s+(.+)$", out, re.M)
        ev = "claude plugin details: " + ", ".join(f"{k} {v}" for k, v in comps.items())
        self.registry.update_checked(ext.id, None, drop_flags={"falha", "indisponivel"}, evidence=ev,
                                     tools=[n.strip() for n in names[0].split(",")] if names else None)
        return {"ok": True, "evidence": ev}
