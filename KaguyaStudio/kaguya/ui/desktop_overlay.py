"""Always-on-top notice while an assistant is using the mouse/keyboard, with a big "Parar"."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ..desktop import control
from .theme import AGENT, C
from .widgets import Dot, button, label


class DesktopOverlay(QWidget):
    def __init__(self, win):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.win = win
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_StyledBackground, True)  # so the gold frame is painted
        self.setObjectName("DesktopOverlay")
        self.setStyleSheet(f"QWidget#DesktopOverlay {{ background: {C['elevated']}; border: 2px solid {C['gold']}; "
                           f"border-radius: 12px; }}")
        self.setFixedWidth(380)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(6)
        top = QHBoxLayout()
        self.dot = Dot(C["gold"], 10, pulse=True)
        self.title = label("", "h2")
        self.title.setStyleSheet(f"color: {C['text']}; font-size: 10.5pt; font-weight: 600;")
        top.addWidget(self.dot)
        top.addWidget(self.title, 1)
        lay.addLayout(top)
        self.where = label("", "muted", wrap=True)
        self.last = label("aguardando a primeira ação…", wrap=True)
        self.last.setStyleSheet(f"color: {C['text']}; font-size: 9.5pt;")
        lay.addWidget(self.where)
        lay.addWidget(self.last)
        row = QHBoxLayout()
        hint = label(f"{control.HOTKEY_TEXT} ou mouse no canto superior esquerdo também param.", "dim", wrap=True)
        hint.setStyleSheet(f"color: {C['dim']}; font-size: 8pt;")
        self.stop_btn = button("Parar", "stop", "danger", "Para o controle do computador e interrompe a tarefa")
        self.stop_btn.clicked.connect(lambda: self.win.stop_desktop("botão Parar"))
        row.addWidget(hint, 1)
        row.addWidget(self.stop_btn)
        lay.addLayout(row)
        self._offset = 0
        self.count = 0
        self._timer = QTimer(self, interval=300)
        self._timer.timeout.connect(self.poll)

    def start(self, agent: str | None, window: str):
        a = AGENT.get(agent or "", AGENT["equipe"])
        name = self.win.mascots[agent].profile["name"] if agent in self.win.mascots else a["name"]
        self.title.setText(f"{name} está usando o computador")
        self.where.setText(f"Somente a janela \"{window}\"" if window else "Tela inteira liberada")
        self.last.setText("aguardando a primeira ação…")
        self._offset, self.count = 0, 0
        self.adjustSize()
        geo = QGuiApplication.primaryScreen().availableGeometry()
        self.move(geo.right() - self.width() - 18, geo.bottom() - self.height() - 18)
        self.show()
        self._timer.start()

    def poll(self):
        entries, self._offset = control.read_activity(self.win.engine.home / "desktop", self._offset)
        if not entries:
            return
        self.count += len(entries)
        e = entries[-1]
        txt = control.ACTION_TEXT.get(e.get("action"), e.get("action"))
        self.last.setText(f"[{e.get('t')}] {txt} {e.get('detail', '')}  •  {self.count} ação(ões)")
        if e.get("action") in ("stopped",):
            self.dot.set_color(C["danger"], False)

    def finish(self):
        self._timer.stop()
        self.poll()
        self.hide()
