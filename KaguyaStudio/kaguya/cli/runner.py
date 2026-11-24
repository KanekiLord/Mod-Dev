"""Run one headless CLI turn with streaming, cancellation and honest result reporting."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import threading
import time
from typing import Callable

from ..env import child_env, redact
from .commands import RunOptions, build_command
from .discovery import Capabilities
from .events import AgentEvent, RunResult, StreamParser

MAX_PROMPT = 60000


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=10,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
    except (OSError, subprocess.TimeoutExpired):
        try:
            proc.kill()
        except OSError:
            pass


def run_command(agent: str, command: list[str], cwd: Path, prompt: str,
                on_event: Callable[[AgentEvent], None], *, log_file: Path | None = None,
                cancel: threading.Event | None = None, env: dict[str, str] | None = None,
                timeout_s: float | None = None, structured: bool = True) -> RunResult:
    run_env, _removed = child_env(env)
    parser = StreamParser(agent)
    parser.result.structured = structured
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    log_lines: list[str] = []
    started = time.monotonic()
    try:
        proc = subprocess.Popen(command, cwd=str(cwd), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                                bufsize=1, env=run_env, creationflags=flags)
    except FileNotFoundError:
        parser.result.errors.append(f"Executável não encontrado: {command[0]}. Rode o diagnóstico da CLI.")
        parser.result.exit_code = -1
        return parser.result
    except OSError as exc:
        parser.result.errors.append(f"Não foi possível iniciar {command[0]}: {exc}")
        parser.result.exit_code = -1
        return parser.result

    def feed_stdin():
        try:
            assert proc.stdin is not None
            proc.stdin.write(prompt[:MAX_PROMPT])
            proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            pass
        finally:
            try:
                proc.stdin.close()
            except (OSError, ValueError):
                pass

    def read_stderr():
        assert proc.stderr is not None
        for raw in proc.stderr:
            line = redact(raw.rstrip("\n"))
            if not line.strip():
                continue
            log_lines.append("[stderr] " + line)
            parser.result.log_tail = (parser.result.log_tail + [line])[-20:]
            low = line.lower()
            if "error" in low or "erro" in low:
                on_event(AgentEvent(agent, "log", line, {"stderr": True}))

    stopped = threading.Event()

    def watchdog():
        while not stopped.wait(0.25):
            if cancel is not None and cancel.is_set():
                parser.result.cancelled = True
                _kill_tree(proc)
                return
            if timeout_s and time.monotonic() - started > timeout_s:
                parser.result.errors.append(f"Tempo limite de {int(timeout_s)}s excedido; execução encerrada.")
                _kill_tree(proc)
                return

    threads = [threading.Thread(target=feed_stdin, daemon=True), threading.Thread(target=read_stderr, daemon=True),
               threading.Thread(target=watchdog, daemon=True)]
    for t in threads:
        t.start()
    try:
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = redact(raw.rstrip("\n"))
            log_lines.append(line)
            for event in parser.feed(line):
                on_event(event)
        parser.result.exit_code = proc.wait()
    finally:
        stopped.set()
        for t in threads[:2]:
            t.join(timeout=3)
        for stream in (proc.stdout, proc.stderr):
            try:
                if stream:
                    stream.close()
            except OSError:
                pass
    if not structured:
        text = "\n".join(l for l in log_lines if not l.startswith("[stderr]")).strip()
        parser.result.final_text = text[-20000:]
        parser.result.completed = parser.result.exit_code == 0
    if log_file:
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            log_file.write_text("$ " + " ".join(_display_cmd(command)) + "\n" + "\n".join(log_lines)[-800000:],
                                encoding="utf-8")
        except OSError:
            pass
    return parser.result


def _display_cmd(command: list[str]) -> list[str]:
    return [Path(command[0]).name, *command[1:]]


def run_agent(agent: str, executable: str, caps: Capabilities, cwd: Path, prompt: str, opts: RunOptions,
              on_event: Callable[[AgentEvent], None], **kwargs) -> RunResult:
    command = build_command(agent, executable, caps, opts)
    structured = ("--json" in command) if agent == "codex" else ("stream-json" in command)
    result = run_command(agent, command, cwd, prompt, on_event, structured=structured, **kwargs)
    if result.stale_session and opts.resume and not result.cancelled:
        on_event(AgentEvent(agent, "warning", "Sessão anterior não encontrada; iniciando nova conversa."))
        fresh = RunOptions(**{**opts.__dict__, "resume": None})
        result = run_command(agent, build_command(agent, executable, caps, fresh), cwd, prompt, on_event,
                             structured=structured, **kwargs)
    return result
