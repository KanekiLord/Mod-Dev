"""Kaguya Music side dock: a thin tab fixed to the screen edge that slides open horizontally on click.

States (spec 05): collapsed (only the tab), preview (hover highlight + tooltip), expanded (player), pinned
(stays open), hidden (tray/Music page brings it back). Edge left/right, vertical position by dragging the tab,
all persisted. Works with the Studio minimized or in the tray.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QSlider, QVBoxLayout, QWidget

from ..music import winmedia
from . import theme
from .theme import C
from .widgets import button, label

TAB_W, TAB_H = 26, 92
PANEL_W, PANEL_H = 500, 188


def fmt(ms: int) -> str:
    s = max(0, int(ms or 0)) // 1000
    return f"{s // 60}:{s % 60:02d}"


class Cover(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(84, 84)
        self.image = None

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 12, 12)
        p.setClipPath(path)
        if self.image is not None and not self.image.isNull():
            p.drawImage(self.rect(), self.image.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
        else:  # night sky with moon (drawn, no bitmap with text)
            g = QLinearGradient(0, 0, 0, self.height())
            g.setColorAt(0, QColor("#2A1F4A"))
            g.setColorAt(1, QColor("#120D1F"))
            p.fillRect(self.rect(), g)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(C["gold"]))
            p.drawEllipse(QRectF(46, 14, 24, 24))
            p.setBrush(QColor("#2A1F4A"))
            p.drawEllipse(QRectF(52, 10, 22, 22))
            p.drawPixmap(14, 44, theme.pixmap("music", C["violet"], 28))


class MusicDock(QWidget):
    def __init__(self, win, player):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.win, self.player = win, player
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle("Kaguya Music")
        st = win.store
        self.edge = st.get_setting("music.dock.edge", "right") if st.get_setting("music.dock.edge", "right") in ("left", "right") else "right"
        self.rel_y = float(st.get_setting("music.dock.y", 0.62) or 0.62)
        self.pinned = bool(st.get_setting("music.dock.pinned", False))
        self.source = "local"
        self.hover = False
        self.progress = 1.0 if self.pinned else 0.0   # 0 = collapsed, 1 = expanded
        self._drag: QPoint | None = None
        self._drag_moved = False
        self._seeking = False
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(220)
        self.anim.valueChanged.connect(self._set_progress)
        self._collapse_timer = QTimer(self, singleShot=True, interval=4000)
        self._collapse_timer.timeout.connect(lambda: self.collapse() if not self.pinned and not self.underMouse() else None)
        self._build()
        player.changed.connect(self.refresh)
        player.position.connect(self._position)
        self._place()
        self.refresh()

    # ------------------------------------------------------------------ build
    def _build(self):
        self.panel = QWidget(self)
        self.panel.setObjectName("musicPanel")
        self.panel.setAttribute(Qt.WA_TranslucentBackground)
        lay = QVBoxLayout(self.panel)
        lay.setContentsMargins(14, 12, 14, 10)
        lay.setSpacing(6)
        top = QHBoxLayout()
        self.cover = Cover()
        top.addWidget(self.cover)
        info = QVBoxLayout()
        info.setSpacing(2)
        self.title = QLabel("Kaguya Music")
        self.title.setStyleSheet(f"color: {C['text']}; font-size: 11pt; font-weight: 700;")
        self.artist = QLabel("")
        self.artist.setStyleSheet(f"color: {C['muted']}; font-size: 9pt;")
        srow = QHBoxLayout()
        srow.setSpacing(4)
        self.src_local = button("Local", "folder", "ghost", "Suas músicas locais, tocadas pelo Studio", checkable=True)
        self.src_win = button("Windows", "window", "ghost", "Teclas de mídia do Windows: controlam o app que estiver tocando "
                              "(YouTube no navegador, Spotify, Amazon Music…). O Studio não lê o que esses apps tocam.",
                              checkable=True)
        self.src_local.clicked.connect(lambda: self.set_source("local"))
        self.src_win.clicked.connect(lambda: self.set_source("windows"))
        srow.addWidget(self.src_local)
        srow.addWidget(self.src_win)
        srow.addStretch(1)
        info.addWidget(self.title)
        info.addWidget(self.artist)
        info.addLayout(srow)
        top.addLayout(info, 1)
        tools = QVBoxLayout()
        self.queue_btn = button("", "list", "ghost", "Fila")
        self.queue_btn.clicked.connect(self.show_queue)
        self.pin_btn = button("", "pin", "ghost", "Fixar aberta", checkable=True)
        self.pin_btn.setChecked(self.pinned)
        self.pin_btn.toggled.connect(self.set_pinned)
        self.hide_btn = button("", "x", "ghost", "Esconder a bandeja (volta pelo ícone na bandeja do Windows ou pela página Kaguya Music)")
        self.hide_btn.clicked.connect(lambda: self.win.set_music_dock_visible(False))
        for b in (self.queue_btn, self.pin_btn, self.hide_btn):
            b.setFixedSize(30, 28)
            tools.addWidget(b)
        top.addLayout(tools)
        lay.addLayout(top)
        prow = QHBoxLayout()
        self.t_pos = label("0:00", "dim")
        self.t_dur = label("0:00", "dim")
        self.seek = QSlider(Qt.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.setAccessibleName("Progresso da música")
        self.seek.sliderPressed.connect(lambda: setattr(self, "_seeking", True))
        self.seek.sliderReleased.connect(self._seek_release)
        prow.addWidget(self.t_pos)
        prow.addWidget(self.seek, 1)
        prow.addWidget(self.t_dur)
        lay.addLayout(prow)
        crow = QHBoxLayout()
        crow.setSpacing(4)
        self.b_shuffle = button("", "shuffle", "ghost", "Aleatório", checkable=True)
        self.b_shuffle.toggled.connect(lambda on: self.player.set_shuffle(on))
        self.b_prev = button("", "skip-back", "ghost", "Anterior")
        self.b_prev.clicked.connect(self.prev)
        self.b_play = button("", "play", "primary", "Tocar/pausar")
        self.b_play.setFixedSize(44, 40)
        self.b_play.clicked.connect(self.toggle)
        self.b_next = button("", "skip-forward", "ghost", "Próxima")
        self.b_next.clicked.connect(self.next)
        self.b_repeat = button("", "repeat", "ghost", "Repetir: desligado")
        self.b_repeat.clicked.connect(lambda: self.player.cycle_repeat())
        for b in (self.b_shuffle, self.b_prev, self.b_play, self.b_next, self.b_repeat):
            crow.addWidget(b)
        crow.addStretch(1)
        crow.addWidget(theme_icon("volume"))
        self.vol = QSlider(Qt.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setFixedWidth(110)
        self.vol.setAccessibleName("Volume da música")
        self.vol.valueChanged.connect(lambda v: self.player.set_volume(v) if not self._syncing else None)
        crow.addWidget(self.vol)
        lay.addLayout(crow)
        self._syncing = False

    # ---------------------------------------------------------------- geometry
    def _screen_rect(self) -> QRect:
        screen = QGuiApplication.screenAt(self.geometry().center()) or QGuiApplication.primaryScreen()
        return screen.availableGeometry()

    def _place(self):
        geo = self._screen_rect()
        w = int(TAB_W + PANEL_W * self.progress)
        h = PANEL_H if self.progress > 0.02 else TAB_H
        center_y = geo.top() + int(geo.height() * self.rel_y)
        y = max(geo.top(), min(center_y - h // 2, geo.bottom() - h))
        x = geo.right() - w + 1 if self.edge == "right" else geo.left()
        self.setGeometry(x, y, w, h)
        self.panel.setVisible(self.progress > 0.35)
        px = TAB_W if self.edge == "right" else 0   # the tab sits on the inner side of the open panel
        self.panel.setGeometry(px, 0, PANEL_W, PANEL_H)
        self.update()

    def _set_progress(self, v):
        self.progress = float(v)
        self._place()

    def expand(self):
        self._animate(1.0)

    def collapse(self):
        if not self.pinned:
            self._animate(0.0)

    def _animate(self, target: float):
        self.anim.stop()
        self.anim.setStartValue(self.progress)
        self.anim.setEndValue(target)
        self.anim.start()

    def set_pinned(self, on: bool):
        self.pinned = bool(on)
        self.win.store.set_setting("music.dock.pinned", self.pinned)
        if on:
            self.expand()

    def set_edge(self, edge: str):
        self.edge = edge if edge in ("left", "right") else "right"
        self.win.store.set_setting("music.dock.edge", self.edge)
        self._place()

    # ------------------------------------------------------------------ paint
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h = self.height()
        tab_x = self._tab_rect().x()
        # panel background
        if self.progress > 0.02:
            body = QRectF(0.5, 0.5, self.width() - 1, h - 1)
            path = QPainterPath()
            path.addRoundedRect(body, 16, 16)
            g = QLinearGradient(0, 0, 0, h)
            g.setColorAt(0, QColor(42, 31, 74, 245))
            g.setColorAt(1, QColor(20, 14, 34, 245))
            p.fillPath(path, g)
            p.setPen(QPen(QColor(C["violet"]), 1.4))
            p.drawPath(path)
        # tab
        tab = QRectF(tab_x + 0.5, (h - TAB_H) / 2 + 0.5, TAB_W - 1, TAB_H - 1)
        tpath = QPainterPath()
        tpath.addRoundedRect(tab, 10, 10)
        base = QColor(C["violet_d"] if self.hover else "#2A1F4A")
        base.setAlpha(250)
        p.fillPath(tpath, base)
        p.setPen(QPen(QColor(C["gold"] if self.player.playing else C["violet"]), 1.4))
        p.drawPath(tpath)
        p.drawPixmap(int(tab.center().x()) - 8, int(tab.top()) + 12, theme.pixmap("music", C["gold"], 16))
        # tiny equalizer while playing
        if self.player.playing:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(C["gold"]))
            import math
            import time
            t = time.monotonic() * 6
            for i in range(3):
                bh = 6 + int(8 * abs(math.sin(t + i * 1.3)))
                p.drawRoundedRect(QRectF(tab.center().x() - 8 + i * 6, tab.bottom() - 14 - bh, 4, bh), 1.5, 1.5)
        arrow = "‹" if (self.edge == "right") == (self.progress <= 0.02) else "›"
        p.setPen(QColor(C["muted"]))
        p.drawText(QRectF(tab.left(), tab.center().y() - 10, tab.width(), 20), Qt.AlignCenter, arrow)

    def _tab_rect(self) -> QRect:
        h = self.height()
        if self.edge == "right":
            x = self.width() - TAB_W if self.progress <= 0.02 else 0
        else:
            x = 0 if self.progress <= 0.02 else self.width() - TAB_W
        return QRect(x, (h - TAB_H) // 2, TAB_W, TAB_H)

    # ------------------------------------------------------------------ mouse
    def enterEvent(self, e):
        self.hover = True
        self._collapse_timer.stop()
        s = self.player.status()
        self.setToolTip(f"♪ {s['title']} — {s['artist']}" if s["title"] else "Kaguya Music — clique para abrir")
        self.update()

    def leaveEvent(self, e):
        self.hover = False
        if self.progress > 0.5 and not self.pinned:
            self._collapse_timer.start()
        self.update()

    def mousePressEvent(self, e):
        if self._tab_rect().contains(e.position().toPoint()):
            self._drag = e.globalPosition().toPoint()
            self._drag_moved = False

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            dy = e.globalPosition().toPoint().y() - self._drag.y()
            if abs(dy) > 4:
                self._drag_moved = True
                geo = self._screen_rect()
                cy = self.geometry().center().y() + dy
                self.rel_y = max(0.05, min(0.95, (cy - geo.top()) / max(1, geo.height())))
                self._drag = e.globalPosition().toPoint()
                self._place()

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            if self._drag_moved:
                self.win.store.set_setting("music.dock.y", round(self.rel_y, 3))
            elif self.progress < 0.5:
                self.expand()
            elif not self.pinned:
                self.collapse()
        self._drag = None

    # --------------------------------------------------------------- controls
    def set_source(self, src: str):
        self.source = src if src == "local" or winmedia.available() else "local"
        if src == "windows" and not winmedia.available():
            self.win.toast("As teclas de mídia do Windows só existem no Windows.")
        self.refresh()

    def toggle(self):
        if self.source == "windows":
            winmedia.press("play_pause")
        elif self.player.playing:
            self.player.pause()
        elif not self.player.resume():
            self.win.toast("Biblioteca vazia: adicione uma pasta em Kaguya Music.")

    def next(self):
        winmedia.press("next") if self.source == "windows" else self.player.next()

    def prev(self):
        winmedia.press("previous") if self.source == "windows" else self.player.previous()

    def show_queue(self):
        menu = QMenu(self)
        if not self.player.queue:
            menu.addAction("Fila vazia").setEnabled(False)
        for i, tid in enumerate(self.player.queue[:40]):
            t = self.player.lib.get(tid)
            if t:
                act = menu.addAction(("▶ " if i == self.player.index else "   ") + t.label[:60])
                act.triggered.connect(lambda _=False, k=i: self.player._play_index(k))
        menu.addSeparator()
        menu.addAction("Abrir Kaguya Music", lambda: (self.win.show_from_tray(), self.win.go("music")))
        menu.exec(self.queue_btn.mapToGlobal(self.queue_btn.rect().bottomLeft()))

    def _seek_release(self):
        self._seeking = False
        self.player.seek(self.seek.value())

    def _position(self, ms: int, dur: int):
        if self.source != "local":
            return
        if not self._seeking:
            self.seek.setRange(0, max(0, dur))
            self.seek.setValue(ms)
        self.t_pos.setText(fmt(ms))
        self.t_dur.setText(fmt(dur))
        if self.player.playing and self.progress <= 0.02:
            self.update()  # animate the tab equalizer

    def refresh(self):
        pl = self.player
        self.src_local.setChecked(self.source == "local")
        self.src_win.setChecked(self.source == "windows")
        self.src_win.setVisible(True)
        local = self.source == "local"
        for w in (self.seek, self.t_pos, self.t_dur, self.b_shuffle, self.b_repeat, self.vol, self.queue_btn):
            w.setEnabled(local)
        if local:
            t = pl.track
            self.title.setText((t.title if t else "Kaguya Music")[:48])
            self.artist.setText((t.artist if t else ("Biblioteca vazia — adicione uma pasta" if pl.lib.count() == 0
                                                     else "Clique em tocar"))[:60])
            self.cover.image = pl.cover
        else:
            self.title.setText("App de mídia do Windows")
            self.artist.setText("Play/pausa, próxima e anterior pelo Windows")
            self.cover.image = None
        self.cover.update()
        self.b_play.setIcon(theme.icon("pause" if (local and pl.playing) else "play", C["ink"]))
        self.b_shuffle.blockSignals(True)
        self.b_shuffle.setChecked(pl.shuffle and local)
        self.b_shuffle.blockSignals(False)
        # visible state: gold when on (it used to look the same — gray — on and off)
        self.b_shuffle.setIcon(theme.icon("shuffle", C["gold"] if (pl.shuffle and local) else C["muted"]))
        self.b_shuffle.setToolTip("Aleatório: ligado" if pl.shuffle else "Aleatório: desligado" if local else
                                  "No modo App do Windows, o aleatório é do próprio app (Spotify, Media Player…). "
                                  "Use \"Kaguya Music\" para o aleatório do Studio.")
        rep = {"off": ("repeat", "Repetir: desligado", C["muted"]), "all": ("repeat", "Repetir: fila", C["gold"]),
               "one": ("repeat-one", "Repetir: esta música", C["gold"])}[pl.repeat]
        self.b_repeat.setIcon(theme.icon(rep[0], rep[2]))
        self.b_repeat.setToolTip(rep[1])
        self._syncing = True
        self.vol.setValue(pl.volume)
        self._syncing = False
        self.update()


def theme_icon(name: str) -> QLabel:
    lb = QLabel()
    lb.setPixmap(theme.pixmap(name, C["muted"], 16))
    return lb
