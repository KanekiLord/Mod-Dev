"""Shared state between the Studio (UI) and the desktop MCP server process.

* ``PARAR`` file in the control folder: when present, every action is refused. The Studio creates it
  from the "Parar" button, the Ctrl+Alt+End hotkey, or the server itself when the failsafe fires
  (mouse pushed into the top-left corner of the screen).
* ``atividade.jsonl``: one line per action (time, action, detail) — the Studio shows the latest one in
  the "usando o computador" overlay and keeps it as the task's record.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import threading
import time

STOP = "PARAR"
ACTIVITY = "atividade.jsonl"
HOTKEY_TEXT = "Ctrl+Alt+End"


def control_dir(base: Path | None = None) -> Path:
    if base is None:
        env = os.environ.get("KAGUYA_DESKTOP_DIR")
        if env:
            base = Path(env)
        else:
            from ..appdirs import data_dir
            base = data_dir() / "desktop"
    Path(base).mkdir(parents=True, exist_ok=True)
    return Path(base)


def request_stop(base: Path, reason: str) -> None:
    (control_dir(base) / STOP).write_text(f"{time.strftime('%H:%M:%S')} {reason}\n", encoding="utf-8")


def stop_reason(base: Path) -> str | None:
    p = control_dir(base) / STOP
    try:
        return p.read_text(encoding="utf-8").strip() or "parada solicitada"
    except FileNotFoundError:
        return None


def reset(base: Path) -> None:
    d = control_dir(base)
    for name in (STOP, ACTIVITY):
        try:
            (d / name).unlink()
        except FileNotFoundError:
            pass


def log_action(base: Path, action: str, detail: str = "") -> None:
    line = json.dumps({"t": time.strftime("%H:%M:%S"), "action": action, "detail": detail[:300]}, ensure_ascii=False)
    with open(control_dir(base) / ACTIVITY, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def read_activity(base: Path, since: int = 0) -> tuple[list[dict], int]:
    """Entries appended after byte offset ``since`` → (entries, new offset)."""
    p = control_dir(base) / ACTIVITY
    try:
        with open(p, "rb") as fh:
            fh.seek(since)
            data = fh.read()
    except FileNotFoundError:
        return [], 0
    out = []
    for raw in data.decode("utf-8", "replace").splitlines():
        try:
            out.append(json.loads(raw))
        except ValueError:
            pass
    return out, since + len(data)


ACTION_TEXT = {"screenshot": "olhando a tela", "click": "clicando", "double_click": "clique duplo", "move": "movendo o mouse",
               "drag": "arrastando", "scroll": "rolando", "type": "digitando", "keys": "teclas", "focus": "trocando de janela",
               "windows": "listando janelas", "wait": "aguardando", "stopped": "parado", "refused": "recusado"}


class StopHotkey:
    """Global Ctrl+Alt+End (Windows) that calls ``on_press`` from a background thread while active."""

    def __init__(self, on_press):
        self.on_press = on_press
        self._thread: threading.Thread | None = None
        self._tid = 0
        self.registered = False

    def start(self) -> bool:
        if sys.platform != "win32" or self._thread:
            return False
        ready = threading.Event()

        def run():
            import ctypes
            from ctypes import wintypes
            user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
            self._tid = kernel32.GetCurrentThreadId()
            MOD_ALT, MOD_CONTROL, MOD_NOREPEAT, VK_END, WM_HOTKEY = 0x1, 0x2, 0x4000, 0x23, 0x0312
            self.registered = bool(user32.RegisterHotKey(None, 0x4B47, MOD_ALT | MOD_CONTROL | MOD_NOREPEAT, VK_END))
            ready.set()
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    try:
                        self.on_press()
                    except Exception:
                        pass
            if self.registered:
                user32.UnregisterHotKey(None, 0x4B47)
        self._thread = threading.Thread(target=run, daemon=True, name="kaguya-hotkey")
        self._thread.start()
        ready.wait(2)
        return self.registered

    def stop(self) -> None:
        if self._thread and sys.platform == "win32" and self._tid:
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self._tid, 0x0012, 0, 0)  # WM_QUIT
            self._thread.join(2)
        self._thread = None
        self._tid = 0
