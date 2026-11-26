"""Run external programs without ever hanging the Studio.

Why this exists: on Windows ``subprocess.run(..., capture_output=True, timeout=N)`` can wait
forever. When the time runs out it kills only the direct child (``claude.cmd`` / ``codex.cmd`` is a
``cmd.exe`` that starts ``node``) and then calls ``communicate()`` **without** a timeout; the
``node`` grandchild still holds the output pipes open, so the call never returns. That froze the
Live ("Preparando…" forever), the name listener and the task queue (Cancelar did nothing).

``run`` has the same signature as ``subprocess.run`` and is a drop-in replacement: it kills the
whole process tree on timeout or cancel, and it never waits more than a few seconds after that.
"""
from __future__ import annotations

import os
import subprocess
import threading
import time

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def kill_tree(proc: subprocess.Popen) -> None:
    """Kill a process and everything it started (Windows: taskkill /T; elsewhere: its process group)."""
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.call(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=10, creationflags=_NO_WINDOW)
        else:
            try:
                os.killpg(proc.pid, 9)
            except (OSError, AttributeError):
                proc.kill()
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        if proc.poll() is None:
            proc.kill()
    except OSError:
        pass


def run(cmd, *, input=None, capture_output: bool = False, timeout: float | None = None,
        cancel: threading.Event | None = None, check: bool = False, text: bool = False,
        encoding: str | None = None, errors: str | None = None, **kw) -> subprocess.CompletedProcess:
    """``subprocess.run`` that cannot hang. Output is captured through temporary files and the wait is
    on the process itself — not on the pipes, which a background child (Gradle daemon, ``node`` behind a
    ``.cmd``) can keep open forever. Timeout/cancel kill the whole tree. Raises
    ``subprocess.TimeoutExpired`` on timeout and ``InterruptedError`` on cancel."""
    import tempfile
    files = []
    if capture_output:
        for name in ("stdout", "stderr"):
            if kw.get(name) in (None, subprocess.PIPE):
                f = tempfile.TemporaryFile()
                files.append((name, f))
                kw[name] = f
    elif kw.get("stdout") == subprocess.PIPE or kw.get("stderr") == subprocess.PIPE:
        for name in ("stdout", "stderr"):
            if kw.get(name) == subprocess.PIPE:
                f = tempfile.TemporaryFile()
                files.append((name, f))
                kw[name] = f
    if input is not None:
        data = input.encode(encoding or "utf-8", errors or "strict") if isinstance(input, str) else input
        fin = tempfile.TemporaryFile()
        fin.write(data)
        fin.seek(0)
        kw["stdin"] = fin
        files.append(("stdin", fin))
    if os.name != "nt":
        kw.setdefault("start_new_session", True)          # own process group → killpg reaches the children
    try:
        proc = subprocess.Popen(cmd, **kw)
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            step = 0.2 if deadline is None else max(0.01, min(0.2, deadline - time.monotonic()))
            try:
                proc.wait(step)
                break
            except subprocess.TimeoutExpired:
                cancelled = cancel is not None and cancel.is_set()
                if cancelled or (deadline is not None and time.monotonic() >= deadline):
                    kill_tree(proc)
                    try:
                        proc.wait(5)
                    except subprocess.TimeoutExpired:
                        pass
                    if cancelled:
                        raise InterruptedError("Cancelado.")
                    raise subprocess.TimeoutExpired(cmd, timeout)
        out = {"stdout": None, "stderr": None}
        for name, f in files:
            if name == "stdin":
                continue
            f.seek(0)
            raw = f.read()
            if text or encoding or errors:
                raw = raw.decode(encoding or "utf-8", errors or "replace").replace("\r\n", "\n")
            out[name] = raw
        res = subprocess.CompletedProcess(cmd, proc.returncode, out["stdout"], out["stderr"])
    finally:
        for _n, f in files:
            try:
                f.close()
            except OSError:
                pass
    if check:
        res.check_returncode()
    return res
