"""Normalise the JSONL streams of ``claude -p --output-format stream-json`` and
``codex exec --json`` into one event model, and decide whether a run really succeeded.

Key fact verified with codex-cli 0.172: ``codex exec --json`` can exit with code **0** after
every request failed (401, limit, network). V3.4 trusted the exit code and marked such
tasks as "executada". Success now requires a completed turn and no fatal error.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any


@dataclass
class AgentEvent:
    agent: str
    kind: str                 # text | thinking | tool | tool_result | command | file_change | web |
                              # session | usage | rate_limit | error | warning | final | log | todo
    text: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    agent: str
    exit_code: int | None = None
    session_id: str | None = None
    final_text: str = ""
    texts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    commands: list[dict] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    rate_limits: list[dict] = field(default_factory=list)
    duration_ms: int = 0
    cost_usd: float | None = None
    cancelled: bool = False
    completed: bool = False     # the CLI reported a finished turn
    is_error: bool = False      # the CLI itself flagged the result as an error
    limit_reached: bool = False
    stale_session: bool = False
    structured: bool = True
    log_tail: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        if self.cancelled or self.exit_code not in (0, None) or self.is_error or self.limit_reached:
            return False
        if self.structured:
            return self.completed and not self.errors
        return self.exit_code == 0

    def failure_reason(self) -> str:
        if self.cancelled:
            return "Interrompido pelo usuário."
        if self.limit_reached:
            return "Limite de uso da assinatura atingido. " + (self.errors[-1] if self.errors else "")
        if self.errors:
            return self.errors[-1]
        if self.exit_code not in (0, None):
            tail = " | ".join(self.log_tail[-4:])
            return f"A CLI terminou com código {self.exit_code}. {tail}".strip()
        if self.structured and not self.completed:
            return "A CLI encerrou sem concluir a resposta (nenhum evento de conclusão recebido)."
        return ""


LIMIT_WORDS = ("usage limit", "rate limit", "limit reached", "hit your", "quota", "usage_limit",
               "too many requests", "429", "limite")


def _looks_like_limit(text: str) -> bool:
    low = text.lower()
    return any(w in low for w in LIMIT_WORDS)


class StreamParser:
    """Feed lines; collects a RunResult and yields AgentEvents for the UI."""

    def __init__(self, agent: str):
        self.agent = agent
        self.result = RunResult(agent=agent)

    def feed(self, line: str) -> list[AgentEvent]:
        line = line.strip()
        if not line:
            return []
        if not line.startswith("{"):
            self.result.log_tail = (self.result.log_tail + [line])[-20:]
            return [AgentEvent(self.agent, "log", line)]
        try:
            obj = json.loads(line)
        except ValueError:
            self.result.log_tail = (self.result.log_tail + [line])[-20:]
            return [AgentEvent(self.agent, "log", line)]
        if not isinstance(obj, dict):
            return []
        return self._claude(obj) if self.agent == "claude" else self._codex(obj)

    # ------------------------------------------------------------------ claude
    def _claude(self, o: dict) -> list[AgentEvent]:
        r, out = self.result, []
        t = o.get("type")
        if o.get("session_id") and not r.session_id:
            r.session_id = o["session_id"]
            out.append(AgentEvent("claude", "session", r.session_id, {"session_id": r.session_id}))
        if t == "system" and o.get("subtype") == "init":
            out.append(AgentEvent("claude", "log", f"Sessão iniciada • modelo {o.get('model', '?')}",
                                  {"model": o.get("model"), "tools": o.get("tools", []),
                                   "mcp_servers": o.get("mcp_servers", []), "agents": o.get("agents", [])}))
        elif t == "assistant":
            for block in (o.get("message") or {}).get("content") or []:
                bt = block.get("type")
                if bt == "text" and block.get("text"):
                    r.texts.append(block["text"])
                    out.append(AgentEvent("claude", "text", block["text"],
                                          {"subagent": bool(o.get("parent_tool_use_id"))}))
                elif bt == "thinking" and block.get("thinking"):
                    out.append(AgentEvent("claude", "thinking", block["thinking"][:2000]))
                elif bt == "tool_use":
                    name = block.get("name", "?")
                    inp = block.get("input") or {}
                    summary = _tool_summary(name, inp)
                    if name in ("Edit", "Write", "MultiEdit", "NotebookEdit") and inp.get("file_path"):
                        if inp["file_path"] not in r.files_changed:
                            r.files_changed.append(inp["file_path"])
                    if name in ("Bash", "PowerShell"):
                        r.commands.append({"command": inp.get("command", "")})
                    kind = "web" if name in ("WebSearch", "WebFetch") else "tool"
                    out.append(AgentEvent("claude", kind, summary, {"tool": name, "input": _clip(inp)}))
        elif t == "user":
            for block in (o.get("message") or {}).get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("is_error"):
                    content = block.get("content")
                    text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                    out.append(AgentEvent("claude", "tool_result", text[:600], {"error": True}))
        elif t == "rate_limit_event":
            info = o.get("rate_limit_info") or {}
            r.rate_limits.append(info)
            if info.get("status") == "rejected":
                r.limit_reached = True
            out.append(AgentEvent("claude", "rate_limit", "", info))
        elif t == "result":
            r.completed = True
            r.is_error = bool(o.get("is_error")) or str(o.get("subtype", "")).startswith("error")
            r.final_text = o.get("result") or (r.texts[-1] if r.texts else "")
            r.duration_ms = int(o.get("duration_ms") or 0)
            if o.get("total_cost_usd") is not None:
                r.cost_usd = float(o["total_cost_usd"])
            u = o.get("usage") or {}
            r.usage = {"input_tokens": int(u.get("input_tokens") or 0) + int(u.get("cache_creation_input_tokens") or 0),
                       "cached_tokens": int(u.get("cache_read_input_tokens") or 0),
                       "output_tokens": int(u.get("output_tokens") or 0)}
            for err in o.get("errors") or []:
                r.errors.append(str(err))
                if "no conversation found" in str(err).lower():
                    r.stale_session = True
            if r.is_error and not r.errors:
                r.errors.append(r.final_text or f"Claude encerrou com erro ({o.get('subtype')}).")
            if r.is_error and _looks_like_limit(" ".join(r.errors)):
                r.limit_reached = True
            denials = o.get("permission_denials") or []
            if denials:
                names = sorted({d.get("tool_name", "?") for d in denials if isinstance(d, dict)})
                r.warnings.append("Ferramentas negadas por permissão: " + ", ".join(names))
            out.append(AgentEvent("claude", "usage", "", dict(r.usage, duration_ms=r.duration_ms)))
            out.append(AgentEvent("claude", "final", r.final_text, {"is_error": r.is_error}))
        return out

    # ------------------------------------------------------------------- codex
    def _codex(self, o: dict) -> list[AgentEvent]:
        r, out = self.result, []
        t = o.get("type", "")
        if t == "thread.started":
            r.session_id = o.get("thread_id")
            out.append(AgentEvent("codex", "session", r.session_id or "", {"session_id": r.session_id}))
        elif t == "turn.completed":
            r.completed = True
            u = o.get("usage") or {}
            r.usage = {"input_tokens": int(u.get("input_tokens") or 0),
                       "cached_tokens": int(u.get("cached_input_tokens") or 0),
                       "output_tokens": int(u.get("output_tokens") or 0)}
            r.final_text = r.texts[-1] if r.texts else ""
            out.append(AgentEvent("codex", "usage", "", dict(r.usage)))
            out.append(AgentEvent("codex", "final", r.final_text))
        elif t == "turn.failed":
            msg = ((o.get("error") or {}).get("message")) or "Turno falhou."
            r.errors.append(msg)
            r.limit_reached = r.limit_reached or _looks_like_limit(msg)
            out.append(AgentEvent("codex", "error", msg))
        elif t == "error":
            msg = str(o.get("message") or "")
            if msg.lower().startswith("reconnecting"):
                out.append(AgentEvent("codex", "warning", msg))
            else:
                r.errors.append(msg)
                r.limit_reached = r.limit_reached or _looks_like_limit(msg)
                if "no rollout found" in msg.lower():
                    r.stale_session = True
                out.append(AgentEvent("codex", "error", msg))
        elif t.startswith("item."):
            item = o.get("item") or {}
            it = item.get("type")
            done = t == "item.completed"
            if it == "agent_message" and done:
                text = item.get("text", "")
                r.texts.append(text)
                out.append(AgentEvent("codex", "text", text))
            elif it == "reasoning" and done and item.get("text"):
                out.append(AgentEvent("codex", "thinking", item["text"][:2000]))
            elif it == "command_execution":
                cmd = item.get("command", "")
                if done:
                    r.commands.append({"command": cmd, "exit_code": item.get("exit_code"),
                                       "status": item.get("status")})
                    out.append(AgentEvent("codex", "command", f"$ {cmd}  → código {item.get('exit_code')}",
                                          {"output": (item.get("aggregated_output") or "")[-1500:],
                                           "exit_code": item.get("exit_code")}))
                elif t == "item.started":
                    out.append(AgentEvent("codex", "command", f"$ {cmd}", {"running": True}))
            elif it == "file_change" and done:
                paths = [c.get("path", "") for c in item.get("changes") or []]
                for p in paths:
                    if p and p not in r.files_changed:
                        r.files_changed.append(p)
                out.append(AgentEvent("codex", "file_change", ", ".join(paths), {"changes": item.get("changes")}))
            elif it == "web_search" and done:
                out.append(AgentEvent("codex", "web", f"Pesquisa: {item.get('query', '')}"))
            elif it == "mcp_tool_call" and done:
                out.append(AgentEvent("codex", "tool", f"MCP {item.get('server', '')}.{item.get('tool', '')}"))
            elif it == "todo_list":
                items = item.get("items") or []
                out.append(AgentEvent("codex", "todo", "\n".join(("☑ " if i.get("completed") else "☐ ") + i.get("text", "")
                                                                  for i in items)))
            elif it == "error" and done:
                msg = item.get("message", "")
                out.append(AgentEvent("codex", "warning", msg))
        return out


def _clip(data: dict, limit: int = 600) -> dict:
    out = {}
    for k, v in data.items():
        s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        out[k] = s[:limit]
    return out


def _tool_summary(name: str, inp: dict) -> str:
    if name in ("Read", "Edit", "Write", "MultiEdit", "NotebookEdit"):
        return f"{name} {inp.get('file_path', '')}"
    if name in ("Bash", "PowerShell"):
        return f"$ {inp.get('command', '')}"[:300]
    if name in ("Grep", "Glob"):
        return f"{name} {inp.get('pattern', '')}"
    if name == "WebSearch":
        return f"Pesquisa web: {inp.get('query', '')}"
    if name == "WebFetch":
        return f"Lendo: {inp.get('url', '')}"
    if name in ("Agent", "Task"):
        return f"Subagente {inp.get('subagent_type', '')}: {inp.get('description', '')}"
    return name
