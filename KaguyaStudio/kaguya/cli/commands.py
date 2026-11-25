"""Command lines for headless runs of the official CLIs.

V3.4 defects fixed here (reproduced in tests/test_regressoes_v34.py):
1. ``codex exec`` outside a trusted Git folder fails with "Not inside a trusted directory and
   --skip-git-repo-check was not specified" -> the flag is added for read-only work in
   folders without Git (writing still requires Git, for safe rollback).
2. ``--disallowedTools`` (and ``--tools``) are *variadic* in Claude Code; V3.4 placed the
   instruction string right after them, so it was swallowed as a tool name. Now the prompt
   travels only through stdin and no positional argument follows a variadic option.
3. ``--permission-mode plan`` in ``-p`` mode only plans and cannot be approved headless;
   ``acceptEdits`` alone denies Bash, so tests could never run. Permissions are now explicit
   per task: read (dontAsk + read tools), write (acceptEdits + edit tools) and an optional
   "executar comandos" permission that allows Bash.
4. Text output had no session id, usage or structured errors -> ``stream-json``/``--json``.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .discovery import Capabilities

READ_TOOLS = ["Read", "Glob", "Grep", "LS", "TodoWrite", "Agent", "Task"]
WRITE_TOOLS = ["Edit", "Write", "MultiEdit", "NotebookEdit"]
WEB_TOOLS = ["WebSearch", "WebFetch"]
COMMAND_TOOLS = ["Bash", "PowerShell"]
# Autonomous mode runs without confirmations, but some actions stay with the user. These Claude Code
# permission rules are a first barrier (best effort); the real safety net is the Git restore point.
AUTONOMY_DENY = [f"{tool}({pat})" for tool in ("Bash", "PowerShell") for pat in (
    "git push:*", "git remote:*", "git config --global:*", "gh:*", "npm install -g:*", "npm i -g:*",
    "pip install:*", "pip3 install:*", "winget:*", "choco:*", "scoop:*", "shutdown:*", "format:*",
    "reg add:*", "reg delete:*", "Remove-Item -Recurse C:*", "rm -rf /:*", "rd /s:*")]


@dataclass
class RunOptions:
    write: bool = False          # may edit files
    commands: bool = False       # may run shell commands (tests/builds)
    web: bool = False            # may search/fetch the web
    mcp: bool = False            # may use configured MCP servers
    autonomous: bool = False     # no confirmations: edit + commands + network for builds (Gradle)
    resume: str | None = None    # session/thread id to continue
    model: str | None = None     # e.g. "sonnet"/"haiku" for cheap roles; None = CLI default
    in_git: bool = True
    workdir: str | None = None
    extra_dirs: list[str] = field(default_factory=list)


def claude_command(exe: str, caps: Capabilities, opts: RunOptions) -> list[str]:
    cmd = [exe, "-p"]
    structured = not caps.flags or caps.has("--output-format")
    if structured:
        cmd += ["--output-format", "stream-json"]
        if not caps.flags or caps.has("--verbose"):
            cmd.append("--verbose")  # required by stream-json in print mode
    if opts.write:
        mode = "acceptEdits"
    elif not caps.flags or caps.mentions("dontAsk"):
        mode = "dontAsk"
    else:
        mode = "default"
    if not caps.flags or caps.has("--permission-mode"):
        cmd += ["--permission-mode", mode]
    allowed = list(READ_TOOLS)
    if opts.write:
        allowed += WRITE_TOOLS
    if opts.commands:
        allowed += COMMAND_TOOLS
    if opts.web:
        allowed += WEB_TOOLS
    if not caps.flags or caps.has("--allowedTools") or caps.has("--allowed-tools"):
        cmd += ["--allowedTools", ",".join(allowed)]
    denied = []
    if not opts.commands:
        denied += COMMAND_TOOLS
    if not opts.write:
        denied += WRITE_TOOLS
    if not opts.web:
        denied += WEB_TOOLS
    if not opts.mcp:
        denied.append("mcp__*")
    if opts.autonomous:
        denied += AUTONOMY_DENY
    if denied and (not caps.flags or caps.has("--disallowedTools") or caps.has("--disallowed-tools")):
        cmd += ["--disallowedTools", ",".join(denied)]
    if opts.model:
        cmd += ["--model", opts.model]
    for d in opts.extra_dirs:
        cmd += ["--add-dir", d]
    if opts.resume and (not caps.flags or caps.has("--resume") or caps.has("-r")):
        cmd += ["--resume", opts.resume]
    # IMPORTANT: no positional prompt. The task goes through stdin (safe for .cmd launchers).
    return cmd


def codex_command(exe: str, caps: Capabilities, opts: RunOptions) -> list[str]:
    cmd = [exe]
    if opts.autonomous and opts.write and (not caps.flags or caps.has("--config") or caps.has("-c")):
        # builds such as Gradle need to download dependencies; the sandbox still limits writes to the project
        cmd += ["-c", "sandbox_workspace_write.network_access=true"]
    if opts.web:
        cmd.append("--search")
    cmd.append("exec")
    if opts.resume:
        cmd += ["resume", opts.resume]
    structured = not caps.flags or caps.has("--json")
    if structured:
        cmd.append("--json")
    if not opts.resume:  # resume inherits the original sandbox/cwd
        sandbox = "workspace-write" if opts.write else "read-only"
        cmd += ["--sandbox", sandbox]
        if opts.workdir and (not caps.flags or caps.has("--cd") or caps.has("-C")):
            cmd += ["-C", opts.workdir]
    if not opts.in_git and (not caps.flags or caps.has("--skip-git-repo-check")):
        cmd.append("--skip-git-repo-check")
    if opts.model:
        cmd += ["-m", opts.model]
    cmd.append("-")  # read the prompt from stdin
    return cmd


def build_command(target: str, exe: str, caps: Capabilities, opts: RunOptions) -> list[str]:
    if opts.write and not opts.in_git:
        raise ValueError("Edição bloqueada: a pasta do projeto não está em um repositório Git (sem como desfazer).")
    if target == "claude":
        return claude_command(exe, caps, opts)
    if target == "codex":
        return codex_command(exe, caps, opts)
    raise ValueError("Destino desconhecido")
