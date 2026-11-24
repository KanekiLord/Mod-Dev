"""Find, version and diagnose the official Codex and Claude Code CLIs.

Windows causes addressed (see docs/AUDITORIA.md):
* GUI apps started from Explorer often have a PATH without ``%APPDATA%\\npm`` or
  ``%USERPROFILE%\\.local\\bin`` (native Claude installer) -> extra known locations are
  searched and the user can pick the executable manually;
* ``.ps1`` shims are never chosen (they cannot be executed by CreateProcess);
* login is verified with the CLIs' own commands and reported per state, with the exact
  reason and a fix, instead of a generic "não verificado";
* capabilities (flags) are detected from ``--help`` so older/newer CLI versions don't
  receive flags they don't understand.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Callable

from ..env import child_env, redact

TARGETS = ("codex", "claude")

# States shown in the UI (briefing §6).
NOT_INSTALLED = "nao_instalado"
FOUND = "encontrado"
NOT_AUTHENTICATED = "nao_autenticado"
AUTHENTICATED = "autenticado"
NO_PERMISSION = "sem_permissao"
READY = "pronto"
RUNNING = "em_execucao"
LIMIT = "limite"
ERROR = "erro"

STATE_LABELS = {
    NOT_INSTALLED: "Não instalado", FOUND: "Encontrado", NOT_AUTHENTICATED: "Não autenticado",
    AUTHENTICATED: "Autenticado", NO_PERMISSION: "Sem permissão", READY: "Pronto",
    RUNNING: "Em execução", LIMIT: "Limite alcançado", ERROR: "Erro",
}

INSTALL_HINTS = {
    "codex": "Instale com: npm install -g @openai/codex  (requer Node.js 18+). Depois rode 'codex login' e escolha 'Sign in with ChatGPT'.",
    "claude": "Instale pelo instalador oficial do Claude Code (claude.ai/install) ou: npm install -g @anthropic-ai/claude-code. Depois rode 'claude' e faça /login com sua conta Claude (Pro/Max).",
}
LOGIN_COMMANDS = {"codex": ["login"], "claude": ["auth", "login"]}


def _no_window() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def candidate_dirs(env: dict[str, str] | None = None) -> list[Path]:
    env = dict(os.environ if env is None else env)
    home = Path(env.get("USERPROFILE") or env.get("HOME") or Path.home())
    dirs: list[Path] = []
    if os.name == "nt":
        for var, sub in (("APPDATA", "npm"), ("LOCALAPPDATA", "pnpm"), ("LOCALAPPDATA", "Programs\\claude"),
                         ("LOCALAPPDATA", "Microsoft\\WindowsApps"), ("ProgramFiles", "nodejs"),
                         ("NVM_SYMLINK", ""), ("VOLTA_HOME", "bin")):
            if env.get(var):
                dirs.append(Path(env[var]) / sub if sub else Path(env[var]))
        dirs += [home / ".local" / "bin", home / ".bun" / "bin", home / "scoop" / "shims",
                 home / "AppData" / "Roaming" / "npm"]
    else:
        dirs += [home / ".local" / "bin", home / ".npm-global" / "bin", home / ".bun" / "bin",
                 home / ".volta" / "bin", Path("/usr/local/bin"), Path("/opt/homebrew/bin"), home / ".claude" / "local"]
    seen, unique = set(), []
    for d in dirs:
        key = str(d).lower()
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique


def _windows_exts() -> list[str]:
    return [".exe", ".cmd", ".bat", ".com"]


def find_cli(name: str, override: str | None = None, env: dict[str, str] | None = None) -> tuple[str | None, str]:
    """Return (absolute path, how it was found)."""
    if override:
        p = Path(override.strip().strip('"'))
        if p.is_file() and p.suffix.lower() != ".ps1":
            return str(p.resolve()), "definido manualmente"
        return None, f"caminho manual inválido: {override}"
    env = dict(os.environ if env is None else env)
    found = shutil.which(name, path=env.get("PATH"))
    if found and not found.lower().endswith(".ps1"):
        return str(Path(found)), "PATH"
    for d in candidate_dirs(env):
        exts = _windows_exts() if os.name == "nt" else [""]
        for ext in exts:
            p = d / f"{name}{ext}"
            if p.is_file() and (os.name == "nt" or os.access(p, os.X_OK)):
                return str(p), f"local conhecido ({d})"
    return None, "não encontrado no PATH nem nos locais padrão"


@dataclass
class Capabilities:
    version: str = ""
    flags: set[str] = field(default_factory=set)
    words: set[str] = field(default_factory=set)

    def has(self, flag: str) -> bool:
        return flag in self.flags

    def mentions(self, word: str) -> bool:
        return word in self.words

    def to_dict(self) -> dict:
        return {"version": self.version, "flags": sorted(self.flags), "words": sorted(self.words)}

    @classmethod
    def from_dict(cls, data: dict) -> "Capabilities":
        return cls(version=data.get("version", ""), flags=set(data.get("flags", [])), words=set(data.get("words", [])))


_FLAG = re.compile(r"(?<![\w-])(--[a-zA-Z][\w-]*|-[a-zA-Z])\b")
_KNOWN_WORDS = ("stream-json", "dontAsk", "acceptEdits", "plan", "resume", "read-only", "workspace-write",
                "app-server", "auth", "status")


def parse_capabilities(version: str, *help_texts: str) -> Capabilities:
    text = "\n".join(help_texts)
    caps = Capabilities(version=version.strip())
    caps.flags = set(_FLAG.findall(text))
    caps.words = {w for w in _KNOWN_WORDS if re.search(r"(?<![\w-])" + re.escape(w) + r"(?![\w-])", text)}
    return caps


@dataclass
class Diagnosis:
    target: str
    state: str = ERROR
    executable: str | None = None
    found_by: str = ""
    version: str = ""
    auth_method: str = ""
    plan: str = ""
    details: list[str] = field(default_factory=list)
    fixes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    removed_env: list[str] = field(default_factory=list)
    capabilities: dict = field(default_factory=dict)
    checked_at: str = ""

    @property
    def label(self) -> str:
        return STATE_LABELS.get(self.state, self.state)

    @property
    def usable(self) -> bool:
        return self.state in (READY, AUTHENTICATED)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["label"] = self.label
        return data

    def report(self) -> str:
        lines = [f"{self.target.upper()}: {self.label}"]
        if self.executable:
            lines.append(f"  Executável: {self.executable} ({self.found_by})")
        if self.version:
            lines.append(f"  Versão: {self.version}")
        if self.auth_method:
            lines.append(f"  Login: {self.auth_method}" + (f" — plano {self.plan}" if self.plan else ""))
        lines += [f"  • {d}" for d in self.details]
        lines += [f"  ⚠ {w}" for w in self.warnings]
        lines += [f"  → {f}" for f in self.fixes]
        return "\n".join(lines)


Runner = Callable[..., subprocess.CompletedProcess]


def _run(runner: Runner, cmd: list[str], cwd: str | None, timeout: float, env: dict) -> subprocess.CompletedProcess:
    return runner(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                  encoding="utf-8", errors="replace", timeout=timeout, creationflags=_no_window())


def git_bash_available(env: dict[str, str] | None = None) -> bool:
    env = dict(os.environ if env is None else env)
    if env.get("CLAUDE_CODE_GIT_BASH_PATH") and Path(env["CLAUDE_CODE_GIT_BASH_PATH"]).is_file():
        return True
    for base in (env.get("ProgramFiles"), env.get("ProgramFiles(x86)"), env.get("LOCALAPPDATA") and
                 str(Path(env["LOCALAPPDATA"]) / "Programs")):
        if base and (Path(base) / "Git" / "bin" / "bash.exe").is_file():
            return True
    git = shutil.which("git", path=env.get("PATH"))
    return bool(git and (Path(git).parent.parent / "bin" / "bash.exe").is_file())


def diagnose(target: str, cwd: str | None = None, override: str | None = None, *,
             runner: Runner = subprocess.run, env: dict[str, str] | None = None,
             timeout: float = 45) -> tuple[Diagnosis, Capabilities]:
    if target not in TARGETS:
        raise ValueError("CLI desconhecida")
    diag = Diagnosis(target=target, checked_at=datetime.now().astimezone().isoformat(timespec="seconds"))
    caps = Capabilities()
    base_env = dict(os.environ if env is None else env)
    run_env, removed = child_env(base_env)
    diag.removed_env = removed
    if removed:
        diag.warnings.append("Variáveis ignoradas para não usar API faturada/outro provedor: " + ", ".join(removed))
    exe, how = find_cli(target, override, base_env)
    diag.executable, diag.found_by = exe, how
    if not exe:
        diag.state = NOT_INSTALLED
        diag.details.append(f"'{target}' {how}.")
        diag.fixes.append(INSTALL_HINTS[target])
        diag.fixes.append("Se já está instalado, informe o executável em Configurações › CLIs (ex.: %APPDATA%\\npm\\" +
                          target + ".cmd ou %USERPROFILE%\\.local\\bin\\" + target + ".exe).")
        return diag, caps
    cwd = cwd if cwd and Path(cwd).is_dir() else None
    # ---- version
    try:
        res = _run(runner, [exe, "--version"], cwd, timeout, run_env)
        out = (res.stdout or res.stderr or "").strip()
        if res.returncode != 0:
            diag.state = ERROR
            diag.details.append(f"'{target} --version' terminou com código {res.returncode}: {redact(out)[:400]}")
            if os.name == "nt" and "node" in out.lower():
                diag.fixes.append("O Node.js não foi encontrado pelo launcher .cmd. Reinstale o Node.js LTS e reabra o Studio.")
            return diag, caps
        diag.version = out.splitlines()[0][:120] if out else "?"
        diag.state = FOUND
    except FileNotFoundError:
        diag.state = NOT_INSTALLED
        diag.details.append(f"O arquivo {exe} não pôde ser executado.")
        diag.fixes.append(INSTALL_HINTS[target])
        return diag, caps
    except PermissionError:
        diag.state = NO_PERMISSION
        diag.details.append(f"Sem permissão para executar {exe} (antivírus/política do Windows?).")
        return diag, caps
    except subprocess.TimeoutExpired:
        diag.state = ERROR
        diag.details.append(f"'{target} --version' não respondeu em {int(timeout)}s (antivírus verificando ou primeira execução).")
        diag.fixes.append("Tente novamente; se persistir, rode o comando num terminal para ver a mensagem.")
        return diag, caps
    except OSError as exc:
        diag.state = ERROR
        diag.details.append(f"Falha ao executar {exe}: {exc}")
        return diag, caps
    # ---- capabilities
    helps = []
    help_cmds = [[exe, "--help"]]
    help_cmds.append([exe, "exec", "--help"] if target == "codex" else [exe, "auth", "status", "--help"])
    for cmd in help_cmds:
        try:
            res = _run(runner, cmd, cwd, timeout, run_env)
            helps.append((res.stdout or "") + "\n" + (res.stderr or ""))
        except (OSError, subprocess.TimeoutExpired):
            pass
    caps = parse_capabilities(diag.version, *helps)
    diag.capabilities = caps.to_dict()
    # ---- login
    if target == "claude":
        _claude_login(diag, exe, cwd, runner, run_env, timeout, caps)
        if os.name == "nt" and not git_bash_available(base_env):
            diag.warnings.append("Git for Windows (git-bash) não encontrado. O Claude Code no Windows precisa dele para "
                                 "executar comandos.")
            diag.fixes.append("Instale o Git for Windows ou defina CLAUDE_CODE_GIT_BASH_PATH apontando para bash.exe.")
    else:
        _codex_login(diag, exe, cwd, runner, run_env, timeout)
        if caps.flags and "--json" not in caps.flags:
            diag.warnings.append("Esta versão do Codex não oferece 'exec --json'; o Studio usará saída de texto. Atualize com 'npm i -g @openai/codex'.")
    if diag.state == AUTHENTICATED:
        missing = _missing_flags(target, caps)
        if missing:
            diag.warnings.append("Recursos ausentes nesta versão: " + ", ".join(missing) + ". Atualize a CLI para melhor integração.")
        diag.state = READY
        diag.details.append("Pronto para tarefas. Um teste real (opcional) envia uma mensagem mínima pela assinatura.")
    return diag, caps


def _missing_flags(target: str, caps: Capabilities) -> list[str]:
    wanted = {"claude": ["--output-format", "--permission-mode", "--allowedTools", "--resume", "--verbose"],
              "codex": ["--json", "--sandbox", "--skip-git-repo-check"]}[target]
    if not caps.flags:
        return []
    return [w for w in wanted if w not in caps.flags]


def _claude_login(diag: Diagnosis, exe: str, cwd, runner, env, timeout, caps: Capabilities) -> None:
    try:
        res = _run(runner, [exe, "auth", "status", "--json"], cwd, timeout, env)
    except subprocess.TimeoutExpired:
        diag.state = ERROR
        diag.details.append("'claude auth status' não respondeu a tempo.")
        return
    except OSError as exc:
        diag.state = ERROR
        diag.details.append(f"Falha ao consultar login: {exc}")
        return
    text = (res.stdout or "").strip()
    data = None
    try:
        start = text.find("{")
        data = json.loads(text[start:]) if start >= 0 else None
    except ValueError:
        data = None
    if data is None:
        combined = (text + "\n" + (res.stderr or "")).lower()
        if "unknown command" in combined or "error: unknown" in combined or "too many arguments" in combined:
            diag.state = FOUND
            diag.details.append("Esta versão do Claude Code não tem 'claude auth status'.")
            diag.fixes.append("Atualize o Claude Code ('claude update' ou reinstale) para o Studio confirmar o login.")
        else:
            diag.state = ERROR
            diag.details.append("Resposta inesperada de 'claude auth status': " + redact(combined)[:300])
        return
    method = str(data.get("authMethod") or "none")
    provider = str(data.get("apiProvider") or "firstParty")
    diag.auth_method = method
    diag.plan = str(data.get("subscriptionType") or data.get("planTier") or "")
    if not data.get("loggedIn") or method == "none":
        diag.state = NOT_AUTHENTICATED
        diag.details.append("O Claude Code não está logado nesta conta do Windows.")
        diag.fixes.append("Clique em 'Entrar' (abre um terminal com 'claude auth login') e entre com sua conta Claude Pro/Max.")
        return
    if provider != "firstParty" or method == "third_party":
        diag.state = NO_PERMISSION
        diag.details.append(f"Configurado para outro provedor ({provider}); isso pode gerar cobrança fora da assinatura.")
        diag.fixes.append("Remova CLAUDE_CODE_USE_BEDROCK/VERTEX/FOUNDRY das configurações (settings.json → env) e faça /login.")
        return
    if method in ("api_key", "api_key_helper") or data.get("apiKeySource"):
        diag.state = NO_PERMISSION
        diag.details.append("O Claude Code está usando API key (cobrança por uso), não a assinatura.")
        diag.fixes.append("Rode 'claude auth logout' e depois 'claude auth login' escolhendo a conta Claude (assinatura). "
                          "Verifique também 'env' em %USERPROFILE%\\.claude\\settings.json.")
        return
    if method in ("claude.ai", "oauth_token", "oauth"):
        diag.state = AUTHENTICATED
        diag.details.append("Login por assinatura Claude confirmado pelo próprio Claude Code" +
                            (f" (plano {diag.plan})." if diag.plan else "."))
        return
    diag.state = FOUND
    diag.details.append(f"Método de login não reconhecido: {method}.")


def _codex_login(diag: Diagnosis, exe: str, cwd, runner, env, timeout) -> None:
    try:
        res = _run(runner, [exe, "login", "status"], cwd, timeout, env)
    except subprocess.TimeoutExpired:
        diag.state = ERROR
        diag.details.append("'codex login status' não respondeu a tempo.")
        return
    except OSError as exc:
        diag.state = ERROR
        diag.details.append(f"Falha ao consultar login: {exc}")
        return
    # Codex prints the status on stderr.
    out = ((res.stdout or "") + "\n" + (res.stderr or "")).strip()
    low = out.lower()
    if "not logged in" in low or (res.returncode != 0 and "logged in" not in low):
        diag.state = NOT_AUTHENTICATED
        diag.auth_method = "nenhum"
        diag.details.append("O Codex não está logado nesta conta do Windows.")
        diag.fixes.append("Clique em 'Entrar' (abre 'codex login') e escolha 'Sign in with ChatGPT'.")
        return
    if "api key" in low:
        diag.state = NO_PERMISSION
        diag.auth_method = "API key"
        diag.details.append("O Codex está logado com API key (cobrança por uso), não com o ChatGPT.")
        diag.fixes.append("Rode 'codex logout' e depois 'codex login' escolhendo 'Sign in with ChatGPT'.")
        return
    if "chatgpt" in low:
        diag.state = AUTHENTICATED
        diag.auth_method = "ChatGPT"
        diag.details.append("Login ChatGPT confirmado pelo próprio Codex.")
        return
    if "access token" in low or "logged in" in low:
        diag.state = AUTHENTICATED
        diag.auth_method = "token de acesso"
        diag.details.append("Codex logado (" + redact(out.splitlines()[0])[:120] + ").")
        return
    diag.state = ERROR
    diag.details.append("Resposta inesperada de 'codex login status': " + redact(out)[:300])


def open_login_terminal(target: str, executable: str, cwd: str | None = None) -> None:
    """Open a visible console running the official login command (the user types there)."""
    args = [executable, *LOGIN_COMMANDS[target]]
    if os.name == "nt":
        subprocess.Popen(["cmd.exe", "/k", subprocess.list2cmdline(args)], cwd=cwd,
                         creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    else:
        for term in (["x-terminal-emulator", "-e"], ["gnome-terminal", "--"], ["xterm", "-e"],
                     ["open", "-a", "Terminal"]):
            if shutil.which(term[0]):
                subprocess.Popen([*term, *args], cwd=cwd)
                return
        raise RuntimeError("Nenhum terminal encontrado; rode manualmente: " + " ".join(args))


def open_interactive(target: str, executable: str, cwd: str | None = None) -> None:
    """Open the interactive CLI (for /status in Codex or /usage in Claude)."""
    if os.name == "nt":
        subprocess.Popen(["cmd.exe", "/k", subprocess.list2cmdline([executable])], cwd=cwd,
                         creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    else:
        for term in (["x-terminal-emulator", "-e"], ["gnome-terminal", "--"], ["xterm", "-e"]):
            if shutil.which(term[0]):
                subprocess.Popen([*term, executable], cwd=cwd)
                return
        raise RuntimeError(f"Abra um terminal e rode: {executable}")
