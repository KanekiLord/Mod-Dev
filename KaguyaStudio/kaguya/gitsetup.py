"""Create a Git repository for a project folder, safely (used by "Criar repositório Git").

* never overwrites an existing ``.gitignore`` (only creates one when absent);
* never touches an existing repository;
* the first commit only happens when the user asked for it, with the identity they gave;
* large/generated Minecraft folders (build/, run/, .gradle/…) are ignored so the first commit
  doesn't swallow worlds, logs or caches.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import shutil
import subprocess

GITIGNORE_MODS = """# Gerado pelo Kaguya Studio para projetos de mods (Gradle / Forge / Fabric / NeoForge)
# Builds e caches
build/
out/
bin/
.gradle/
classes/
*.class

# Execução local do Minecraft (mundos, logs, configs de teste)
run/
runs/
logs/
crash-reports/
*.log

# IDEs
.idea/
*.iml
*.ipr
*.iws
.vscode/
.classpath
.project
.settings/
*.launch

# Sistema
.DS_Store
Thumbs.db
desktop.ini

# Segredos (nunca versionar)
.env
*.keystore
"""


@dataclass
class GitSetupResult:
    ok: bool
    steps: list[str] = field(default_factory=list)
    error: str = ""


def _no_window() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _git(path: Path, *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(path), capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, creationflags=_no_window())


def git_available() -> bool:
    return shutil.which("git") is not None


def global_identity() -> tuple[str, str]:
    if not git_available():
        return "", ""
    def get(key):
        try:
            r = subprocess.run(["git", "config", "--global", key], capture_output=True, text=True, timeout=10,
                               creationflags=_no_window())
            return r.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            return ""
    return get("user.name"), get("user.email")


def init_repository(folder: Path, *, gitignore: bool = True, first_commit: bool = True,
                    name: str = "", email: str = "") -> GitSetupResult:
    folder = Path(folder)
    res = GitSetupResult(ok=False)
    if not git_available():
        res.error = "Git não está instalado. Instale o Git for Windows (git-scm.com) e reabra o Studio."
        return res
    if not folder.is_dir():
        res.error = f"Pasta não encontrada: {folder}"
        return res
    if (folder / ".git").exists():
        res.error = "Esta pasta já tem um repositório Git."
        return res
    r = _git(folder, "init")
    if r.returncode != 0:
        res.error = "git init falhou: " + (r.stderr or r.stdout).strip()[:400]
        return res
    res.steps.append("Repositório criado (git init).")
    _git(folder, "branch", "-M", "main")
    if gitignore:
        gi = folder / ".gitignore"
        if gi.exists():
            res.steps.append(".gitignore já existia — mantido sem alterações.")
        else:
            gi.write_text(GITIGNORE_MODS, encoding="utf-8")
            res.steps.append(".gitignore para mods criado (build, run, .gradle, logs, IDEs ignorados).")
    if first_commit:
        if name.strip() and email.strip():
            _git(folder, "config", "user.name", name.strip())
            _git(folder, "config", "user.email", email.strip())
            res.steps.append(f"Identidade dos commits deste projeto: {name.strip()} <{email.strip()}>.")
        add = _git(folder, "add", "-A", timeout=600)
        if add.returncode != 0:
            res.error = "git add falhou: " + (add.stderr or add.stdout).strip()[:400]
            return res
        commit = _git(folder, "commit", "-m", "Estado inicial (criado pelo Kaguya Studio)", timeout=600)
        if commit.returncode != 0:
            msg = (commit.stderr or commit.stdout).strip()
            if "nothing to commit" in msg or "nada a submeter" in msg:
                res.steps.append("Pasta vazia: nada para o commit inicial.")
            elif "Please tell me who you are" in msg or "user.email" in msg:
                res.error = ("O repositório foi criado, mas o commit inicial precisa do seu nome e e-mail do Git. "
                             "Preencha os campos e tente de novo, ou rode: git config --global user.name \"Seu Nome\"")
                res.ok = True
                return res
            else:
                res.error = "commit inicial falhou: " + msg[:400]
                res.ok = True
                return res
        else:
            count = _git(folder, "rev-list", "--count", "HEAD").stdout.strip()
            files = _git(folder, "ls-files").stdout.count("\n")
            res.steps.append(f"Commit inicial feito ({files} arquivos versionados, commit {count}).")
    res.ok = True
    return res
