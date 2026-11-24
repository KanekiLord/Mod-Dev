"""Child-process environment that keeps the official CLIs on the paid *subscription* login.

V3.4 raised an exception when any provider variable existed (e.g. an unrelated
``AWS_ACCESS_KEY_ID``), which blocked every agent with a confusing message. Now those
variables are simply not passed to Codex/Claude, and the removal is reported in the
diagnosis so the user knows what was ignored. Values are never logged.
"""
from __future__ import annotations

import os
import re

# Variables that would make a CLI bill an API key or route to another provider.
API_KEY_VARS = (
    "OPENAI_API_KEY", "CODEX_API_KEY", "ANTHROPIC_API_KEY", "CLAUDE_CODE_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
)
PROVIDER_VARS = (
    "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY",
    "ANTHROPIC_BASE_URL", "OPENAI_BASE_URL", "OPENAI_API_BASE", "ANTHROPIC_BEDROCK_BASE_URL",
    "ANTHROPIC_VERTEX_PROJECT_ID",
)


def child_env(origin: dict[str, str] | None = None) -> tuple[dict[str, str], list[str]]:
    """Return (environment for the CLI, names of variables that were removed)."""
    env = dict(os.environ if origin is None else origin)
    removed = []
    for name in (*API_KEY_VARS, *PROVIDER_VARS):
        if env.get(name):
            removed.append(name)
        env.pop(name, None)
    # Make CLI output machine friendly and stable across Windows code pages.
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env["NO_COLOR"] = "1"
    return env, sorted(removed)


_SECRET_PATTERNS = [
    re.compile(r"sk-(?:ant-|proj-)?[A-Za-z0-9_\-]{12,}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{12,}"),
    re.compile(r"(?i)((?:api[_-]?key|token|secret|password|senha)\s*[=:]\s*)[^\s'\"]{6,}"),
    re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}"),
]


def redact(text: str) -> str:
    """Mask things that look like credentials before storing or displaying logs."""
    if not text:
        return text
    out = text
    for pattern in _SECRET_PATTERNS:
        if pattern.groups:
            out = pattern.sub(lambda m: m.group(1) + "***", out)
        else:
            out = pattern.sub("***", out)
    return out
