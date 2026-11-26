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
  --mcp-config <configs...>  --strict-mcp-config
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
  -i, --image <FILE>...
"""


def _hub_home():
    return Path(os.environ.get("FAKE_HOME") or Path.home())


def _jload(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


if name == "claude" and args[:1] in (["mcp"], ["plugin"]):
    home = _hub_home()
    cfg_path = home / ".claude.json"
    if args[:3] == ["plugin", "list", "--json"]:
        print(os.environ.get("FAKE_CLAUDE_PLUGINS", "[]")); sys.exit(0)
    if args[:2] == ["plugin", "details"]:
        print(f"{args[2]}\n  Source: {args[2]}\n\nComponent inventory\n  Skills (1)  revisar-modelo\n  Agents (0)\n"
              "  Hooks (0)\n  MCP servers (0)\n  LSP servers (0)\n"); sys.exit(0)
    if args[:2] in (["plugin", "enable"], ["plugin", "disable"], ["plugin", "uninstall"], ["plugin", "install"]):
        print(f"{args[1]} ok: {args[2]}"); sys.exit(0)
    if args[:2] == ["mcp", "get"]:
        status = json.loads(os.environ.get("FAKE_MCP_STATUS", "{}")).get(args[2], "connected")
        text = {"connected": "√ Connected", "failed": "× Failed to connect", "needs-auth": "△ Needs authentication",
                "pending": "⏸ Pending approval"}[status]
        print(f"{args[2]}:\n  Scope: User config\n  Status: {text}\n  Type: stdio\n  Environment:\n    API_KEY=valor-secreto-do-fake")
        sys.exit(0)
    if args[:2] == ["mcp", "add-json"]:
        nm, raw = args[2], args[3]
        scope = args[args.index("-s") + 1] if "-s" in args else "local"
        spec = json.loads(sys.stdin.read() if raw == "-" else raw)
        if scope == "project":
            pj = Path.cwd() / ".mcp.json"
            data = _jload(pj); data.setdefault("mcpServers", {})[nm] = spec
            pj.write_text(json.dumps(data), encoding="utf-8")
        else:
            data = _jload(cfg_path)
            target = data if scope == "user" else data.setdefault("projects", {}).setdefault(str(Path.cwd()), {})
            target.setdefault("mcpServers", {})[nm] = spec
            cfg_path.write_text(json.dumps(data), encoding="utf-8")
        print(f"Added MCP server {nm} to {scope} config"); sys.exit(0)
    if args[:2] == ["mcp", "remove"]:
        nm = args[2]
        data = _jload(cfg_path)
        data.get("mcpServers", {}).pop(nm, None)
        for proj in data.get("projects", {}).values():
            proj.get("mcpServers", {}).pop(nm, None)
        cfg_path.write_text(json.dumps(data), encoding="utf-8")
        pj = Path.cwd() / ".mcp.json"
        if pj.is_file():
            d2 = _jload(pj); d2.get("mcpServers", {}).pop(nm, None); pj.write_text(json.dumps(d2), encoding="utf-8")
        print(f"Removed MCP server {nm}"); sys.exit(0)

if name == "codex" and args[:1] in (["mcp"], ["plugin"]):
    home = _hub_home()
    toml_path = home / ".codex" / "config.toml"
    if args[:3] == ["plugin", "list", "--json"]:
        print(json.dumps({"installed": json.loads(os.environ.get("FAKE_CODEX_PLUGINS", "[]")), "available": []}))
        sys.exit(0)
    if args[:3] == ["mcp", "list", "--json"]:
        import tomllib
        cfg = tomllib.loads(toml_path.read_text(encoding="utf-8")) if toml_path.is_file() else {}
        auth = json.loads(os.environ.get("FAKE_CODEX_AUTH_STATUS", "{}"))
        print(json.dumps([{"name": n, "enabled": v.get("enabled", True), "disabled_reason": None,
                           "transport": {"type": "stdio", "command": v.get("command"), "env": v.get("env", {})},
                           "auth_status": auth.get(n, "unsupported")} for n, v in cfg.get("mcp_servers", {}).items()]))
        sys.exit(0)
    if args[:2] == ["mcp", "add"]:
        nm = args[2]
        env, rest = {}, args[3:]
        while rest and rest[0] == "--env":
            k, v = rest[1].split("=", 1); env[k] = v; rest = rest[2:]
        if rest and rest[0] == "--":
            rest = rest[1:]
        toml_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"\n[mcp_servers.{nm}]", f"command = {json.dumps(rest[0])}", f"args = {json.dumps(rest[1:])}"]
        if env:
            lines.append(f"[mcp_servers.{nm}.env]")
            lines += [f"{k} = {json.dumps(v)}" for k, v in env.items()]
        with open(toml_path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        print(f"Added global MCP server '{nm}'."); sys.exit(0)
    if args[:2] == ["mcp", "remove"]:
        import re as _re
        nm = args[2]
        text = toml_path.read_text(encoding="utf-8") if toml_path.is_file() else ""
        text = _re.sub(rf"\n?\[mcp_servers\.{_re.escape(nm)}(\.env)?\][^\[]*", "", text)
        toml_path.write_text(text, encoding="utf-8")
        print(f"Removed global MCP server '{nm}'."); sys.exit(0)

if name == "claude":
    if args[:1] == ["--version"]:
        print("2.1.0 (Claude Code)"); sys.exit(0)
    if args[:1] == ["--help"]:
        print(CLAUDE_HELP); sys.exit(0)
    if args[:2] == ["auth", "status"]:
        if "--help" in args:
            print("Usage: claude auth status [options]\n  --json  --text"); sys.exit(0)
        if os.environ.get("FAKE_CLAUDE_AUTH_HANG"):
            # what froze the Studio on Windows: the command never answers and a child holds the output open
            import subprocess as _sp
            _sp.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
            import time as _t
            _t.sleep(120)
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
        if os.environ.get("FAKE_PROMPT_LOG"):   # lets tests see exactly what the assistant received
            with open(os.environ["FAKE_PROMPT_LOG"], "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"cli": name, "args": args, "prompt": prompt}) + "\n")
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
        if os.environ.get("FAKE_CLAUDE_SLEEP"):  # a long task (to test cancellation)
            import time as _t
            _t.sleep(float(os.environ["FAKE_CLAUDE_SLEEP"]))
        if "--mcp-config" in args:
            # like the real CLI: start every configured MCP server and use the desktop tools once
            cfg = json.load(open(args[args.index("--mcp-config") + 1], encoding="utf-8"))
            for name, srv in cfg["mcpServers"].items():
                penv = dict(os.environ, **srv.get("env", {}))
                msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                        {"jsonrpc": "2.0", "method": "notifications/initialized"},
                        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "screenshot", "arguments": {}}},
                        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "click", "arguments": {"x": 5, "y": 5}}}]
                r = subprocess.run([srv["command"], *srv.get("args", [])], input="\n".join(json.dumps(m) for m in msgs) + "\n",
                                   capture_output=True, text=True, env=penv, timeout=60)
                replies = [json.loads(l) for l in r.stdout.splitlines() if l.strip()]
                ok = [not rep.get("result", {}).get("isError", True) for rep in replies if rep.get("id") in (2, 3)]
                out({"type": "assistant", "session_id": sid, "message": {"content": [
                    {"type": "text", "text": f"MCP {name}: {len(replies)} respostas, ferramentas ok={ok}"}]}})
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
            if os.environ.get("FAKE_CLAUDE_REPLY") and "[Pedido da" not in prompt:
                text = os.environ["FAKE_CLAUDE_REPLY"]
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
        if os.environ.get("FAKE_PROMPT_LOG"):   # lets tests see exactly what the assistant received
            with open(os.environ["FAKE_PROMPT_LOG"], "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"cli": name, "args": args, "prompt": prompt}) + "\n")
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
