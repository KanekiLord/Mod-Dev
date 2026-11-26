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
# Secrets are never read or changed by the assistants, in any task (verified with Claude Code 2.1.331:
# "File is in a directory that is denied by your permission settings"). Codex gets the same rule in the prompt.
SENSITIVE_GLOBS = ["**/.env", "**/.env.*", "**/*.pem", "**/*.key", "**/*.p12", "**/*.pfx", "**/id_rsa*",
                   "**/id_ed25519*", "**/.ssh/**", "**/.aws/**", "**/.azure/**", "**/.git-credentials", "**/.netrc",
                   "**/.npmrc", "**/.pypirc", "**/credentials.json", "**/*.kdbx", "**/.codex/auth.json",
                   "**/.claude/.credentials.json"]
SENSITIVE_DENY = [f"{tool}({g})" for tool in ("Read", "Edit", "Write", "Grep") for g in SENSITIVE_GLOBS]

# "Meu computador": deleting the user's files in bulk is never done through the shell (the assistant must ask
# with the confirm tool and delete precise files)
PC_DENY = [f"{tool}({pat})" for tool in ("Bash", "PowerShell") for pat in (
    "rm -r:*", "rm -rf:*", "rmdir /s:*", "del /s:*", "Remove-Item -Recurse:*", "Clear-RecycleBin:*",
    "cipher /w:*", "takeown:*", "icacls:*", "net user:*", "bcdedit:*", "Set-ExecutionPolicy:*")]
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
    desktop: dict | None = None  # {"command": [...], "env": {...}, "config_file": path} → screen/mouse/keyboard MCP
    pc: bool = False             # "Meu computador": user's home folder, no Git requirement, personal-assistant tools
    resume: str | None = None    # session/thread id to continue
    model: str | None = None     # e.g. "sonnet"/"haiku" for cheap roles; None = CLI default
    in_git: bool = True
    workdir: str | None = None
    extra_dirs: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)   # files attached by the user (e.g. a captured video frame)
    browser: dict | None = None  # {"command", "env", "config_file"} → Kaguya Browser tools (shared tabs only)


def claude_command(exe: str, caps: Capabilities, opts: RunOptions) -> list[str]:
    cmd = [exe, "-p"]
    structured = not caps.flags or caps.has("--output-format")
    if structured:
        cmd += ["--output-format", "stream-json"]
        if not caps.flags or caps.has("--verbose"):
            cmd.append("--verbose")  # required by stream-json in print mode
    if opts.write or opts.pc:
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
    if opts.desktop:
        allowed.append("mcp__" + DESKTOP_SERVER)
    if opts.browser:
        allowed.append("mcp__" + BROWSER_SERVER)
    if not caps.flags or caps.has("--allowedTools") or caps.has("--allowed-tools"):
        cmd += ["--allowedTools", ",".join(allowed)]
    denied = []
    if not opts.commands:
        denied += COMMAND_TOOLS
    if not opts.write:
        denied += WRITE_TOOLS
    if not opts.web:
        denied += WEB_TOOLS
    if not opts.mcp and not opts.desktop and not opts.browser:
        denied.append("mcp__*")
    denied += SENSITIVE_DENY
    if opts.autonomous or opts.pc:
        denied += AUTONOMY_DENY
    if opts.pc:
        denied += PC_DENY
    if denied and (not caps.flags or caps.has("--disallowedTools") or caps.has("--disallowed-tools")):
        cmd += ["--disallowedTools", ",".join(denied)]
    if opts.model:
        cmd += ["--model", opts.model]
    studio_mcp = opts.desktop or opts.browser   # both write the same config file listing the Studio's servers
    if studio_mcp and (not caps.flags or caps.has("--mcp-config")):
        cmd += ["--mcp-config", str(studio_mcp["config_file"])]
        if not opts.mcp:
            cmd.append("--strict-mcp-config")  # only the Studio's servers, none of the user's MCPs
    import os as _os
    dirs = list(opts.extra_dirs)
    for img in opts.images:   # Claude opens attached images with its Read tool: allow just their folder
        folder = _os.path.dirname(_os.path.abspath(img))
        if folder not in dirs:
            dirs.append(folder)
    for d in dirs:
        cmd += ["--add-dir", d]
    if opts.resume and (not caps.flags or caps.has("--resume") or caps.has("-r")):
        cmd += ["--resume", opts.resume]
    # IMPORTANT: no positional prompt. The task goes through stdin (safe for .cmd launchers).
    return cmd


