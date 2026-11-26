"""Install / enable / disable / remove — only through the official CLIs, only after the user approves the exact plan.

A plan shows: the command that will run (secrets masked), where it lands (client + scope), a security review (origin,
permissions, costs, secrets, scripts that download code), conflicts, and how to undo it. ``apply`` refuses to run a
plan that was not approved, or that changed after approval. Secret values typed by the user only travel to the
official CLI (stdin for Claude Code) — never to disk, logs or the catalogue.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid

from . import redact
from .adapters import PAID, permissions_for
from .. import procutil

RISKY_LAUNCHERS = {"npx": "baixa e executa um pacote do npm", "uvx": "baixa e executa um pacote do PyPI",
                   "pipx": "baixa e executa um pacote do PyPI", "bunx": "baixa e executa um pacote",
                   "docker": "executa um contêiner", "dnx": "baixa e executa um pacote .NET"}


@dataclass
class ChangePlan:
    kind: str                     # install-mcp | remove-mcp | enable-plugin | disable-plugin | install-plugin | uninstall-plugin
    provider: str
    name: str
    scope: str
    project: str = ""
    display: str = ""             # command shown to the user (secrets masked)
    changes: list[str] = field(default_factory=list)
    review: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    rollback: str = ""
    status: str = "proposta"      # proposta | aprovada | executada | falhou | recusada
    approved: bool = False
    executed: bool = False
    approval_id: str = ""
    plan_hash: str = ""
    result: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    _cmd: list[str] = field(default_factory=list, repr=False)
    _stdin: str = field(default="", repr=False)
    _cwd: str = field(default="", repr=False)

    def public(self) -> dict:
        d = {k: v for k, v in asdict(self).items() if not k.startswith("_")}
        return json.loads(redact.value(json.dumps(d, ensure_ascii=False)))

    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps([self.kind, self.provider, self.name, self.scope, self.project, self._cmd,
                                          self._stdin], ensure_ascii=False).encode("utf-8")).hexdigest()[:24]


def _exe(provider: str, exes: dict) -> str:
    exe = (exes or {}).get(provider) or shutil.which(provider)
    if not exe:
        raise RuntimeError(f"{provider} não encontrado neste PC: instale/abra o cliente oficial primeiro")
    return exe


def review_for(name: str, command: str, args: list[str], url: str, env: dict, origin: str) -> tuple[dict, list[str]]:
    perms, details = permissions_for(name, f"{command} {' '.join(args)} {url}", "http" if url else "stdio")
    warnings = []
    launcher = Path(command or "").stem.lower()
    scripts = RISKY_LAUNCHERS.get(launcher, "")
    if scripts:
        warnings.append(f"“{launcher}” {scripts} — confira a origem antes de aprovar")
    if re.search(r"curl|wget|iwr|invoke-webrequest", f"{command} {' '.join(args)}", re.I):
        warnings.append("o comando baixa algo da internet")
    if details.get("custo"):
        warnings.append(details["custo"] + " — usar só com sua confirmação a cada uso que gaste")
    review = {"origem": origin or "não informada (confira antes de aprovar)",
              "permissoes": perms or ["nenhuma óbvia pelo nome/comando (não é garantia)"],
              "custos": details.get("custo", "nenhum serviço pago reconhecido (não é garantia)"),
              "segredos": [f"{k} (valor guardado só pelo cliente oficial)" for k in sorted(env)] or ["nenhum"],
              "scripts": scripts or "nenhum lançador que baixe código"}
    if not origin:
        warnings.append("origem não informada")
    return review, warnings


class Lifecycle:
    def __init__(self, registry, data_dir: Path, exes=lambda: {}, rescan=None, runner=None):
        self.registry = registry
        self.dir = Path(data_dir) / "hub" / "planos"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.exes = exes
        self.rescan = rescan
        self.runner = runner or self._run

    # ------------------------------------------------------------------ plans
    def plan_install_mcp(self, provider: str, name: str, scope: str, *, project: str = "", command: str = "",
                         args: list[str] | None = None, url: str = "", env: dict | None = None,
                         origin: str = "") -> ChangePlan:
        if not re.fullmatch(r"[A-Za-z0-9_.\-]{1,64}", name or ""):
            raise ValueError("Nome do servidor: só letras, números, ponto, hífen e sublinhado")
        if bool(command) == bool(url):
            raise ValueError("Informe um comando (servidor local) OU uma URL (servidor remoto)")
        if provider not in ("claude", "codex"):
            raise ValueError("Cliente desconhecido")
        if provider == "codex" and scope != "user":
            raise ValueError("O Codex instala MCPs no escopo do usuário (config.toml)")
        if scope in ("project", "local") and not (project and Path(project).is_dir()):
            raise ValueError("Escolha a pasta do projeto para o escopo de projeto")
        args, env = [str(a) for a in args or []], {str(k): str(v) for k, v in (env or {}).items()}
        exe = _exe(provider, self.exes())
        plan = ChangePlan(kind="install-mcp", provider=provider, name=name, scope=scope, project=project)
        plan.review, plan.warnings = review_for(name, command, args, url, env, origin)
        dup = [e for e in self.registry.all(include_removed=False)
               if e.provider == provider and e.kind == "mcp" and e.name == name
               and (e.scope == scope or scope == "user" or e.scope == "user")
               and (not project or not e.project or e.project == project)]
        if dup:
            raise ValueError(f"Já existe um MCP “{name}” no {provider} ({dup[0].scope}): remova ou escolha outro nome")
        ports = set(re.findall(r"(?:--port[= ]|:)(\d{2,5})\b", f"{' '.join(args)} {url}"))
        for e in self.registry.all(include_removed=False):
            if e.kind == "mcp" and ports & set(re.findall(r"(?:--port[= ]|:)(\d{2,5})\b", e.command)):
                plan.warnings.append(f"a porta {', '.join(sorted(ports))} também aparece em “{e.name}” ({e.provider})")
        if provider == "claude":
            spec = {"type": "http", "url": url} if url else {"type": "stdio", "command": command, "args": args}
            if env and not url:
                spec["env"] = env
            if env:   # secrets go through stdin: they never appear in the process list
                plan._cmd = [exe, "mcp", "add-json", name, "-", "-s", scope]
                plan._stdin = json.dumps(spec)
            else:
                plan._cmd = [exe, "mcp", "add-json", name, json.dumps(spec), "-s", scope]
            plan._cwd = project
            shown = dict(spec)
            if "env" in shown:
                shown["env"] = {k: "***" for k in shown["env"]}
            if "url" in shown:
                shown["url"] = redact.url(shown["url"])
            if "args" in shown:
                shown["args"] = redact.args(shown["args"])
            plan.display = (f"claude mcp add-json {name} - -s {scope}   (configuração pela entrada padrão: "
                            f"{json.dumps(shown, ensure_ascii=False)})" if env else
                            f"claude mcp add-json {name} '{json.dumps(shown, ensure_ascii=False)}' -s {scope}")
            plan.rollback = f"claude mcp remove {name} -s {scope}"
        else:
            cmd = [exe, "mcp", "add", name]
            for k, v in env.items():
                cmd += ["--env", f"{k}={v}"]
            cmd += ["--url", url] if url else ["--", command, *args]
            plan._cmd = cmd
            plan.display = "codex mcp add " + name + "".join(f" --env {k}=***" for k in env) + \
                           (f" --url {redact.url(url)}" if url else f" -- {redact.command_line(command, args)}")
            plan.rollback = f"codex mcp remove {name}"
            if env:
                plan.warnings.append("os valores de --env passam pela linha de comando do Codex (ferramenta oficial)")
        where = {"user": "todas as sessões deste usuário", "project": "o projeto (arquivo .mcp.json, compartilhável)",
                 "local": "só este projeto, só para você"}.get(scope, scope)
        plan.changes = [f"Adicionar o MCP “{name}” ao {('Claude Code (Miwa)' if provider == 'claude' else 'Codex (Kaguya)')}"
                        f" — vale para {where}",
                        "Nada é instalado na outra IA (ela pode pedir o trabalho a esta, pelo Studio)",
                        "Depois: o Hub relê a configuração e você pode testar a conexão"]
        return self._store(plan)

    def plan_remove(self, ext_id: str) -> ChangePlan:
        ext = self.registry.get(ext_id)
        if ext is None or "removido" in ext.flags:
            raise ValueError("Extensão não encontrada")
        exe = _exe(ext.provider, self.exes())
        if ext.kind == "mcp" and ext.scope in ("user", "project", "local") and not ext.parent:
            plan = ChangePlan(kind="remove-mcp", provider=ext.provider, name=ext.name, scope=ext.scope, project=ext.project)
            if ext.provider == "claude":
                plan._cmd, plan._cwd = [exe, "mcp", "remove", ext.name, "-s", ext.scope], ext.project
                plan.display = f"claude mcp remove {ext.name} -s {ext.scope}"
            else:
                plan._cmd = [exe, "mcp", "remove", ext.name]
                plan.display = f"codex mcp remove {ext.name}"
            plan.rollback = "Reinstalar pelo Hub (valores secretos precisarão ser digitados de novo)"
        elif ext.kind == "plugin" and ext.provider == "claude" and ext.scope != "builtin":
            plan = ChangePlan(kind="uninstall-plugin", provider="claude", name=ext.name, scope=ext.scope)
            plan._cmd = [exe, "plugin", "uninstall", ext.name, "-s", ext.scope]
            plan.display = f"claude plugin uninstall {ext.name} -s {ext.scope}"
            plan.rollback = f"claude plugin install {ext.name} -s {ext.scope}"
        elif ext.kind == "plugin" and ext.provider == "codex":
            plan = ChangePlan(kind="uninstall-plugin", provider="codex", name=ext.name, scope=ext.scope)
            plan._cmd = [exe, "plugin", "remove", ext.name]
            plan.display = f"codex plugin remove {ext.name}"
            plan.rollback = f"codex plugin add {ext.name}"
        else:
            raise ValueError("Este item não é removido pelo Hub (veja a configuração original)")
        plan.changes = [f"Remover “{ext.name}” do {ext.provider} ({ext.scope})", "O histórico fica no Hub"]
        plan.review = {"origem": ext.source, "permissoes": ext.permissions, "custos": ext.details.get("custo", ""),
                       "segredos": ext.env_keys, "scripts": ""}
        return self._store(plan)

    def plan_toggle_plugin(self, ext_id: str, enable: bool) -> ChangePlan:
        ext = self.registry.get(ext_id)
        if ext is None or ext.kind != "plugin" or ext.provider != "claude":
            raise ValueError("Só plugins do Claude Code são ativados/desativados pelo Hub")
        exe = _exe("claude", self.exes())
        verb = "enable" if enable else "disable"
        scope = "user" if ext.scope == "builtin" else ext.scope
        plan = ChangePlan(kind=f"{verb}-plugin", provider="claude", name=ext.name, scope=scope)
        plan._cmd = [exe, "plugin", verb, ext.name, "-s", scope]
        plan.display = f"claude plugin {verb} {ext.name} -s {scope}"
        plan.rollback = f"claude plugin {'disable' if enable else 'enable'} {ext.name} -s {scope}"
        plan.changes = [f"{'Ativar' if enable else 'Desativar'} o plugin “{ext.name}”",
                        "Vale nas próximas sessões do Claude Code (sessões abertas precisam reiniciar)"]
        plan.review = {"origem": ext.details.get("marketplace", ""), "permissoes": ext.permissions,
                       "custos": ext.details.get("custo", ""), "segredos": [], "scripts": ""}
        return self._store(plan)

    def _store(self, plan: ChangePlan) -> ChangePlan:
        plan.plan_hash = plan.fingerprint()
        (self.dir / f"{plan.id}.json").write_text(json.dumps(plan.public(), ensure_ascii=False, indent=1),
                                                 encoding="utf-8")
        return plan

    # ------------------------------------------------------------------ approval + execution
    def approve(self, plan: ChangePlan, reviewed: bool) -> str:
        if not reviewed:
            raise PermissionError("Confirme que revisou origem, permissões e custos")
        plan.approved, plan.status = True, "aprovada"
        plan.approval_id = uuid.uuid4().hex[:16]
        plan.plan_hash = plan.fingerprint()
        self._store(plan)
        return plan.approval_id

    def apply(self, plan: ChangePlan, approval_id: str) -> ChangePlan:
        if not plan.approved or not approval_id or approval_id != plan.approval_id:
            raise PermissionError("Este plano não foi aprovado pelo usuário")
        if plan.fingerprint() != plan.plan_hash:
            raise PermissionError("O plano mudou depois da aprovação: aprove de novo")
        code, out = self.runner(plan._cmd, plan._stdin, plan._cwd)
        plan.executed = code == 0
        plan.status = "executada" if plan.executed else "falhou"
        plan.result = redact.value(out.strip())[-500:]
        if not plan.executed and "inside a Claude Code session" in out:
            plan.result = ("O Claude Code recusou receber segredos pela entrada porque o Studio foi aberto de dentro de "
                           "uma sessão do Claude Code (proteção oficial). Abra o Studio normalmente e tente de novo.")
        plan._stdin = ""                              # secret values leave memory with the plan
        self._store(plan)
        with self.registry._db() as db:
            self.registry.audit(db, f"{plan.provider}:{plan.kind}:{plan.scope}:{plan.name}", plan.provider, plan.scope,
                                plan.kind, "", plan.status, actor="usuário", approval=approval_id,
                                summary=f"{plan.display} → {plan.result[-200:]}")
        if self.rescan:
            self.rescan()
        return plan

    @staticmethod
    def _run(cmd: list[str], stdin: str, cwd: str) -> tuple[int, str]:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        try:
            p = procutil.run(cmd, input=stdin or None, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=180, cwd=cwd if cwd and Path(cwd).is_dir() else None,
                               creationflags=flags)
            return p.returncode, (p.stdout or "") + (p.stderr or "")
        except (OSError, subprocess.TimeoutExpired) as exc:
            return -1, str(exc)

    def plans(self, limit: int = 50) -> list[dict]:
        files = sorted(self.dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
        out = []
        for f in files:
            try:
                out.append(json.loads(f.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return out


assert PAID and time
