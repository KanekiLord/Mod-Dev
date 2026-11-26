"""Live mode as a small floating chibi (instead of a big window).

A transparent, always-on-top little window with the active assistant's chibi, a speech bubble with what was said,
the microphone level and four round buttons (mute, switch assistant, silence the voice, end). Drag it anywhere; the
position is remembered. Same public interface as ``LiveWindow`` (set_agent / on_event / close), so the Live session
does not know which one is on screen.

Animation follows the real conversation:
listening → calm, breathing · hearing → attentive · understanding/thinking → thinking (Miwa opens her laptop when it
takes long) · speaking → talking sequences that only move while there is voice in the audio · start → greeting ·
error → serious.
"""
from __future__ import annotations

import json
import math
import random
import time

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..appdirs import ASSETS
from . import theme
from .theme import AGENT, C

FOLDERS = {"codex": "kaguya_chibi", "claude": "miwa_chibi"}
TALK = {"codex": {"fala_neutra": 4, "explicando": 2, "animada": 1, "carinhosa": 1},
        "claude": {"fala_neutra": 4, "explicando": 2, "explicando2": 2, "animada": 1}}
GREET = {"codex": "carinhosa", "claude": "acenando"}
STATE_TEXT = {"failed": "Não foi possível iniciar — veja o aviso", "preparing": "Preparando…", "listening": "Ouvindo", "hearing": "Ouvindo você…",
              "transcribing": "Entendendo…", "thinking": "Pensando…", "speaking": "Falando",
              "muted": "Microfone desligado", "idle": "Pronto"}
SPRITE = 210


class ChibiSet:
    """Frames of one character's chibi, as pixmaps already scaled for the window."""

    def __init__(self, agent: str, size: int = SPRITE):
        base = ASSETS / "mascots" / FOLDERS[agent]
        self.agent = agent
        man = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
        native = int(man.get("frame_size", 128))
        pixel_art = native <= 128   # Kaguya's chibi is pixel art: integer-ish nearest scaling keeps it sharp
        self.ms = man.get("frame_durations_ms") or [140]
        self.seq: dict[str, list[QPixmap]] = {}
        for name, spec in man["sequences"].items():
            frames = []
            for f in spec["frames"]:
                pm = QPixmap(str(base / f))
                if pm.isNull():
                    continue
                frames.append(pm.scaled(size, size, Qt.KeepAspectRatio,
                                        Qt.FastTransformation if pixel_art else Qt.SmoothTransformation))
            if frames:
                self.seq[name] = frames

    def has(self, name: str) -> bool:
        return name in self.seq

    def idle(self) -> QPixmap:
        return (self.seq.get("parada") or self.seq["fala_neutra"])[0]


