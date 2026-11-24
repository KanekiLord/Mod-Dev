"""Mascots: Kaguya (Codex) and Claude, docked in the Studio and as floating desktop windows.

Floating windows use per-pixel alpha (``WA_TranslucentBackground``) — real transparency on
Windows, instead of Tk's single colour key that produced dark squares/fringes. Each mascot
reacts only to the state of *its own* CLI.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from pathlib import Path

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer, Signal, QObject
from PySide6.QtGui import QAction, QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from ..appdirs import ASSETS
from . import theme
from .theme import C
from .widgets import load_sprite

PROFILES = {
    "codex": {"name": "Kaguya", "agent": "Codex", "folder": "kaguya", "prefix": "kaguya", "accent": C["violet"],
              "expressions": ["neutra", "feliz", "sorriso_sutil", "falando", "surpresa", "curiosa", "pensando", "confiante",
                              "provocante", "apaixonada", "emburrada", "triste", "envergonhada", "preocupada", "cansada",
                              "chorando", "determinada", "rindo"],
              "states": {"idle": "neutra", "running": "determinada", "success": "feliz", "error": "preocupada",
                         "cancelled": "emburrada", "limit": "cansada", "speaking": "falando", "listening": "curiosa",
                         "thinking": "pensando", "approved": "confiante", "rejected": "triste"}},
    "claude": {"name": "Claude", "agent": "Claude Code", "folder": "claude", "prefix": "claude_feminina", "accent": C["amber"],
               "expressions": ["neutra", "feliz", "pensando", "falando", "surpresa", "piscando", "focada", "sucesso", "cafe"],
               "states": {"idle": "neutra", "running": "focada", "success": "sucesso", "error": "surpresa",
                          "cancelled": "pensando", "limit": "cafe", "speaking": "falando", "listening": "piscando",
                          "thinking": "pensando", "approved": "feliz", "rejected": "pensando"}},
}
STATE_LABELS = {"idle": "Aguardando", "running": "Trabalhando", "success": "Concluiu o turno", "error": "Erro",
                "cancelled": "Interrompido", "limit": "Limite atingido", "speaking": "Falando", "listening": "Ouvindo",
                "thinking": "Pensando", "approved": "Aprovado", "rejected": "Reprovado"}


@dataclass
class MascotPrefs:
    visible: bool = False
    x: int = -1
    y: int = -1
    scale: int = 2
    topmost: bool = True
    crisp: bool = True
    animations: bool = False


class Mascot(QObject):
    changed = Signal()
    open_chat = Signal(str)
    open_studio = Signal()

    def __init__(self, agent: str, prefs_path: Path):
        super().__init__()
        self.agent = agent
        self.profile = PROFILES[agent]
        self.prefs_path = prefs_path
        self.prefs = self._load_prefs()
        self.state = "idle"
        self.expression = self.profile["states"]["idle"]
        self._cache: dict[tuple[str, bool], QImage] = {}
        self.window: FloatingMascot | None = None
        self.tick = 0

    def _load_prefs(self) -> MascotPrefs:
        try:
            raw = json.loads(self.prefs_path.read_text(encoding="utf-8"))
            return MascotPrefs(**{k: v for k, v in raw.items() if k in MascotPrefs.__dataclass_fields__})
        except (OSError, ValueError, TypeError):
            return MascotPrefs()

    def save(self):
        self.prefs_path.parent.mkdir(parents=True, exist_ok=True)
        self.prefs_path.write_text(json.dumps(asdict(self.prefs), indent=2), encoding="utf-8")

    def sprite_path(self, expression: str) -> Path:
        base = ASSETS / "mascots" / self.profile["folder"]
        if self.prefs.animations and self.agent == "codex":
            seq = None
            if expression == "falando":
                seq, idx = "talk", (self.tick // 3) % 3 + 1
            elif expression == "neutra":
                t = self.tick % 58
                seq, idx = ("blink", t - 47) if 48 <= t < 51 else ("idle", (self.tick // 6) % 4 + 1)
            if seq:
                cand = base / "animacoes" / f"{seq}_{idx:02d}.png"
                if cand.is_file():
                    return cand
        p = base / "expressoes" / f"{self.profile['prefix']}_{expression}.png"
        return p if p.is_file() else base / "expressoes" / f"{self.profile['prefix']}_neutra.png"

    def image(self) -> QImage:
        path = self.sprite_path(self.expression)
        key = (str(path), self.prefs.crisp)
        if key not in self._cache:
            self._cache[key] = load_sprite(path, self.prefs.crisp)
        return self._cache[key]

    def set_state(self, state: str):
        self.state = state
        self.expression = self.profile["states"].get(state, "neutra")
        self.changed.emit()
        if self.window:
            self.window.update()

    def set_expression(self, expression: str):
        if expression in self.profile["expressions"]:
            self.expression = expression
            self.changed.emit()
            if self.window:
                self.window.update()

    def advance(self):
        self.tick += 1
        if self.prefs.animations or self.state == "running":
            self.changed.emit()
            if self.window:
                self.window.update()

    @property
    def label(self) -> str:
        return STATE_LABELS.get(self.state, self.state)

    # ---------------------------------------------------------------- window
    def show_window(self):
        if self.window is None:
            self.window = FloatingMascot(self)
        self.window.place()
        self.window.show()
        self.window.raise_()
        self.prefs.visible = True
        self.save()

    def hide_window(self):
        if self.window:
            self.window.hide()
        self.prefs.visible = False
        self.save()

    def toggle_window(self):
        if self.window and self.window.isVisible():
            self.hide_window()
        else:
            self.show_window()


class FloatingMascot(QWidget):
    FOOTER = 30

    def __init__(self, mascot: Mascot):
        flags = Qt.FramelessWindowHint | Qt.Tool
        if mascot.prefs.topmost:
            flags |= Qt.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.m = mascot
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle(f"{mascot.profile['name']} — {mascot.profile['agent']}")
        self._drag: QPoint | None = None
        self.resize_to_scale()

    def resize_to_scale(self):
        s = 128 * self.m.prefs.scale
        self.setFixedSize(s, s + self.FOOTER)

    def place(self):
        screen = QApplication.primaryScreen().availableGeometry()
        w, h = self.width(), self.height()
        x, y = self.m.prefs.x, self.m.prefs.y
        if x < 0 or y < 0:
            offset = 0 if self.m.agent == "codex" else w + 24
            x, y = screen.right() - w - 40 - offset, screen.bottom() - h - 40
        x = max(screen.left(), min(x, screen.right() - w))
        y = max(screen.top(), min(y, screen.bottom() - h))
        self.move(x, y)

    def paintEvent(self, e):
        p = QPainter(self)
        img = self.m.image()
        s = self.m.prefs.scale
        if not img.isNull():
            dpr = self.devicePixelRatioF()
            scaled = img.scaled(int(img.width() * s * dpr), int(img.height() * s * dpr), Qt.KeepAspectRatio,
                                Qt.FastTransformation)
            bob = 1 if (self.m.state == "running" and (self.m.tick // 4) % 2) else 0
            target = QRectF(0, bob, 128 * s, 128 * s)
            p.drawImage(target, scaled)
        p.setRenderHint(QPainter.Antialiasing)
        footer = QRectF(10, self.height() - self.FOOTER + 3, self.width() - 20, self.FOOTER - 7)
        path = QPainterPath()
        path.addRoundedRect(footer, 10, 10)
        p.fillPath(path, QColor(20, 14, 33, 235))
        p.setPen(QPen(QColor(self.m.profile["accent"]), 1))
        p.drawPath(path)
        p.setPen(QColor(C["text"]))
        p.setFont(theme.font(8, QFont.DemiBold))
        p.drawText(footer, Qt.AlignCenter, f"{self.m.profile['name'].upper()}  •  {self.m.label}")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            self._drag = None
            self.m.prefs.x, self.m.prefs.y = self.x(), self.y()
            self.m.save()

    def mouseDoubleClickEvent(self, e):
        self.m.open_chat.emit(self.m.agent)

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        menu.addAction(theme.icon("chat", C["text"]), "Chat rápido", lambda: self.m.open_chat.emit(self.m.agent))
        menu.addAction(theme.icon("window", C["text"]), "Abrir Kaguya Studio", self.m.open_studio.emit)
        menu.addSeparator()
        top = QAction("Sempre visível", menu, checkable=True, checked=self.m.prefs.topmost)
        top.toggled.connect(self._set_topmost)
        menu.addAction(top)
        crisp = QAction("Recorte nítido (pixel art)", menu, checkable=True, checked=self.m.prefs.crisp)
        crisp.toggled.connect(self._set_crisp)
        menu.addAction(crisp)
        if self.m.agent == "codex":
            anim = QAction("Animações experimentais", menu, checkable=True, checked=self.m.prefs.animations)
            anim.toggled.connect(self._set_anim)
            menu.addAction(anim)
        size = menu.addMenu("Tamanho")
        for s in (1, 2, 3):
            act = QAction(f"{s}× ({128 * s}px)", size, checkable=True, checked=self.m.prefs.scale == s)
            act.triggered.connect(lambda _=False, s=s: self._set_scale(s))
            size.addAction(act)
        expr = menu.addMenu(f"Expressões ({len(self.m.profile['expressions'])})")
        for ex in self.m.profile["expressions"]:
            expr.addAction(ex.replace("_", " ").capitalize(), lambda ex=ex: self.m.set_expression(ex))
        menu.addSeparator()
        menu.addAction("Ocultar mascote", self.m.hide_window)
        menu.exec(e.globalPos())

    def _set_topmost(self, on):
        self.m.prefs.topmost = on
        self.m.save()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        self.show()

    def _set_crisp(self, on):
        self.m.prefs.crisp = on
        self.m.save()
        self.m.changed.emit()
        self.update()

    def _set_anim(self, on):
        self.m.prefs.animations = on
        self.m.save()

    def _set_scale(self, s):
        self.m.prefs.scale = s
        self.m.save()
        self.resize_to_scale()
        self.place()
        self.update()
