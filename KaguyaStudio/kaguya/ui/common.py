"""Thread bridge, background helper and folder picking that cannot hide behind other windows."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import threading
import traceback

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QFileDialog, QWidget


class Bridge(QObject):
    """Engine listener → Qt signal (queued into the GUI thread automatically)."""
    event = Signal(dict)
    call = Signal(object)

    def __init__(self):
        super().__init__()
        self.call.connect(lambda fn: fn())

    def listener(self, data: dict) -> None:
        self.event.emit(data)


_bridge: Bridge | None = None


def bridge() -> Bridge:
    global _bridge
    if _bridge is None:
        _bridge = Bridge()
    return _bridge


def run_bg(fn, on_done=None, on_error=None) -> threading.Thread:
    """Run ``fn`` in a thread; deliver result/error back on the GUI thread."""
    def worker():
        try:
            result = fn()
        except Exception as exc:  # reported to the UI, never swallowed
            tb = traceback.format_exc()
            if on_error:
                bridge().call.emit(lambda: on_error(exc, tb))
            else:
                print(tb, file=sys.stderr)
            return
        if on_done:
            bridge().call.emit(lambda: on_done(result))
    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return t


_hidden_windows: list[QWidget] = []


def pick_folder(parent: QWidget, title: str, start: str = "") -> str | None:
    """Folder dialog parented to the window. Floating always-on-top mascots are hidden while
    it is open (in V3.4 the second dialog could open *behind* topmost windows)."""
    hidden = []
    for w in QApplication.topLevelWidgets():
        if w.isVisible() and w.windowTitle().startswith(("Kaguya —", "Claude —")):
            w.hide()
            hidden.append(w)
    try:
        start_dir = start if start and Path(start).exists() else str(Path.home())
        path = QFileDialog.getExistingDirectory(parent, title, start_dir, QFileDialog.ShowDirsOnly)
    finally:
        for w in hidden:
            w.show()
    if parent is not None:
        parent.activateWindow()
        parent.raise_()
    return path or None


def pick_file(parent: QWidget, title: str, start: str = "", filt: str = "") -> str | None:
    path, _ = QFileDialog.getOpenFileName(parent, title, start or str(Path.home()), filt)
    return path or None


def open_path(path: str) -> bool:
    if not path or not Path(path).exists():
        return False
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def open_url(url: str) -> bool:
    return QDesktopServices.openUrl(QUrl(url))


def obsidian_uri(vault: str, rel: str) -> str:
    from urllib.parse import quote
    return f"obsidian://open?vault={quote(Path(vault).name)}&file={quote(rel.removesuffix('.md'))}"


def reveal(path: str) -> None:
    p = Path(path)
    if os.name == "nt" and p.exists():
        subprocess.Popen(["explorer", "/select,", str(p)])
    else:
        open_path(str(p.parent if p.is_file() else p))
