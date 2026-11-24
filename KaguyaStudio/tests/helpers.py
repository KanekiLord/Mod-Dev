"""Test utilities: temporary fake CLIs that behave like the official ones."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

FAKE = Path(__file__).resolve().parent / "fake_cli.py"


def make_fake_clis(folder: Path) -> dict[str, str]:
    """Create ``codex`` and ``claude`` launchers (``.cmd`` on Windows, like npm does)."""
    folder.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name in ("codex", "claude"):
        if os.name == "nt":
            p = folder / f"{name}.cmd"
            p.write_text(f'@"{sys.executable}" "{FAKE}" {name} %*\r\n', encoding="utf-8")
        else:
            p = folder / name
            p.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" {name} "$@"\n', encoding="utf-8")
            p.chmod(0o755)
        paths[name] = str(p)
    return paths


def fake_env(folder: Path, **extra: str) -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = str(folder) + os.pathsep + env.get("PATH", "")
    env["FAKE_LOG"] = str(folder / "calls.jsonl")
    for key in [k for k in env if k.startswith("FAKE_") and k != "FAKE_LOG"]:
        env.pop(key)
    # Provider/credential variables would make the V3.4 code refuse to run at all
    # (a defect covered by its own regression test); remove them so each test isolates one defect.
    for key in ("AWS_ACCESS_KEY_ID", "GOOGLE_APPLICATION_CREDENTIALS", "ANTHROPIC_BASE_URL", "OPENAI_BASE_URL",
                "OPENAI_API_BASE", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY"):
        env.pop(key, None)
    env.update(extra)
    return env


def calls(folder: Path) -> list[dict]:
    log = folder / "calls.jsonl"
    if not log.exists():
        return []
    return [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]


def git_init(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "teste@example.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Teste"], check=True)
    (path / "README.md").write_text("projeto\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "inicial"], check=True)