def codex_command(exe: str, caps: Capabilities, opts: RunOptions) -> list[str]:
    cmd = [exe]
    sandbox = "workspace-write" if opts.write else "read-only"
    if not caps.flags or caps.has("--config") or caps.has("-c"):
        # always THIS task's permissions — also when resuming: a resumed session used to keep the sandbox of the
        # task that created it (a read-only question could resume a session allowed to write)
        cmd += ["-c", f"sandbox_mode='{sandbox}'"]
    if (opts.autonomous or opts.pc) and opts.write and (not caps.flags or caps.has("--config") or caps.has("-c")):
        # builds such as Gradle need to download dependencies; the sandbox still limits writes to the project
        cmd += ["-c", "sandbox_workspace_write.network_access=true"]
    if opts.desktop and (not caps.flags or caps.has("--config") or caps.has("-c")):
        cmd += codex_desktop_config(opts.desktop)
    if opts.browser and (not caps.flags or caps.has("--config") or caps.has("-c")):
        cmd += codex_desktop_config(opts.browser, BROWSER_SERVER)
    if opts.web:
        cmd.append("--search")
    cmd.append("exec")
    if opts.resume:
        cmd += ["resume", opts.resume]
    structured = not caps.flags or caps.has("--json")
    if opts.images and structured and (not caps.flags or caps.has("--image") or caps.has("-i")):
        for img in opts.images:   # always followed by --json, so the variadic option never eats the prompt "-"
            cmd += ["--image", img]
    if structured:
        cmd.append("--json")
    if not opts.resume:  # "exec resume" has no --sandbox flag: the -c sandbox_mode above covers it
        cmd += ["--sandbox", sandbox]
        if opts.workdir and (not caps.flags or caps.has("--cd") or caps.has("-C")):
            cmd += ["-C", opts.workdir]
    if not opts.in_git and (not caps.flags or caps.has("--skip-git-repo-check")):
        cmd.append("--skip-git-repo-check")
    if opts.model:
        cmd += ["-m", opts.model]
    cmd.append("-")  # read the prompt from stdin
    return cmd


DESKTOP_SERVER = "kaguya_desktop"
BROWSER_SERVER = "kaguya_browser"


def _toml_str(value: str) -> str:
    value = str(value)
    if "'" not in value and "\n" not in value:
        return "'" + value + "'"  # literal string: Windows backslashes need no escaping
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def codex_desktop_config(desktop: dict, server: str = DESKTOP_SERVER) -> list[str]:
    exe, *args = desktop["command"]
    key = f"mcp_servers.{server}"
    env = ",".join(f"{k}={_toml_str(v)}" for k, v in sorted((desktop.get("env") or {}).items()))
    out = ["-c", f"{key}.command={_toml_str(exe)}",
           "-c", f"{key}.args=[{','.join(_toml_str(a) for a in args)}]",
           "-c", f"{key}.default_tools_approval_mode='approve'",  # no double quotes (safe through .cmd launchers)
           "-c", f"{key}.tool_timeout_sec=90"]
    if env:
        out += ["-c", f"{key}.env={{{env}}}"]
    return out


def claude_desktop_config(desktop: dict | None, browser: dict | None = None) -> dict:
    servers = {}
    for name, spec in ((DESKTOP_SERVER, desktop), (BROWSER_SERVER, browser)):
        if spec:
            exe, *args = spec["command"]
            servers[name] = {"type": "stdio", "command": exe, "args": args, "env": dict(spec.get("env") or {})}
    return {"mcpServers": servers}


def build_command(target: str, exe: str, caps: Capabilities, opts: RunOptions) -> list[str]:
    if opts.write and not opts.in_git and not opts.pc:
        raise ValueError("Edição bloqueada: a pasta do projeto não está em um repositório Git (sem como desfazer).")
    if target == "claude":
        return claude_command(exe, caps, opts)
    if target == "codex":
        return codex_command(exe, caps, opts)
    raise ValueError("Destino desconhecido")
