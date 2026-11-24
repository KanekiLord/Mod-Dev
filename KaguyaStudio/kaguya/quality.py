"""Automatic checks run by the Studio itself (not reported by the agents).

Read-only Git checks always run; project tests run only with the user's explicit
permission for that task, because they execute repository code.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

from .env import child_env, redact


@dataclass
class Check:
    name: str
    status: str      # PASS | FAIL | ERRO | INDISPONIVEL | NAO_EXECUTADO
    details: str = ""

    def line(self) -> str:
        return f"{self.name}: {self.status}" + (f" — {self.details.strip().splitlines()[0][:160]}" if self.details.strip() else "")


def _no_window() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _git(repo: Path, *args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, creationflags=_no_window())


def git_snapshot(repo: Path) -> dict:
    if not shutil.which("git"):
        return {"available": False}
    try:
        status = _git(repo, "status", "--porcelain")
        stat = _git(repo, "diff", "--stat")
        head = _git(repo, "rev-parse", "--short", "HEAD")
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False}
    return {"available": status.returncode == 0, "status": status.stdout, "diffstat": stat.stdout.strip(),
            "head": head.stdout.strip()}


def detect_test_command(repo: Path) -> list[str] | None:
    repo = Path(repo)
    if os.name == "nt" and (repo / "gradlew.bat").is_file():
        return [str(repo / "gradlew.bat"), "--offline", "test"]
    if (repo / "gradlew").is_file():
        return ["bash" if os.name != "nt" else "sh", str(repo / "gradlew"), "--offline", "test"]
    if (repo / "pyproject.toml").is_file() or (repo / "pytest.ini").is_file():
        return [sys.executable, "-m", "pytest", "-q"]
    if (repo / "tests").is_dir() and any((repo / "tests").glob("test*.py")):
        return [sys.executable, "-m", "unittest", "discover", "-s", "tests"]
    if (repo / "package.json").is_file():
        npm = shutil.which("npm")
        return [npm, "test", "--silent"] if npm else None
    return None


def run_checks(repo: Path, *, run_tests: bool = False, test_command: str | None = None,
               timeout: int = 900) -> list[Check]:
    repo = Path(repo)
    checks: list[Check] = []
    if shutil.which("git"):
        try:
            p = _git(repo, "diff", "--check")
            if p.returncode == 0:
                checks.append(Check("git diff --check", "PASS"))
            elif "not a git repository" in (p.stderr or "").lower():
                checks.append(Check("git diff --check", "INDISPONIVEL", "pasta sem Git"))
            else:
                checks.append(Check("git diff --check", "FAIL", (p.stdout + p.stderr)[-2500:]))
            snap = git_snapshot(repo)
            if snap.get("available"):
                changed = [l for l in snap["status"].splitlines() if l.strip()]
                checks.append(Check("arquivos alterados", "PASS", f"{len(changed)} arquivo(s)\n" + snap["diffstat"][-2000:]))
                conflict = [l for l in changed if l[:2] in ("UU", "AA", "DD")]
                if conflict:
                    checks.append(Check("conflitos de merge", "FAIL", "\n".join(conflict)))
        except (OSError, subprocess.TimeoutExpired) as exc:
            checks.append(Check("git", "ERRO", str(exc)))
    else:
        checks.append(Check("git", "INDISPONIVEL", "Git não encontrado"))
    if not run_tests:
        checks.append(Check("testes do projeto", "NAO_EXECUTADO", "sem autorização para executar código do repositório nesta tarefa"))
        return checks
    cmd = shlex.split(test_command, posix=os.name != "nt") if test_command else detect_test_command(repo)
    if not cmd:
        checks.append(Check("testes do projeto", "INDISPONIVEL", "nenhum comando de teste reconhecido; configure em Projetos"))
        return checks
    env, _ = child_env()
    try:
        p = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, env=env, creationflags=_no_window())
        checks.append(Check(" ".join(Path(cmd[0]).name if i == 0 else c for i, c in enumerate(cmd)),
                            "PASS" if p.returncode == 0 else "FAIL", redact((p.stdout + "\n" + p.stderr)[-6000:])))
    except subprocess.TimeoutExpired:
        checks.append(Check("testes do projeto", "ERRO", f"tempo limite de {timeout}s"))
    except OSError as exc:
        checks.append(Check("testes do projeto", "ERRO", str(exc)))
    return checks


def summarize(checks: list[Check]) -> str:
    return "\n".join("- " + c.line() for c in checks)


def tests_passed(checks: list[Check]) -> bool | None:
    test = [c for c in checks if c.name not in ("git diff --check", "arquivos alterados", "conflitos de merge", "git")]
    if not test or test[-1].status in ("NAO_EXECUTADO", "INDISPONIVEL"):
        return None
    return all(c.status == "PASS" for c in test) and not any(c.status == "FAIL" for c in checks)
