"""Stand-in for the official CLIs in automated tests (no network, no account, no cost).

Behaviour mirrors what was observed on the real binaries (codex-cli 0.172, Claude Code 2.1):
* ``codex exec`` refuses to run outside Git unless ``--skip-git-repo-check`` is given;
* ``codex exec --json`` exits 0 even when every request failed (FAKE_CODEX_FAIL=1);
* ``codex login status`` prints to stderr; ``claude auth status --json`` prints JSON;
* ``--disallowedTools`` is variadic: a positional argument after it is swallowed.
Controlled by environment variables FAKE_*; every invocation is appended to FAKE_LOG.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

name = sys.argv[1]
args = sys.argv[2:]
log = os.environ.get("FAKE_LOG")
if log:
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"cli": name, "args": args, "cwd": os.getcwd(),
                             "has_api_key": bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"))})
                 + "\n")


def out(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def in_git():
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
        return r.returncode == 0
    except OSError:
        return False


def next_verdict():
    path = os.environ.get("FAKE_VERDICTS")
    if not path or not os.path.exists(path):
        return "aprovado"
    with open(path, encoding="utf-8") as fh:
        items = [l.strip() for l in fh if l.strip()]
    first, rest = (items[0], items[1:]) if items else ("aprovado", [])
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(rest))
    return first


CLAUDE_HELP = """Usage: claude [options] [command] [prompt]
  -p, --print  --output-format <format> "text", "json", or "stream-json"  --verbose
  --permission-mode <mode> (choices: "acceptEdits", "auto", "bypassPermissions", "default", "dontAsk", "plan")
  --allowedTools, --allowed-tools <tools...>  --disallowedTools, --disallowed-tools <tools...>
  --model <model>  -r, --resume [value]  --add-dir <directories...>  --tools <tools...>
Commands: auth  Manage authentication
"""
CODEX_HELP = """Usage: codex [OPTIONS] [PROMPT]
  --search   Enable live web search
Commands: exec  login  app-server
"""
CODEX_EXEC_HELP = """Usage: codex exec [OPTIONS] [PROMPT]
Commands: resume
  -s, --sandbox <SANDBOX_MODE> [possible values: read-only, workspace-write, danger-full-access]
  -c, --config <key=value>  -C, --cd <DIR>  -m, --model <MODEL>  --skip-git-repo-check  --json  -o, --output-last-message <FILE>
