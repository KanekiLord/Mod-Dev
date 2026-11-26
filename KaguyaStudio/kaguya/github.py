"""GitHub integration through the official GitHub CLI (``gh``) and Git.

* Login is done by ``gh auth login`` (browser) — the Studio never reads, stores or prints tokens
  (``--show-token`` is never used);
* every remote action (publish, push, pull, pull request) runs only when the user clicks it;
  agents are still forbidden to commit/push on their own;
* new repositories are **private** by default.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import subprocess

from .cli.discovery import find_cli
from .env import redact
from . import procutil

INSTALL_HINT = ("Instale a GitHub CLI: no PowerShell rode 'winget install --id GitHub.cli' (ou baixe em cli.github.com), "
                "feche e reabra o Studio.")


def _flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _run(cmd: list[str], cwd: str | Path | None = None, timeout: int = 120, env: dict | None = None) -> subprocess.CompletedProcess:
    run_env = dict(os.environ if env is None else env)
    run_env["GH_PROMPT_DISABLED"] = "1"   # never wait for interactive input
    run_env["GIT_TERMINAL_PROMPT"] = "0"
    run_env["NO_COLOR"] = "1"
    return procutil.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, env=run_env, stdin=subprocess.DEVNULL, creationflags=_flags())


def _out(p: subprocess.CompletedProcess) -> str:
    return redact(((p.stdout or "") + "\n" + (p.stderr or "")).strip())


@dataclass
class GhStatus:
    state: str = "nao_instalado"     # nao_instalado | nao_autenticado | pronto | erro
    executable: str | None = None
    version: str = ""
    login: str = ""
    protocol: str = ""
    details: list[str] = field(default_factory=list)
    fixes: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.state == "pronto"

    @property
    def label(self) -> str:
        return {"nao_instalado": "Não instalado", "nao_autenticado": "Não autenticado", "pronto": "Pronto",
                "erro": "Erro"}.get(self.state, self.state)


def diagnose(override: str | None = None, env: dict | None = None) -> GhStatus:
    st = GhStatus()
    exe, how = find_cli("gh", override, env)
    if not exe:
        st.details.append("GitHub CLI (gh) " + how + ".")
        st.fixes.append(INSTALL_HINT)
        return st
    st.executable = exe
    try:
        v = _run([exe, "--version"], timeout=30, env=env)
        st.version = (v.stdout or "").splitlines()[0].strip() if v.stdout else ""
        a = _run([exe, "auth", "status", "--json", "hosts"], timeout=30, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        st.state = "erro"
        st.details.append(f"Falha ao executar gh: {exc}")
        return st
    try:
        hosts = (json.loads(a.stdout or "{}").get("hosts") or {})
    except ValueError:
        hosts = None
    if hosts is None:  # very old gh without --json
        text = _out(a).lower()
        if "logged in to github.com" in text:
            st.state = "pronto"
            m = re.search(r"account ([\w-]+)", _out(a))
            st.login = m.group(1) if m else ""
        else:
            st.state = "nao_autenticado"
    else:
        accounts = hosts.get("github.com") or []
        active = next((x for x in accounts if x.get("active")), accounts[0] if accounts else None)
        if active and active.get("state") == "success":
            st.state = "pronto"
            st.login = str(active.get("login") or "")
            st.protocol = str(active.get("gitProtocol") or "")
        elif active:
            st.state = "nao_autenticado"
            st.details.append("O login salvo no gh não é válido: " + str(active.get("error") or "erro")[:200])
        else:
            st.state = "nao_autenticado"
    if st.state == "pronto":
        st.details.append(f"Conectado ao GitHub como {st.login or '?'}" + (f" (git via {st.protocol})" if st.protocol else "") + ".")
    else:
        st.details.append("A GitHub CLI não está conectada à sua conta.")
        st.fixes.append("Clique em 'Entrar no GitHub' (abre 'gh auth login --web' no terminal) e autorize no navegador.")
    return st


def login_command(exe: str) -> list[str]:
    return [exe, "auth", "login", "--hostname", "github.com", "--web", "--git-protocol", "https"]


@dataclass
class RepoStatus:
    is_git: bool = False
    root: str = ""
    branch: str = ""
    remote_url: str = ""
    github_repo: str = ""        # owner/name when the remote is on github.com
    web_url: str = ""
    has_commits: bool = False
    changed: int = 0
    ahead: int | None = None
    behind: int | None = None
    message: str = ""


_GH_URL = re.compile(r"github\.com[:/]+([^/\s]+)/([^/\s]+?)(?:\.git)?/?$")


def repo_status(folder: str | Path, fetch: bool = False, env: dict | None = None) -> RepoStatus:
    rs = RepoStatus()
    try:
        top = _run(["git", "rev-parse", "--show-toplevel"], folder, 20, env)
    except (OSError, subprocess.TimeoutExpired):
        rs.message = "Git não encontrado."
        return rs
    if top.returncode != 0:
        rs.message = "A pasta não é um repositório Git."
        return rs
    rs.is_git, rs.root = True, top.stdout.strip()
    rs.branch = _run(["git", "branch", "--show-current"], folder, 20, env).stdout.strip()
    rs.has_commits = _run(["git", "rev-parse", "--verify", "HEAD"], folder, 20, env).returncode == 0
    rs.changed = len([l for l in _run(["git", "status", "--porcelain"], folder, 60, env).stdout.splitlines() if l.strip()])
    # raw configured URL (``get-url`` would apply insteadOf rewrites and hide the github.com address)
    url = _run(["git", "config", "--get", "remote.origin.url"], folder, 20, env)
    if url.returncode == 0:
        rs.remote_url = url.stdout.strip()
        m = _GH_URL.search(rs.remote_url)
        if m:
            rs.github_repo = f"{m.group(1)}/{m.group(2)}"
            rs.web_url = f"https://github.com/{rs.github_repo}"
        if fetch:
            _run(["git", "fetch", "--quiet", "origin"], folder, 120, env)
        if rs.branch and rs.has_commits:
            cnt = _run(["git", "rev-list", "--left-right", "--count", f"origin/{rs.branch}...HEAD"], folder, 30, env)
            if cnt.returncode == 0 and cnt.stdout.split():
                behind, ahead = cnt.stdout.split()[:2]
                rs.behind, rs.ahead = int(behind), int(ahead)
    return rs


@dataclass
class ActionResult:
    ok: bool
    message: str
    url: str = ""


def suggest_repo_name(folder: str | Path) -> str:
    name = Path(folder).name.strip()
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.") or "meu-projeto"
    return name[:90]


def commit_all(folder: str | Path, message: str, env: dict | None = None) -> ActionResult:
    message = message.strip() or "Atualização"
    add = _run(["git", "add", "-A"], folder, 300, env)
    if add.returncode != 0:
        return ActionResult(False, "git add falhou: " + _out(add)[:400])
    c = _run(["git", "commit", "-m", message], folder, 300, env)
    out = _out(c)
    if c.returncode != 0:
        if "nothing to commit" in out or "nada a submeter" in out:
            return ActionResult(True, "Nada novo para salvar: tudo já está no último commit.")
        if "Please tell me who you are" in out:
            return ActionResult(False, "Configure seu nome/e-mail do Git (botão 'Criar repositório Git' mostra os campos) "
                                       "ou rode: git config --global user.name \"Seu Nome\"")
        return ActionResult(False, "commit falhou: " + out[:400])
    return ActionResult(True, "Versão salva (commit): " + message[:80])


def publish(folder: str | Path, gh: str, name: str, private: bool = True, description: str = "",
            env: dict | None = None) -> ActionResult:
    rs = repo_status(folder, env=env)
    if not rs.is_git:
        return ActionResult(False, "Crie primeiro o repositório Git do projeto.")
    if rs.remote_url:
        return ActionResult(False, f"O projeto já tem um repositório remoto: {rs.remote_url}")
    cmd = [gh, "repo", "create", name, "--private" if private else "--public", "--source", str(folder), "--remote", "origin"]
    if description.strip():
        cmd += ["--description", description.strip()[:300]]
    if rs.has_commits:
        cmd.append("--push")
    p = _run(cmd, folder, 300, env)
    out = _out(p)
    if p.returncode != 0:
        if "Name already exists" in out or "already exists" in out:
            return ActionResult(False, f"Já existe um repositório '{name}' na sua conta. Escolha outro nome.")
        return ActionResult(False, "gh repo create falhou: " + out[:500])
    url = next((l.strip() for l in (p.stdout or "").splitlines() if l.strip().startswith("https://github.com/")), "")
    msg = "Publicado no GitHub como repositório " + ("privado" if private else "público") + "."
    if not rs.has_commits:
        msg += " Ainda não havia commits: use 'Salvar versão' e depois 'Enviar'."
    return ActionResult(True, msg, url or repo_status(folder, env=env).web_url)


def push(folder: str | Path, env: dict | None = None) -> ActionResult:
    rs = repo_status(folder, env=env)
    if not rs.remote_url:
        return ActionResult(False, "Sem repositório remoto: use 'Publicar no GitHub'.")
    if not rs.has_commits:
        return ActionResult(False, "Nada para enviar: faça 'Salvar versão' primeiro.")
    p = _run(["git", "push", "-u", "origin", rs.branch or "HEAD"], folder, 600, env)
    out = _out(p)
    if p.returncode != 0:
        if "rejected" in out or "non-fast-forward" in out or "fetch first" in out:
            return ActionResult(False, "O GitHub tem alterações que você não tem. Use 'Atualizar do GitHub' antes de enviar.")
        if "Authentication failed" in out or "could not read Username" in out:
            return ActionResult(False, "Falha de autenticação no Git. Em Diagnóstico › GitHub clique em 'Entrar no GitHub' "
                                       "(o gh configura o Git automaticamente).")
        return ActionResult(False, "git push falhou: " + out[:500])
    return ActionResult(True, f"Enviado para o GitHub ({rs.branch}).", rs.web_url)


def pull(folder: str | Path, env: dict | None = None) -> ActionResult:
    rs = repo_status(folder, env=env)
    if not rs.remote_url:
        return ActionResult(False, "Sem repositório remoto.")
    if rs.changed:
        return ActionResult(False, f"Há {rs.changed} arquivo(s) alterado(s) sem commit. Salve uma versão antes de atualizar.")
    p = _run(["git", "pull", "--ff-only", "origin", rs.branch or "HEAD"], folder, 600, env)
    out = _out(p)
    if p.returncode != 0:
        if "Not possible to fast-forward" in out or "diverg" in out:
            return ActionResult(False, "Seu projeto e o GitHub divergiram. Resolva manualmente (merge/rebase); o Studio não "
                                       "faz merge às cegas.")
        return ActionResult(False, "git pull falhou: " + out[:500])
    return ActionResult(True, "Atualizado a partir do GitHub." if "Already up to date" not in out else "Já estava atualizado.")


def create_pr(folder: str | Path, gh: str, title: str = "", body: str = "", env: dict | None = None) -> ActionResult:
    rs = repo_status(folder, env=env)
    if not rs.github_repo:
        return ActionResult(False, "O projeto não está publicado no GitHub.")
    pushed = push(folder, env=env)
    if not pushed.ok:
        return pushed
    cmd = [gh, "pr", "create", "--head", rs.branch]
    cmd += ["--title", title, "--body", body or "Criado pelo Kaguya Studio."] if title.strip() else ["--fill"]
    p = _run(cmd, folder, 300, env)
    out = _out(p)
    if p.returncode != 0:
        if "already exists" in out:
            return ActionResult(False, "Já existe um pull request aberto para este ramo.")
        if "No commits between" in out:
            return ActionResult(False, "Este ramo não tem diferenças em relação ao ramo principal.")
        return ActionResult(False, "gh pr create falhou: " + out[:500])
    url = next((l.strip() for l in (p.stdout or "").splitlines() if "/pull/" in l), "")
    return ActionResult(True, "Pull request criado.", url)