class LiveChibi(QWidget):
    def __init__(self, win):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.win = win
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("Kaguya Studio — Live")
        self.setWindowIcon(win.windowIcon())
        self.setFixedSize(300, 430)
        self.agent = "codex"
        self.sets: dict[str, ChibiSet] = {}
        self.state = "preparing"
        self.level = 0.0
        self.bubble = ""          # what the assistant said (or "Você: …" while it thinks)
        self.bubble_user = False
        self._anim: list[QPixmap] = []
        self._pos = 0
        self._once = False        # play a sequence once, then go back to the state's pose
        self._since = time.monotonic()
        self._drag: QPoint | None = None
        self._t0 = time.monotonic()
        # texts kept as labels (same API as LiveWindow; also handy for screen readers and tests)
        self.you, self.ai, self.err = QLabel(), QLabel(), QLabel()
        for lab in (self.you, self.ai, self.err):
            lab.hide()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 8)
        lay.addStretch(1)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch(1)
        self.mute_btn = self._round("mic-off", "Desligar o microfone (sem sair do Live)", checkable=True)
        self.mute_btn.toggled.connect(lambda on: self.win.live_mute(on))
        self.switch_btn = self._round("claude", "Passar a conversa para a outra IA")
        self.switch_btn.clicked.connect(lambda: self.win.live_switch("claude" if self.agent == "codex" else "codex"))
        self.hush_btn = self._round("volume-off", "Silenciar a voz agora")
        self.hush_btn.clicked.connect(lambda: self.win.voice.stop_speaking())
        self.end_btn = self._round("x", "Encerrar o Live", danger=True)
        self.end_btn.clicked.connect(self.close)
        for b in (self.mute_btn, self.switch_btn, self.hush_btn, self.end_btn):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self._timer = QTimer(self, interval=60)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._next_frame = 0.0
        self._place()

    # ----------------------------------------------------------------- parts
    def _round(self, ic: str, tip: str, checkable: bool = False, danger: bool = False) -> QPushButton:
        b = QPushButton()
        b.setToolTip(tip)
        b.setCheckable(checkable)
        b.setFixedSize(38, 38)
        b.setCursor(Qt.PointingHandCursor)
        b.setIcon(theme.icon(ic, C["danger"] if danger else C["text"]))
        b.setStyleSheet(f"QPushButton {{ background: rgba(27,20,48,225); border: 1px solid {C['border']};"
                        f" border-radius: 19px; }} QPushButton:hover {{ background: {C['hover']}; }}"
                        f" QPushButton:checked {{ background: {C['danger']}; border-color: {C['danger']}; }}")
        return b

    def _place(self):
        pos = self.win.store.get_setting("live.chibi.pos", None)
        screen = self.win.screen().availableGeometry() if self.win.screen() else None
        if pos and screen and screen.adjusted(-50, -50, 50, 50).contains(QPoint(*pos)):
            self.move(*pos)
        elif screen:
            self.move(screen.right() - self.width() - 24, screen.bottom() - self.height() - 24)

    def chibi(self, agent: str | None = None) -> ChibiSet:
        agent = agent or self.agent
        if agent not in self.sets:
            self.sets[agent] = ChibiSet(agent)
        return self.sets[agent]

    # ------------------------------------------------------------- interface
    def set_agent(self, agent: str):
        changed = agent != self.agent or not self.sets
        self.agent = agent
        other = "claude" if agent == "codex" else "codex"
        oname = self.win.mascots[other].profile["name"]
        self.switch_btn.setIcon(theme.icon(AGENT[other]["icon"], AGENT[other]["color"]))
        self.switch_btn.setToolTip(f"Passar a conversa para {oname} — ou diga \"falar com a {oname}\"")
        self.switch_btn.setText("")
        self.switch_btn.setProperty("other", oname)
        if changed:
            self.play(GREET[agent], once=True)
        self.update()

    def on_event(self, ev: dict):
        t = ev["type"]
        if t == "agent":
            self.set_agent(ev["agent"])
        elif t == "state":
            self.set_state(ev["state"])
        elif t == "level":
            self.level = float(ev["value"])
        elif t == "caption":
            if ev["role"] == "user":
                self.you.setText(f"Você: {ev['text']}")
                self.ai.setText("")
                self.err.setText("")
                self.bubble, self.bubble_user = ev["text"], True
            else:
                name = self.win.mascots[ev.get("agent", self.agent)].profile["name"]
                self.ai.setText(f"{name}: {ev['text']}")
                self.bubble, self.bubble_user = ev["text"], False
            self.update()
        elif t == "progress":
            self.ai.setText(ev["text"])
            self.bubble, self.bubble_user = ev["text"], False
            self.update()
        elif t == "error":
            self.err.setText("⚠ " + ev["message"][:300])
            self.bubble, self.bubble_user = "⚠ " + ev["message"][:160], False
            self.play("seria", once=True)
            self.update()
        elif t == "called":
            self.play(GREET[self.agent], once=True)
        elif t == "request_end":
            QTimer.singleShot(1500, self, self.close)

    def set_state(self, st: str):
        if st == self.state:
            return
        self.state, self._since = st, time.monotonic()
        m = self.win.mascots.get(self.agent)
        if m:   # keep the desktop mascot in sync too
            m.set_state({"listening": "listening", "hearing": "listening", "transcribing": "thinking",
                         "thinking": "thinking", "speaking": "speaking"}.get(st, "idle"))
        if self._once:
            return
        self._pose()

    # -------------------------------------------------------------- animation
    def play(self, name: str, once: bool = False):
        cs = self.chibi()
        if not cs.has(name):
            return
        self._anim, self._pos, self._once = cs.seq[name], 0, once
        self._next_frame = 0.0

    def _pose(self):
        """Sequence for the current state (looping)."""
        cs = self.chibi()
        st = self.state
        if st == "speaking":
            names = [n for n in TALK[self.agent] if cs.has(n)]
            pick = random.choices(names, weights=[TALK[self.agent][n] for n in names])[0]
            self.play(pick)
        elif st in ("transcribing", "thinking", "preparing"):
            long = time.monotonic() - self._since > 4 and cs.has("trabalhando")
            self.play("trabalhando" if long else "pensando")
        elif st == "hearing":
            self._anim, self._pos = [cs.seq["surpresa"][0] if cs.has("surpresa") else cs.idle()], 0
        else:
            self._anim, self._pos = [cs.idle()], 0

    def _tick(self):
        now = time.monotonic()
        if now >= self._next_frame and self._anim:
            talking = self.state == "speaking" and not self._once
            voice = self._voice_level()
            if talking and voice is not None and voice < 0.08:
                self._pos = 0                       # a pause in the real audio: mouth closed, wait
                self._next_frame = now + 0.06
            else:
                self._pos += 1
                if self._pos >= len(self._anim):
                    if self._once:
                        self._once = False
                        self._pose()
                    elif self.state == "speaking":
                        self._pose()                # next gesture
                    elif self.state in ("transcribing", "thinking") and self.chibi().has("trabalhando") \
                            and time.monotonic() - self._since > 4:
                        self._pose()
                    else:
                        self._pos = 0
                ms = self.chibi().ms
                self._next_frame = now + (ms[self._pos % len(ms)] if isinstance(ms, list) else ms) / 1000
        self.update()

    def _voice_level(self):
        try:
            return self.win.voice.level()
        except Exception:
            return None

    def frame(self) -> QPixmap:
        if not self._anim:
            self._pose()
        return self._anim[min(self._pos, len(self._anim) - 1)]

    # ---------------------------------------------------------------- drawing
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor(AGENT[self.agent]["color"])
        w = self.width()
        sprite_top = self.height() - 56 - SPRITE - 26
        # soft glow under the character (reacts to the microphone while listening)
        t = time.monotonic() - self._t0
        listening = self.state in ("listening", "hearing")
        pulse = 0.5 + 0.5 * math.sin(t * 2.2)
        glow = QColor(color)
        glow.setAlpha(int(40 + (110 * min(1.0, self.level * 2) if listening else 30 * pulse)))
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QRectF(w / 2 - 82, sprite_top + SPRITE - 26, 164, 34))
        # the chibi (breathing when idle)
        pm = self.frame()
        bob = 2.5 * math.sin(t * 2.0) if self.state in ("listening", "muted", "idle") else 0
        if self.state == "muted":
            p.setOpacity(0.55)
        p.drawPixmap(int((w - pm.width()) / 2), int(sprite_top + (SPRITE - pm.height()) + bob), pm)
        p.setOpacity(1.0)
        # name + state chip
        name = self.win.mascots[self.agent].profile["name"]
        chip = f"{name} · {STATE_TEXT.get(self.state, self.state)}"
        f = QFont(theme.FONT_UI, 9)
        f.setBold(True)
        p.setFont(f)
        fm = QFontMetrics(f)
        cw = fm.horizontalAdvance(chip) + 34
        cr = QRectF((w - cw) / 2, sprite_top + SPRITE + 2, cw, 22)
        p.setBrush(QColor(20, 15, 34, 225))
        p.setPen(QPen(color, 1))
        p.drawRoundedRect(cr, 11, 11)
        dot = {"listening": C["success"], "hearing": C["gold"], "muted": C["dim"]}.get(self.state, color.name())
        p.setBrush(QColor(dot))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(cr.left() + 10, cr.center().y() - 4, 8, 8))
        p.setPen(QColor(C["text"]))
        p.drawText(cr.adjusted(24, 0, -6, 0), Qt.AlignVCenter | Qt.AlignLeft, chip)
        # speech bubble above the head
        text = self.bubble
        if text:
            f2 = QFont(theme.FONT_UI, 9)
            p.setFont(f2)
            fm2 = QFontMetrics(f2)
            maxw = w - 28
            prefix = "Você: " if self.bubble_user else ""
            r = fm2.boundingRect(0, 0, maxw - 20, 1000, Qt.TextWordWrap, prefix + text)
            lines_h = min(r.height(), fm2.lineSpacing() * 5)
            bw = min(maxw, max(120, r.width() + 22))
            bh = lines_h + 16
            br = QRectF((w - bw) / 2, max(4, sprite_top - bh + 6), bw, bh)
            path = QPainterPath()
            path.addRoundedRect(br, 12, 12)
            tail = QPainterPath()
            cx = w / 2 + 18
            tail.moveTo(cx - 8, br.bottom() - 1)
            tail.lineTo(cx + 6, br.bottom() + 11)
            tail.lineTo(cx + 8, br.bottom() - 1)
            path = path.united(tail)
            p.setBrush(QColor(255, 255, 255, 238) if not self.bubble_user else QColor(43, 33, 70, 235))
            p.setPen(QPen(color if not self.bubble_user else QColor(C["border"]), 1.2))
            p.drawPath(path)
            p.setPen(QColor("#1B1430") if not self.bubble_user else QColor(C["muted"]))
            p.drawText(br.adjusted(10, 8, -10, -8), Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop,
                       self._elide(fm2, prefix + text, int(br.width() - 20), 5))
        p.end()

    @staticmethod
    def _elide(fm: QFontMetrics, text: str, width: int, lines: int) -> str:
        """Keep the END of a long answer visible (the latest sentence is what is being spoken)."""
        words, out = text.split(), ""
        for wd in reversed(words):
            cand = (wd + " " + out).strip()
            if fm.boundingRect(0, 0, width, 10000, Qt.TextWordWrap, cand).height() > fm.lineSpacing() * lines:
                return "… " + out
            out = cand
        return out

    # ---------------------------------------------------------------- moving
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            self._drag = None
            self.win.store.set_setting("live.chibi.pos", [self.x(), self.y()])

    def closeEvent(self, e):
        self._timer.stop()
        self.win.stop_live()
        super().closeEvent(e)
