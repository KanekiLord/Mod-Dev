"""Restore points for autonomous work.

Before an autonomous task touches the project, the Studio records the exact state of the working
tree (tracked files and new files that are not ignored) as a commit object under
``refs/kaguya/checkpoints/<task>``. It uses a temporary index, so the user's staging area, branch
and stash are never changed. "Desfazer" puts the files back exactly as they were and, if the agent
created commits, moves the branch back (the commits stay in the reflog). Nothing is ever pushed.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import tempfile

PREFIX = "refs/kaguya/checkpoints/"


class CheckpointError(RuntimeError):
    pass


@dataclass
class Checkpoint:
    ref: str
    commit: str
    head: str        # HEAD when the checkpoint was taken ("" in a repository without commits)
    branch: str      # branch name ("" when detached)
    index: str = ""  # tree of the user's staging area, restored exactly on undo


def _flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _git(repo: Path, *args: str, env: dict | None = None, check: bool = True, timeout: int = 120) -> str:
    run_env = dict(os.environ)
    run_env.update({"GIT_TERMINAL_PROMPT": "0", "GIT_AUTHOR_NAME": "Kaguya Studio",
                    "GIT_AUTHOR_EMAIL": "kaguya-studio@localhost", "GIT_COMMITTER_NAME": "Kaguya Studio",
                    "GIT_COMMITTER_EMAIL": "kaguya-studio@localhost"})
    if env:
        run_env.update(env)
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=run_env, timeout=timeout, creationflags=_flags())
    if check and p.returncode != 0:
        raise CheckpointError(f"git {' '.join(args[:2])}: {(p.stderr or p.stdout).strip()[:300]}")
    return p.stdout.strip()


def _files(repo: Path, rev: str | None) -> set[str]:
    if rev:
        out = _git(repo, "ls-tree", "-r", "-z", "--name-only", rev)
    else:
        out = _git(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    return {f for f in out.split("\0") if f}


def create(repo: Path, label: str) -> Checkpoint:
    repo = Path(repo)
    head = _git(repo, "rev-parse", "--verify", "-q", "HEAD", check=False)
    branch = _git(repo, "symbolic-ref", "-q", "--short", "HEAD", check=False)
    user_index = _git(repo, "write-tree", check=False)  # fails (→ "") only with merge conflicts
    fd, index = tempfile.mkstemp(prefix="kaguya-index-")
    os.close(fd)
    os.unlink(index)  # git creates it
    try:
        env = {"GIT_INDEX_FILE": index}
        if head:
            _git(repo, "read-tree", head, env=env)
        _git(repo, "add", "-A", "--", ".", env=env)
        tree = _git(repo, "write-tree", env=env)
    finally:
        try:
            os.unlink(index)
        except OSError:
            pass
    args = ["commit-tree", tree, "-m", f"Kaguya Studio: ponto de restauração — {label}"]
    if head:
        args[2:2] = ["-p", head]
    commit = _git(repo, *args)
    ref = PREFIX + "".join(c if c.isalnum() or c in "-_" else "-" for c in label)[:80]
    _git(repo, "update-ref", ref, commit)
    return Checkpoint(ref=ref, commit=commit, head=head, branch=branch, index=user_index)


def changes_since(repo: Path, cp: Checkpoint) -> list[str]:
    """Paths that differ between the checkpoint and the current working tree (incl. new/removed files)."""
    repo = Path(repo)
    fd, index = tempfile.mkstemp(prefix="kaguya-index-")
    os.close(fd)
    os.unlink(index)
    try:
        env = {"GIT_INDEX_FILE": index}
        _git(repo, "read-tree", cp.commit, env=env)
        _git(repo, "add", "-A", "--", ".", env=env)
        out = _git(repo, "diff", "--cached", "--name-only", "-z", cp.commit, env=env)
    finally:
        try:
            os.unlink(index)
        except OSError:
            pass
    return sorted(f for f in out.split("\0") if f)


def restore(repo: Path, cp: Checkpoint) -> list[str]:
    """Put the working tree back exactly as in ``cp``. Returns the paths that were changed."""
    repo = Path(repo)
    changed = changes_since(repo, cp)
    current_head = _git(repo, "rev-parse", "--verify", "-q", "HEAD", check=False)
    if cp.head and current_head != cp.head:
        # The agent committed: move the branch back (commits remain reachable through the reflog).
        _git(repo, "reset", "-q", "--mixed", cp.head)
    wanted = _files(repo, cp.commit)
    for rel in _files(repo, None) - wanted:
        p = repo / rel
        try:
            if p.is_file() or p.is_symlink():
                p.unlink()
        except OSError:
            pass
    if wanted:
        _git(repo, "checkout", cp.commit, "--", ".")
    # checkout also stages files: put the user's staging area back exactly as it was
    if cp.index:
        _git(repo, "read-tree", cp.index, check=False)
    elif cp.head:
        _git(repo, "reset", "-q", "--", ".", check=False)
    return changed


def drop(repo: Path, cp: Checkpoint) -> None:
    _git(Path(repo), "update-ref", "-d", cp.ref, check=False)


def to_text(cp: Checkpoint) -> str:
    return "|".join((cp.ref, cp.commit, cp.head, cp.branch, cp.index))


def from_text(text: str) -> Checkpoint | None:
    parts = (text or "").split("|")
    if len(parts) not in (4, 5) or not parts[0].startswith(PREFIX):
        return None
    return Checkpoint(*parts)