"""

if name == "claude":
    if args[:1] == ["--version"]:
        print("2.1.0 (Claude Code)"); sys.exit(0)
    if args[:1] == ["--help"]:
        print(CLAUDE_HELP); sys.exit(0)
    if args[:2] == ["auth", "status"]:
        if "--help" in args:
            print("Usage: claude auth status [options]\n  --json  --text"); sys.exit(0)
        mode = os.environ.get("FAKE_CLAUDE_AUTH", "claude.ai")
        data = {"loggedIn": mode != "none", "authMethod": mode, "apiProvider": "firstParty"}
        if mode == "claude.ai":
            data["subscriptionType"] = "max"
        print(json.dumps(data, indent=2)); sys.exit(0)
    if "-p" in args and "--input-format" in args:
        # Persistent stream-json conversation (Live mode): one process, many turns.
        sid = "22222222-3333-4444-8555-666666666666"
        out({"type": "system", "subtype": "init", "session_id": sid, "model": "claude-test"})
        history = []
        for line in sys.stdin:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("type") == "control_request":
                continue
            text = (msg.get("message") or {}).get("content", "")
            history.append(text)
            reply = f"Entendi, você disse: {text}. Já são {len(history)} mensagens nesta conversa."
            if "implement" in text.lower():
                reply += " Vou deixar na fila.\n[[TAREFA: " + text + "]]"
            for i in range(0, len(reply), 7):
                out({"type": "stream_event", "session_id": sid,
                     "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": reply[i:i + 7]}}})
            out({"type": "rate_limit_event", "session_id": sid, "rate_limit_info": {"status": "allowed",
                 "unifiedWindows": {"five_hour": {"utilization": 0.3, "resetsAt": 1795600000}}}})
            out({"type": "result", "subtype": "success", "is_error": False, "session_id": sid, "result": reply})
        sys.exit(0)
    if "-p" in args:
        # Emulate commander's variadic options: positional after --disallowedTools is a tool name.
        prompt = sys.stdin.read()
        if not prompt.strip():
            print("Error: Input must be provided either through stdin or as a prompt argument", file=sys.stderr)
            sys.exit(1)
        if "--resume" in args and os.environ.get("FAKE_CLAUDE_STALE"):
            sid = args[args.index("--resume") + 1]
            print(f"No conversation found with session ID: {sid}", file=sys.stderr)
            out({"type": "result", "subtype": "error_during_execution", "is_error": True, "session_id": sid,
                 "errors": [f"No conversation found with session ID: {sid}"], "usage": {}})
            sys.exit(1)
        sid = "11111111-2222-4333-8444-555555555555"
        out({"type": "system", "subtype": "init", "session_id": sid, "model": "claude-test", "tools": ["Read"]})
        if os.environ.get("FAKE_CLAUDE_LIMIT"):
            out({"type": "rate_limit_event", "session_id": sid,
                 "rate_limit_info": {"status": "rejected", "rateLimitType": "five_hour", "resetsAt": 1795600000}})
            out({"type": "result", "subtype": "success", "is_error": True, "session_id": sid,
                 "result": "You've hit your session limit", "usage": {}})
            sys.exit(1)
        if "REVISOR" in prompt:
            verdict = next_verdict()
            text = ("Revisei o diff.\n```json\n" + json.dumps({"veredito": verdict, "problemas":
                    ([] if verdict == "aprovado" else ["Falta tratar entrada vazia em Missao.java"])}) + "\n```")
        else:
            text = "Resposta do Claude: " + prompt.strip().splitlines()[-1][:120]
            text += "\nAPRENDIZADOS:\n- Forge 1.7.10 exige registrar eventos no FMLInitializationEvent."
        out({"type": "assistant", "session_id": sid, "message": {"content": [{"type": "text", "text": text}]}})
        out({"type": "rate_limit_event", "session_id": sid,
             "rate_limit_info": {"status": "allowed", "unifiedWindows": {
                 "five_hour": {"utilization": 0.25, "resetsAt": 1795600000},
                 "seven_day": {"utilization": 0.5, "resetsAt": 1796000000}}}})
        out({"type": "result", "subtype": "success", "is_error": False, "session_id": sid, "result": text,
             "duration_ms": 1200, "usage": {"input_tokens": 100, "output_tokens": 50, "cache_read_input_tokens": 10}})
        sys.exit(0)
    print("interactive mode not supported in fake", file=sys.stderr); sys.exit(2)

if name == "codex":
    if args[:1] == ["--version"]:
        print("codex-cli 0.172.0"); sys.exit(0)
    if args[:1] == ["--help"]:
        print(CODEX_HELP); sys.exit(0)
    if args[:2] == ["exec", "--help"]:
        print(CODEX_EXEC_HELP); sys.exit(0)
    if args[:2] == ["login", "status"]:
        mode = os.environ.get("FAKE_CODEX_AUTH", "chatgpt")
        if mode == "none":
            print("Not logged in", file=sys.stderr); sys.exit(1)
        if mode == "apikey":
            print("Logged in using an API key - sk-proj-***ABCDE", file=sys.stderr); sys.exit(0)
        print("Logged in using ChatGPT", file=sys.stderr); sys.exit(0)
    rest = [a for a in args if a != "--search"]
    while rest[:1] == ["-c"]:  # global config overrides, as in the real CLI
        rest = rest[2:]
    if rest[:1] == ["exec"]:
        if "--skip-git-repo-check" not in rest and not in_git():
            print("Not inside a trusted directory and --skip-git-repo-check was not specified.", file=sys.stderr)
            sys.exit(1)
        prompt = sys.stdin.read()
        tid = "01a20fdf-0796-7d02-b7ef-05a8bbec3a05"
        if "resume" in rest and os.environ.get("FAKE_CODEX_STALE"):
            print("Error: thread/resume: thread/resume failed: no rollout found for thread id", file=sys.stderr)
            out({"type": "error", "message": "thread/resume failed: no rollout found for thread id x"})
            sys.exit(1)
        out({"type": "thread.started", "thread_id": tid})
        out({"type": "turn.started"})
        if os.environ.get("FAKE_CODEX_FAIL"):
            for i in range(1, 3):
                out({"type": "error", "message": f"Reconnecting... {i}/5 (unexpected status 401 Unauthorized)"})
            out({"type": "error", "message": "unexpected status 401 Unauthorized: Missing bearer or basic authentication"})
            sys.exit(0)  # real codex exits 0 here!
        if os.environ.get("FAKE_CODEX_WRITE") and "workspace-write" in rest:
            with open("feito_pelo_codex.txt", "a", encoding="utf-8") as fh:
                fh.write("ok\n")
            out({"type": "item.completed", "item": {"id": "i1", "type": "file_change",
                                                     "changes": [{"path": "feito_pelo_codex.txt", "kind": "add"}]}})
        out({"type": "item.completed", "item": {"id": "i2", "type": "command_execution", "command": "git status",
                                                 "aggregated_output": "", "exit_code": 0, "status": "completed"}})
        last = prompt.strip().splitlines()[-1][:160] if prompt.strip() else ""
        out({"type": "item.completed", "item": {"id": "i3", "type": "agent_message",
                                                 "text": "Implementado pelo Codex. " + last}})
        out({"type": "turn.completed", "usage": {"input_tokens": 300, "cached_input_tokens": 20, "output_tokens": 80}})
        sys.exit(0)
    print("unsupported", file=sys.stderr); sys.exit(2)

if name == "gh":
    if args[:1] == ["--version"]:
        print("gh version 2.89.0 (2026-03-26)"); sys.exit(0)
    if args[:2] == ["auth", "status"]:
        if "--show-token" in args or "-t" in args:
            print("FALHA: o Studio nunca deve pedir o token", file=sys.stderr); sys.exit(9)
        mode = os.environ.get("FAKE_GH_AUTH", "ok")
        hosts = {} if mode == "none" else {"github.com": [{"state": "success", "active": True, "host": "github.com",
                                                           "login": "kaguya-teste", "gitProtocol": "https"}]}
        print(json.dumps({"hosts": hosts})); sys.exit(0)
    if args[:2] == ["repo", "create"]:
        repo = args[2]
        remotes = os.environ["FAKE_GH_REMOTES"]
        bare = os.path.join(remotes, repo + ".git")
        if os.path.exists(bare):
            print("GraphQL: Name already exists on this account (createRepository)", file=sys.stderr); sys.exit(1)
        subprocess.run(["git", "init", "-q", "--bare", bare], check=True)
        src = args[args.index("--source") + 1]
        url = f"https://github.com/kaguya-teste/{repo}.git"
        subprocess.run(["git", "-C", src, "config", f"url.{Path(bare).as_uri()}.insteadOf", url], check=True)
        subprocess.run(["git", "-C", src, "remote", "add", "origin", url], check=True)
        if "--push" in args:
            br = subprocess.run(["git", "-C", src, "branch", "--show-current"], capture_output=True, text=True).stdout.strip()
            subprocess.run(["git", "-C", src, "push", "-q", "-u", "origin", br], check=True)
        print(f"https://github.com/kaguya-teste/{repo}"); sys.exit(0)
    if args[:2] == ["pr", "create"]:
        print("https://github.com/kaguya-teste/repo/pull/1"); sys.exit(0)
    print("unsupported", file=sys.stderr); sys.exit(2)
