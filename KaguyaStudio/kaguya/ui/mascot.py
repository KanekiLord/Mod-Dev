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
    "claude": {"name": "Miwa", "agent": "Claude Code", "folder": "claude", "prefix": "claude_feminina", "accent": C["amber"],
               "expressions": ["neutra", "feliz", "pensando", "falando", "surpresa", "piscando", "focada", "sucesso", "cafe"],
               "states": {"idle": "neutra", "running": "focada", "success": "sucesso", "error": "surpresa",
                          "cancelled": "pensando", "limit": "cafe", "speaking": "falando", "listening": "piscando",
                          "thinking": "pensando", "approved": "feliz", "rejected": "pensando"}},
}
# Alternative art sets. Kaguya V2 (9 expressions, 2026-11) is the default; V1 (18 + animation
# frames) stays available. Original files are never modified.
VARIANTS = {
    "codex": {
        "v2": {"folder": "kaguya_v2", "prefix": "kaguya", "label": "Kaguya V2 (9 expressões)", "animated": False,
               "expressions": ["neutra", "feliz", "pensando", "falando", "surpresa", "entediada", "apaixonada",
                               "confiante", "dormindo"],
               "states": {"idle": "neutra", "running": "pensando", "success": "feliz", "error": "surpresa",
                          "cancelled": "entediada", "limit": "dormindo", "speaking": "falando", "listening": "surpresa",
                          "thinking": "pensando", "approved": "confiante", "rejected": "entediada"}},
        "v1": {"label": "Kaguya V1 (18 expressões + animações)", "animated": True},
        # portraits the user sent with real transparency (2026-11): smooth art, not pixel art → no crisp cut-out
        "v3": {"folder": "kaguya_v3", "prefix": "kaguya", "label": "Kaguya V3 (retrato, fala e gestos)",
               "animated": False, "crisp": False,
               "expressions": ["neutra", "falando", "feliz", "surpresa", "explicando", "carinhosa", "confiante",
                               "sorriso", "oferecendo"],
               "states": {"idle": "neutra", "running": "sorriso", "success": "feliz", "error": "surpresa",
                          "cancelled": "sorriso", "limit": "sorriso", "speaking": "falando", "listening": "neutra",
                          "thinking": "sorriso", "approved": "confiante", "rejected": "explicando"}},
    },
    "claude": {
        "v2": {"folder": "miwa_v2", "prefix": "miwa", "label": "Miwa V2 (fala e gestos)", "animated": False,
               "expressions": ["neutra", "feliz", "pensando", "falando", "surpresa", "explicando"],
               "states": {"idle": "neutra", "running": "pensando", "success": "feliz", "error": "surpresa",
                          "cancelled": "pensando", "limit": "pensando", "speaking": "falando", "listening": "neutra",
                          "thinking": "pensando", "approved": "feliz", "rejected": "explicando"}},
        "v1": {"label": "Miwa V1 (9 expressões)"},
    },
}
DEFAULT_VARIANT = {"codex": "v2", "claude": "v2"}

