"""Live mode window: hands-free voice conversation with the active assistant."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..appdirs import ASSETS
from . import theme
from .theme import AGENT, C
from .widgets import Dot, Meter, Pill, SpriteView, button, label

STATE_TEXT = {"preparing": "Preparando…", "listening": "Ouvindo — pode falar", "hearing": "Ouvindo você…",
              "transcribing": "Entendendo…", "thinking": "Pensando…", "speaking": "Falando — fale por cima para interromper",
              "muted": "Microfone desligado", "idle": "Pronto"}
MASCOT_STATE = {"listening": "listening", "hearing": "listening", "transcribing": "thinking", "thinking": "thinking",
                "speaking": "speaking", "muted": "idle", "preparing": "thinking"}


class LiveWindow(QWidget):
    def __init__(self, win):
        super().__init__(None, Qt.Window)
        self.win = win
        self.setWindowTitle("Kaguya Studio — Modo Live")
        self.setWindowIcon(win.windowIcon())
        self.resize(520, 720)
        self.setMinimumSize(420, 600)
        self.bg = QPixmap(str(ASSETS / "backgrounds" / "noite.png"))
        self.agent = "codex"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)
        top = QHBoxLayout()
        t = label("Modo Live", "h1")
        top.addWidget(t)
        top.addStretch(1)
        self.agent_pill = Pill("", C["violet"])
        top.addWidget(self.agent_pill)
        lay.addLayout(top)
        self.sprite = SpriteView(C["violet"])
        self.sprite.setMinimumSize(256, 256)
        lay.addWidget(self.sprite, 1)
        srow = QHBoxLayout()
        srow.addStretch(1)
        self.dot = Dot(C["success"], 10, pulse=True)
        self.state = label("Preparando…")
        self.state.setStyleSheet(f"font-size: 12pt; font-weight: 600; color: {C['text']};")
        srow.addWidget(self.dot)
        srow.addWidget(self.state)
        srow.addStretch(1)
        lay.addLayout(srow)
        self.meter = Meter(C["success"])
        self.meter.set_value(0)
        lay.addWidget(self.meter)
        self.you = label("", wrap=True)
        self.you.setStyleSheet(f"color: {C['muted']}; font-size: 10pt;")
        self.ai = label("", wrap=True)
        self.ai.setStyleSheet(f"color: {C['text']}; font-size: 11pt;")
        self.ai.setMinimumHeight(90)
        self.ai.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        lay.addWidget(self.you)
        lay.addWidget(self.ai)
        self.err = label("", wrap=True)
        self.err.setStyleSheet(f"color: {C['warning']}; font-size: 9pt;")
        lay.addWidget(self.err)
        row = QHBoxLayout()
        self.mute_btn = button("Mudo", "mic-off", tip="Desliga o microfone sem sair do Live", checkable=True)
        self.mute_btn.toggled.connect(lambda on: self.win.live_mute(on))
        self.switch_btn = button("Claude", "claude")
        self.switch_btn.clicked.connect(lambda: self.win.live_switch("claude" if self.agent == "codex" else "codex"))
        hush = button("Silenciar voz", "volume-off", "ghost")
        hush.clicked.connect(lambda: self.win.voice.stop_speaking())
        end = button("Encerrar", "x", "danger")
        end.clicked.connect(self.close)
        for b in (self.mute_btn, self.switch_btn, hush, end):
            row.addWidget(b)
        lay.addLayout(row)
        hint = label("Fale normalmente • fale por cima para interromper • diga \"falar com a Miwa\" ou \"encerrar\". "
                     "Use fone para a IA não ouvir a própria voz. Pedidos de mudança no código viram tarefas na fila.",
                     "dim", wrap=True)
        hint.setStyleSheet(f"color: {C['dim']}; font-size: 8.5pt;")
        lay.addWidget(hint)
        self._timer = QTimer(self, interval=220)
        self._timer.timeout.connect(self._refresh_sprite)
        self._timer.start()

    def paintEvent(self, e):
        p = QPainter(self)
        if not self.bg.isNull():
            scale = max(self.width() / self.bg.width(), self.height() / self.bg.height())
            sw, sh = self.width() / scale, self.height() / scale
            p.drawPixmap(QRectF(self.rect()), self.bg, QRectF((self.bg.width() - sw) / 2, 0, sw, sh))
        g = QLinearGradient(0, 0, 0, self.height())
        g.setColorAt(0, QColor(14, 10, 22, 150))
        g.setColorAt(0.5, QColor(14, 10, 22, 200))
        g.setColorAt(1, QColor(14, 10, 22, 245))
        p.fillRect(self.rect(), g)

    def set_agent(self, agent: str):
        self.agent = agent
        a = AGENT[agent]
        name = self.win.mascots[agent].profile["name"]
        self.agent_pill.set(name if name == a["name"] else f"{name} • {a['name']}", a["color"])
        self.sprite.accent = QColor(a["color"])
        other = "claude" if agent == "codex" else "codex"
        oname = self.win.mascots[other].profile["name"]
        self.switch_btn.setText(oname)
        self.switch_btn.setToolTip(f"Passar a conversa para {oname} ({AGENT[other]['name']}) — ou diga \"falar com a {oname}\"")
        self.switch_btn.setIcon(theme.icon(AGENT[other]["icon"], AGENT[other]["color"]))
        self._refresh_sprite()

    def _refresh_sprite(self):
        self.sprite.set_image(self.win.mascots[self.agent].image())

    def on_event(self, ev: dict):
        t = ev["type"]
        if t == "agent":
            self.set_agent(ev["agent"])
        elif t == "state":
            st = ev["state"]
            self.state.setText(STATE_TEXT.get(st, st))
            color = {"listening": C["success"], "hearing": C["gold"], "speaking": C["violet"] if self.agent == "codex"
                     else C["amber"], "muted": C["dim"]}.get(st, C["info"])
            self.dot.set_color(color, st not in ("muted",))
            m = self.win.mascots.get(self.agent)
            if m:
                m.set_state(MASCOT_STATE.get(st, "idle"))
        elif t == "level":
            self.meter.set_value(ev["value"] * 100)
        elif t == "caption":
            if ev["role"] == "user":
                self.you.setText(f"Você: {ev['text']}")
                self.ai.setText("")
                self.err.setText("")
            else:
                name = self.win.mascots[ev.get("agent", self.agent)].profile["name"]
                self.ai.setText(f"<b>{name}:</b> {ev['text']}")
        elif t == "error":
            self.err.setText("⚠ " + ev["message"][:300])
        elif t == "request_end":
            QTimer.singleShot(1500, self.close)

    def closeEvent(self, e):
        self.win.stop_live()
        super().closeEvent(e)
