"""Isolated Git worktrees for parallel work, plus supervised integration.

Each parallel worker edits its own worktree/branch, so two agents never edit the same file
at the same time. Integration is a separate, user-approved step that refuses to proceed
when the user has uncommitted changes and aborts cleanly on conflicts (no blind merge).
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess


def _git(repo: Path, *args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0)


def worktree_base(repo_root: Path) -> Path:
    return Path(repo_root).parent / f".{Path(repo_root).name}-kaguya-worktrees"


def create(repo_root: Path, task_id: int, index: int, agent: str) -> tuple[Path, str]:
    # a per-run suffix: a requeued task used to fail forever ("branch already exists")
    import secrets
    run = secrets.token_hex(3)
    branch = f"kaguya/t{task_id}-{index}-{agent}-{run}"
    path = worktree_base(repo_root) / f"t{task_id}-{index}-{agent}-{run}"
    path.parent.mkdir(parents=True, exist_ok=True)
    res = _git(repo_root, "worktree", "add", "-b", branch, str(path), "HEAD")
    if res.returncode != 0:
        raise RuntimeError("Não foi possível criar worktree: " + (res.stderr or res.stdout)[-500:])
    return path, branch


def commit_all(worktree: Path, message: str) -> bool:
    _git(worktree, "add", "-A")
    if not _git(worktree, "status", "--porcelain").stdout.strip():
        return False
    res = _git(worktree, "-c", "user.name=Kaguya Studio", "-c", "user.email=kaguya-studio@localhost",
               "commit", "-q", "-m", message)
    return res.returncode == 0


def changed_files(repo_root: Path, branch: str) -> list[str]:
    res = _git(repo_root, "diff", "--name-only", f"HEAD...{branch}")
    return [l for l in res.stdout.splitlines() if l.strip()]


def overlap(repo_root: Path, branches: list[str]) -> dict[str, list[str]]:
    seen: dict[str, list[str]] = {}
    for b in branches:
        for f in changed_files(repo_root, b):
            seen.setdefault(f, []).append(b)
    return {f: bs for f, bs in seen.items() if len(bs) > 1}


def diff(repo_root: Path, branch: str, limit: int = 60000) -> str:
    return _git(repo_root, "diff", f"HEAD...{branch}").stdout[:limit]


def integrate(repo_root: Path, branch: str) -> tuple[bool, str]:
    """Merge one worker branch into the current branch, only on explicit user action."""
    if _git(repo_root, "status", "--porcelain", "--untracked-files=no").stdout.strip():
        return False, "Há alterações não commitadas no projeto. Faça commit/backup antes de integrar."
    if not re.fullmatch(r"kaguya/[\w\-]+", branch):
        return False, "Ramo inválido."
    res = _git(repo_root, "merge", "--no-ff", "--no-edit", branch)
    if res.returncode != 0:
        _git(repo_root, "merge", "--abort")
        return False, "Conflito ao integrar; nada foi alterado (merge abortado).\n" + (res.stdout + res.stderr)[-1500:]
    return True, res.stdout.strip() or "Integrado."


def remove(repo_root: Path, path: Path, branch: str | None = None) -> None:
    _git(repo_root, "worktree", "remove", "--force", str(path))
    if branch:
        _git(repo_root, "branch", "-D", branch)
