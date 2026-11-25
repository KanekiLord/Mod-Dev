"""Startup log, error capture and hang watchdog.

Why: a modal error dialog raised from a repeating timer opens *nested* event loops — each
new dialog is created inside the previous one and never gets painted, leaving a small white
window and a frozen app. Errors are now logged to files and announced by at most one
non-blocking dialog; a watchdog dumps every thread's stack when the interface stops
responding, so a freeze on the user's PC leaves evidence in ``%LOCALAPPDATA%\\KaguyaStudio\\logs``.
"""
from __future__ import annotations

from datetime import datetime
import faulthandler
from pathlib import Path
import sys
import threading
import time
import traceback

from ..env import redact

_state = {"errors": 0, "dialog": None, "last_dialog": 0.0, "in_hook": False, "beat": time.monotonic(),
          "logs": None, "fault_file": None}


def logs_dir() -> Path:
    from ..appdirs import data_dir
    p = data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def step(message: str) -> None:
    """Append a line to logs/inicializacao.log (never raises)."""
    try:
        with (logs_dir() / "inicializacao.log").open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now():%Y-%m-%d %H:%M:%S.%f}"[:-3] + f"  {message}\n")
    except Exception:
        pass


def _record(text: str) -> Path | None:
    _state["errors"] += 1
    try:
        path = logs_dir() / "erros.log"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} (erro {_state['errors']}) =====\n{redact(text)}")
        return path
    except Exception:
        return None


def _notify(summary: str, path: Path | None) -> None:
    """One non-modal dialog, reused; never opens a nested event loop."""
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication, QMessageBox
    except Exception:
        return
    app = QApplication.instance()
    if app is None:
        return

    def show():
        now = time.monotonic()
        box = _state["dialog"]
        text = (f"{summary}\n\nO Studio continua aberto. Detalhes em:\n{path}\n"
                f"(erros nesta sessão: {_state['errors']})")
        if box is None:
            box = QMessageBox(QMessageBox.Warning, "Kaguya Studio — erro registrado", text)
            box.setModal(False)
            box.setWindowModality(0)
            _state["dialog"] = box
        elif now - _state["last_dialog"] < 2:
            box.setText(text)
            return
        box.setText(text)
        box.show()
        box.raise_()
        _state["last_dialog"] = now
    QTimer.singleShot(0, show)


def _hook(exc_type, exc, tb):
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    if sys.__stderr__:
        try:
            sys.__stderr__.write(text)
        except Exception:
            pass
    if _state["in_hook"]:
        return
    _state["in_hook"] = True
    try:
        path = _record(text)
        _notify(f"{exc_type.__name__}: {str(exc)[:300]}", path)
    finally:
        _state["in_hook"] = False


def install() -> None:
    sys.excepthook = _hook
    threading.excepthook = lambda args: _hook(args.exc_type, args.exc_value, args.exc_traceback)
    try:
        f = (logs_dir() / "falha_grave.log").open("a", encoding="utf-8")
        _state["fault_file"] = f
        faulthandler.enable(file=f, all_threads=True)
    except Exception:
        pass


def start_watchdog(app, timeout_s: float = 12.0) -> None:
    """GUI heartbeat every second; if it stops for ``timeout_s``, dump all stacks once per freeze."""
    from PySide6.QtCore import QTimer

    def beat():
        _state["beat"] = time.monotonic()
    timer = QTimer(app)
    timer.timeout.connect(beat)
    timer.start(1000)
    app._kaguya_heartbeat = timer

    def watch():
        dumped = False
        while True:
            time.sleep(2)
            idle = time.monotonic() - _state["beat"]
            if idle > timeout_s and not dumped:
                try:
                    path = logs_dir() / f"travamento_{datetime.now():%Y%m%d_%H%M%S}.txt"
                    with path.open("w", encoding="utf-8") as fh:
                        fh.write(f"Interface sem resposta há {idle:.0f}s. Pilhas de execução:\n\n")
                        faulthandler.dump_traceback(file=fh, all_threads=True)
                    step(f"TRAVAMENTO detectado ({idle:.0f}s) → {path.name}")
                except Exception:
                    pass
                dumped = True
            elif idle < timeout_s:
                dumped = False
    threading.Thread(target=watch, daemon=True, name="kaguya-watchdog").start()


def error_count() -> int:
    return _state["errors"]