# Talking animations (mouth + gestures) played while the voice is actually speaking.
# frames are 1-based indexes; weight = how often the sequence is chosen.
TALK = {
    ("codex", "v2"): {"path": "fala/{seq}/{seq}_{i:02d}.png", "sequences": {
        "talk_basic": {"frames": [1, 2, 3, 4, 3, 2], "ms": 150, "weight": 4},
        "talk_explaining": {"frames": [1, 2, 3, 4, 5, 6], "ms": 160, "weight": 2},
        "talk_warm": {"frames": [1, 2, 3, 4, 5, 6], "ms": 170, "weight": 2}}},
    ("codex", "v3"): {"path": "fala/{seq}/{seq}_{i:02d}.png", "sequences": {   # frame 1 = mouth closed
        "retrato_fala": {"frames": [1, 2, 3, 4, 3, 2], "ms": 150, "weight": 4},
        "retrato_explicando": {"frames": [1, 2, 3, 4, 5, 6], "ms": 170, "weight": 2},
        "retrato_animada": {"frames": [1, 2, 3, 4, 5, 6], "ms": 170, "weight": 2}}},
    ("claude", "v2"): {"path": "fala/{seq}/{seq}_{i:02d}.png", "sequences": {
        "fala_normal": {"frames": [1, 2, 3, 4], "ms": [220, 140, 150, 180], "weight": 4},
        "explicando": {"frames": [1, 2, 3, 4], "ms": [220, 140, 150, 180], "weight": 2},
        "pensando_falando": {"frames": [1, 2, 3, 4], "ms": [220, 140, 150, 180], "weight": 1},
        "animada_acenando": {"frames": [1, 2, 3, 4], "ms": [220, 140, 150, 180], "weight": 1}}},
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
    variant: str = ""
    talk: bool = True            # mouth/gesture animation while speaking


class Mascot(QObject):
    changed = Signal()
    open_chat = Signal(str)
    open_studio = Signal()

    def __init__(self, agent: str, prefs_path: Path, parent=None):
        super().__init__(parent)  # owned by the main window: destroyed on the UI thread, never by a GC elsewhere
        self.agent = agent
        self.prefs_path = prefs_path
        self.prefs = self._load_prefs()
        if not self.prefs.variant or self.prefs.variant not in VARIANTS.get(agent, {}):
            self.prefs.variant = DEFAULT_VARIANT.get(agent, "")
        self.state = "idle"
        self.expression = self.profile["states"]["idle"]
        self._cache: dict[tuple[str, bool], QImage] = {}
        self.window: FloatingMascot | None = None
        self.tick = 0
        self.talk_frame: Path | None = None
        self._talk_seq: list[tuple[Path, int]] = []
        self._talk_pos = 0
        self._talk_timer = QTimer(self)
        self._talk_timer.setSingleShot(True)
        self._talk_timer.timeout.connect(self._talk_step)
        self.level_source = None     # callable → loudness 0..1 of the voice being heard (set by the main window)

    def _load_prefs(self) -> MascotPrefs:
        try:
            raw = json.loads(self.prefs_path.read_text(encoding="utf-8"))
            return MascotPrefs(**{k: v for k, v in raw.items() if k in MascotPrefs.__dataclass_fields__})
        except (OSError, ValueError, TypeError):
            return MascotPrefs()

    @property
    def profile(self) -> dict:
        base = PROFILES[self.agent]
        override = VARIANTS.get(self.agent, {}).get(self.prefs.variant)
        return {**base, **override} if override else base

    def variants(self) -> list[tuple[str, str]]:
        return [(k, v["label"]) for k, v in VARIANTS.get(self.agent, {}).items()]

    def set_variant(self, variant: str) -> None:
        if variant in VARIANTS.get(self.agent, {}):
            self.prefs.variant = variant
            self.save()
            self.set_state(self.state)

    def save(self):
        self.prefs_path.parent.mkdir(parents=True, exist_ok=True)
        self.prefs_path.write_text(json.dumps(asdict(self.prefs), indent=2), encoding="utf-8")

    # ------------------------------------------------------------------ talking
    def talk_config(self) -> dict | None:
        return TALK.get((self.agent, self.prefs.variant)) if self.prefs.talk else None

    def talk_sequence(self, name: str | None = None) -> list[tuple[Path, int]]:
        """[(frame path, duration ms)] of one pass of a talking sequence (random by weight if no name)."""
        import random
        cfg = self.talk_config()
        if not cfg:
            return []
        seqs = cfg["sequences"]
        if name is None:
            names = list(seqs)
            name = random.choices(names, weights=[seqs[n].get("weight", 1) for n in names])[0]
        spec = seqs[name]
        base = ASSETS / "mascots" / self.profile["folder"]
        ms = spec["ms"]
        out = []
        for k, i in enumerate(spec["frames"]):
            p = base / cfg["path"].format(seq=name, i=i)
            if p.is_file():
                out.append((p, ms[k % len(ms)] if isinstance(ms, list) else ms))
        return out

    def _start_talk(self):
        self._talk_seq, self._talk_pos = self.talk_sequence(), 0
        if self._talk_seq:
            self._talk_step()

    def _stop_talk(self):
        self._talk_timer.stop()
        self.talk_frame = None
        self._talk_seq = []

    def _talk_step(self):
        if self.state != "speaking":
            self._stop_talk()
            return
        level = self.level_source() if self.level_source else None
        if level is not None and level < 0.08 and self._talk_seq:
            # a pause in the real audio: close the mouth (first frame) and wait, instead of moving on its own
            self.talk_frame = self._talk_seq[0][0]
            self._talk_timer.start(60)
            self.changed.emit()
            if self.window:
                self.window.update()
            return
        if self._talk_pos >= len(self._talk_seq):  # one pass done: next gesture
            self._talk_seq, self._talk_pos = self.talk_sequence(), 0
            if not self._talk_seq:
                return
        self.talk_frame, ms = self._talk_seq[self._talk_pos]
        self._talk_pos += 1
        self._talk_timer.start(ms)
        self.changed.emit()
        if self.window:
            self.window.update()

    def sprite_path(self, expression: str) -> Path:
        if self.talk_frame is not None and self.state == "speaking":
            return self.talk_frame
        base = ASSETS / "mascots" / self.profile["folder"]
        if self.prefs.animations and self.profile.get("animated", self.agent == "codex"):
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
        crisp = self.prefs.crisp and self.profile.get("crisp", True)
        key = (str(path), crisp)
        if key not in self._cache:
            self._cache[key] = load_sprite(path, crisp)
        return self._cache[key]

    def set_state(self, state: str):
        was = self.state
        self.state = state
        self.expression = self.profile["states"].get(state, "neutra")
        if state == "speaking" and was != "speaking":
            self._start_talk()
        elif state != "speaking":
            self._stop_talk()
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
        if self.m.variants():
            vmenu = menu.addMenu("Visual")
            for key, text in self.m.variants():
                act = QAction(text, vmenu, checkable=True, checked=self.m.prefs.variant == key)
                act.triggered.connect(lambda _=False, k=key: (self.m.set_variant(k), self.update()))
                vmenu.addAction(act)
        if self.m.talk_config() is not None or TALK.get((self.m.agent, self.m.prefs.variant)):
            talk = QAction("Boca e gestos ao falar", menu, checkable=True, checked=self.m.prefs.talk)
            talk.toggled.connect(lambda on: (setattr(self.m.prefs, "talk", on), self.m.save()))
            menu.addAction(talk)
        if self.m.profile.get("animated"):
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
