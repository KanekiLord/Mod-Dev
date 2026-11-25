"""Reusable components of the Kaguya design system."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal, Property, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (QBrush, QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
                           QRadialGradient)
from PySide6.QtWidgets import (QAbstractButton, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)

from ..appdirs import ASSETS
from . import theme
from .theme import C


def label(text: str = "", role: str | None = None, wrap: bool = False, selectable: bool = False) -> QLabel:
    lb = QLabel(text)
    if role:
        lb.setProperty("role", role)
    lb.setWordWrap(wrap)
    if selectable:
        lb.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
    return lb


def button(text: str, icon_name: str | None = None, kind: str | None = None, tip: str = "", color: str | None = None,
           checkable: bool = False) -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setProperty("kind", kind)
    if icon_name:
        col = color or ("#24170A" if kind == "primary" else C["muted"] if kind in ("ghost", "nav", "chip") else C["text"])
        b.setIcon(theme.icon(icon_name, col, active=C["text"] if kind in ("nav", "chip") else None))
        b.setIconSize(QSize(16, 16))
    if tip:
        b.setToolTip(tip)
    b.setCheckable(checkable)
    b.setCursor(Qt.PointingHandCursor)
    return b


def hline() -> QFrame:
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet(f"background: {C['border_soft']};")
    return f


class Card(QFrame):
    """Rounded surface with subtle vertical gradient, hairline border and optional accent."""

    def __init__(self, parent=None, accent: str | None = None, padding: int = 16, radius: int = 14,
                 glow: bool = False, pattern: bool = False):
        super().__init__(parent)
        self.accent, self.radius, self.pattern = accent, radius, pattern
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(padding, padding, padding, padding)
        self.lay.setSpacing(10)
        if glow:
            fx = QGraphicsDropShadowEffect(self)
            fx.setBlurRadius(28)
            fx.setOffset(0, 6)
            fx.setColor(QColor(0, 0, 0, 120))
            self.setGraphicsEffect(fx)
        self._pattern = None

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, self.radius, self.radius)
        g = QLinearGradient(0, 0, 0, r.height())
        g.setColorAt(0, QColor("#211938"))
        g.setColorAt(1, QColor("#1A1330"))
        p.fillPath(path, g)
        if self.pattern:
            if self._pattern is None:
                self._pattern = theme.svg_pixmap("ornaments/seigaiha.svg", 48, 24)
            p.save()
            p.setClipPath(path)
            p.setOpacity(0.55)
            p.drawTiledPixmap(r.toRect(), self._pattern)
            p.restore()
        pen = QPen(QColor(C["border"]))
        pen.setWidthF(1)
        p.setPen(pen)
        p.drawPath(path)
        if self.accent:
            ac = QColor(self.accent)
            grad = QLinearGradient(r.left(), 0, r.right(), 0)
            ac.setAlpha(0)
            grad.setColorAt(0, ac)
            ac.setAlpha(200)
            grad.setColorAt(0.5, ac)
            ac.setAlpha(0)
            grad.setColorAt(1, ac)
            p.setPen(QPen(QBrush(grad), 1.5))
            p.drawLine(QPointF(r.left() + self.radius, r.top() + 0.75), QPointF(r.right() - self.radius, r.top() + 0.75))


class Pill(QLabel):
    def __init__(self, text: str = "", color: str = C["muted"], bg: str | None = None, icon_name: str | None = None):
        super().__init__()
        self.set(text, color, bg, icon_name)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

    def set(self, text: str, color: str = C["muted"], bg: str | None = None, icon_name: str | None = None):
        bgc = QColor(bg or color)
        if bg is None:
            bgc.setAlpha(38)
        border = QColor(color)
        border.setAlpha(110)
        self.setStyleSheet(f"QLabel {{ color: {color}; background: rgba({bgc.red()},{bgc.green()},{bgc.blue()},{bgc.alpha()});"
                           f" border: 1px solid rgba({border.red()},{border.green()},{border.blue()},{border.alpha()});"
                           f" border-radius: 10px; padding: 2px 9px; font-size: 8pt; font-weight: 600; }}")
        self.setText(text)
        self.setVisible(bool(text))


class Dot(QWidget):
    def __init__(self, color: str = C["dim"], size: int = 9, pulse: bool = False):
        super().__init__()
        self.color, self.size_ = QColor(color), size
        self.setFixedSize(size + 6, size + 6)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.set_pulse(pulse)

    def set_color(self, color: str, pulse: bool | None = None):
        self.color = QColor(color)
        if pulse is not None:
            self.set_pulse(pulse)
        self.update()

    def set_pulse(self, on: bool):
        if on:
            self._timer.start(60)
        else:
            self._timer.stop()
            self._phase = 0
        self.update()

    def _tick(self):
        self._phase = (self._phase + 0.06) % 1.0
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        if self._timer.isActive():
            halo = QColor(self.color)
            halo.setAlpha(int(120 * (1 - self._phase)))
            p.setBrush(halo)
            p.setPen(Qt.NoPen)
            rr = self.size_ / 2 + 3 * self._phase
            p.drawEllipse(c, rr, rr)
        p.setBrush(self.color)
        p.setPen(Qt.NoPen)
        p.drawEllipse(c, self.size_ / 2 - 1, self.size_ / 2 - 1)


class Meter(QWidget):
    """Quota bar: shows used % only when a value is known; otherwise a hatched 'indisponível'."""

    def __init__(self, color: str = C["violet"]):
        super().__init__()
        self.color = QColor(color)
        self.value: float | None = None
        self.setFixedHeight(8)
        self.setMinimumWidth(80)

    def set_value(self, used_percent: float | None):
        self.value = None if used_percent is None else max(0.0, min(100.0, float(used_percent)))
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        bg = QPainterPath()
        bg.addRoundedRect(r, 4, 4)
        p.fillPath(bg, QColor(C["night"]))
        if self.value is None:
            p.setClipPath(bg)
            pen = QPen(QColor(C["border"]), 2)
            p.setPen(pen)
            x = -r.height()
            while x < r.width():
                p.drawLine(QPointF(x, r.height()), QPointF(x + r.height(), 0))
                x += 7
            return
        w = r.width() * self.value / 100
        if w <= 0:
            return
        fg = QPainterPath()
        fg.addRoundedRect(QRectF(0, 0, max(w, 8), r.height()), 4, 4)
        g = QLinearGradient(0, 0, r.width(), 0)
        c1 = QColor(self.color)
        c1.setAlpha(150)
        g.setColorAt(0, c1)
        g.setColorAt(1, self.color)
        if self.value >= 90:
            g.setColorAt(1, QColor(C["danger"]))
        elif self.value >= 75:
            g.setColorAt(1, QColor(C["warning"]))
        p.fillPath(fg, g)


class Stepper(QWidget):
    """Team pipeline: Implementação → Verificação → Revisão → Correção → Veredito."""
    STEPS = [("implementacao", "Código"), ("verificacao", "Testes"), ("revisao", "Revisão"),
             ("correcao", "Ajustes"), ("final", "Veredito")]

    def __init__(self):
        super().__init__()
        self.current = None
        self.done: set[str] = set()
        self.failed = False
        self.cycle_text = ""
        self.setMinimumHeight(58)

    def set_stage(self, stage: str | None, cycle: int = 1, max_cycles: int = 1, failed: bool = False):
        if stage is None:
            self.current, self.done, self.failed, self.cycle_text = None, set(), False, ""
        else:
            if self.current and self.current != stage:
                self.done.add(self.current)
            self.current, self.failed = stage, failed
            self.cycle_text = f"ciclo {cycle}/{max_cycles}" if max_cycles > 1 else ""
            if stage == "final":
                self.done.add("final")
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n = len(self.STEPS)
        w = self.width()
        y = 16
        xs = [18 + i * (w - 36) / (n - 1) for i in range(n)]
        pen = QPen(QColor(C["border"]), 2)
        p.setPen(pen)
        p.drawLine(QPointF(xs[0], y), QPointF(xs[-1], y))
        f = theme.font(7.5, QFont.Medium)
        p.setFont(f)
        for i, (key, title) in enumerate(self.STEPS):
            x = xs[i]
            if key in self.done and key != self.current:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(C["success"]))
                p.drawEllipse(QPointF(x, y), 8, 8)
                p.setPen(QPen(QColor("#102018"), 2))
                p.drawLine(QPointF(x - 3.5, y), QPointF(x - 1, y + 3))
                p.drawLine(QPointF(x - 1, y + 3), QPointF(x + 4, y - 3))
            elif key == self.current:
                col = QColor(C["danger"] if self.failed else C["violet"])
                halo = QColor(col)
                halo.setAlpha(60)
                p.setPen(Qt.NoPen)
                p.setBrush(halo)
                p.drawEllipse(QPointF(x, y), 12, 12)
                p.setBrush(QColor(C["night"]))
                p.setPen(QPen(col, 2.5))
                p.drawEllipse(QPointF(x, y), 7.5, 7.5)
                p.setBrush(col)
                p.setPen(Qt.NoPen)
                p.drawEllipse(QPointF(x, y), 3, 3)
            else:
                p.setBrush(QColor(C["night"]))
                p.setPen(QPen(QColor(C["border"]), 2))
                p.drawEllipse(QPointF(x, y), 7, 7)
            p.setPen(QColor(C["text"] if key == self.current else C["muted"]))
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(title)
            tx = min(max(0, x - tw / 2), w - tw)
            p.drawText(QPointF(tx, y + 26), title)
        if self.cycle_text:
            p.setPen(QColor(C["gold"]))
            p.drawText(QPointF(w - p.fontMetrics().horizontalAdvance(self.cycle_text) - 2, y + 42), self.cycle_text)


def load_sprite(path: Path, crisp: bool = True) -> QImage:
    """Load a mascot PNG. ``crisp`` applies a *display-only* alpha snap (≥50% → opaque,
    else transparent) so pixel art has no halo and no see-through body; files are untouched."""
    img = QImage(str(path))
    if img.isNull():
        return img
    img = img.convertToFormat(QImage.Format_ARGB32)
    if crisp:
        ptr = img.bits()
        data = memoryview(ptr).cast("B")
        n = img.sizeInBytes()
        buf = bytearray(data[:n])
        buf[3::4] = bytes(255 if a >= 128 else 0 for a in buf[3::4])
        for i in range(3, n, 4):
            if buf[i] == 0:
                buf[i - 3] = buf[i - 2] = buf[i - 1] = 0
        data[:n] = buf
    return img


class SpriteView(QWidget):
    """Pixel-perfect sprite (integer nearest-neighbour scale) with optional soft aura and bob."""

    def __init__(self, accent: str = C["violet"], aura: bool = True):
        super().__init__()
        self.image: QImage | None = None
        self.accent = QColor(accent)
        self.aura = aura
        self.bob = 0
        self.setMinimumSize(96, 96)

    def set_image(self, img: QImage | None):
        self.image = img
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        if self.aura:
            p.setRenderHint(QPainter.Antialiasing)
            g = QRadialGradient(QPointF(self.width() / 2, self.height() * 0.55), min(self.width(), self.height()) * 0.55)
            a = QColor(self.accent)
            a.setAlpha(70)
            g.setColorAt(0, a)
            a.setAlpha(0)
            g.setColorAt(1, a)
            p.fillRect(self.rect(), g)
        if self.image is None or self.image.isNull():
            return
        dpr = self.devicePixelRatioF()
        avail_w, avail_h = self.width() * dpr, self.height() * dpr
        scale = max(1, int(min(avail_w / self.image.width(), avail_h / self.image.height())))
        if min(avail_w / self.image.width(), avail_h / self.image.height()) < 1:
            pm = QPixmap.fromImage(self.image.scaled(int(avail_w), int(avail_h), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            pm = QPixmap.fromImage(self.image.scaled(self.image.width() * scale, self.image.height() * scale,
                                                     Qt.KeepAspectRatio, Qt.FastTransformation))
        pm.setDevicePixelRatio(dpr)
        w, h = pm.width() / dpr, pm.height() / dpr
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        p.drawPixmap(QPointF((self.width() - w) / 2, self.height() - h + self.bob), pm)


class EmptyState(QWidget):
    def __init__(self, state: str, title: str, text: str, action: QPushButton | None = None):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        art = QLabel()
        art.setPixmap(theme.svg_pixmap(f"states/{state}.svg", 96, 96))
        art.setAlignment(Qt.AlignCenter)
        lay.addWidget(art)
        t = label(title, "h2")
        t.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        d = label(text, "muted", wrap=True)
        d.setAlignment(Qt.AlignCenter)
        d.setMaximumWidth(460)
        lay.addWidget(d, 0, Qt.AlignHCenter)
        if action:
            lay.addSpacing(8)
            lay.addWidget(action, 0, Qt.AlignHCenter)


class Divider(QLabel):
    def __init__(self, width: int = 260):
        super().__init__()
        self.setPixmap(theme.svg_pixmap("ornaments/divisor.svg", width, 12))
        self.setAlignment(Qt.AlignCenter)


class Toggle(QAbstractButton):
    """Switch with label (accessible as a checkable button)."""

    def __init__(self, text: str, checked: bool = False, tip: str = ""):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setText(text)
        self.setToolTip(tip)
        self.setCursor(Qt.PointingHandCursor)
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)
        self.setFont(theme.font(8.8, QFont.Medium))

    def _animate(self, on: bool):
        self._anim.stop()
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def get_knob(self):
        return self._pos

    def set_knob(self, v):
        self._pos = v
        self.update()

    knob = Property(float, get_knob, set_knob)

    def sizeHint(self):
        fm = self.fontMetrics()
        return QSize(34 + 8 + fm.horizontalAdvance(self.text()) + 6, max(22, fm.height() + 6))

    def minimumSizeHint(self):
        return self.sizeHint()

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == e.Type.FontChange:
            self.updateGeometry()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h = 18
        y = (self.height() - h) / 2
        track = QRectF(0, y, 34, h)
        on = QColor(C["violet_d"])
        off = QColor(C["surface2"])
        c = QColor(int(off.red() + (on.red() - off.red()) * self._pos), int(off.green() + (on.green() - off.green()) * self._pos),
                   int(off.blue() + (on.blue() - off.blue()) * self._pos))
        path = QPainterPath()
        path.addRoundedRect(track, h / 2, h / 2)
        p.fillPath(path, c)
        p.setPen(QPen(QColor(C["violet"] if self.isChecked() else C["border"]), 1))
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#FFFFFF" if self.isChecked() else C["muted"]))
        p.drawEllipse(QPointF(9 + 16 * self._pos, y + h / 2), 6.5, 6.5)
        p.setPen(QColor(C["text"] if self.isChecked() else C["muted"]) if self.isEnabled() else QColor(C["dim"]))
        p.drawText(QRectF(42, 0, self.width() - 42, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text())
        if self.hasFocus():
            p.setPen(QPen(QColor(C["violet"]), 1, Qt.DotLine))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)


def icon_label(name: str, color: str, size: int = 18) -> QLabel:
    lb = QLabel()
    lb.setPixmap(theme.pixmap(name, color, size))
    lb.setFixedSize(size + 2, size + 2)
    return lb


class Header(QWidget):
    """App banner: night background + wordmark + sakura ornaments (separate assets)."""

    def __init__(self, demo: bool = False):
        super().__init__()
        self.setFixedHeight(64)
        self.bg = QPixmap(str(ASSETS / "backgrounds" / "cabecalho@2x.png"))
        self.branch = QPixmap(str(ASSETS / "ornaments" / "galho_sakura@2x.png"))
        self.wordmark = QPixmap(str(ASSETS / "branding" / "wordmark@2x.png"))
        self.logo = theme.svg_pixmap("branding/logo.svg", 38, 38)
        self.demo = demo
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 18, 0)
        lay.addStretch(1)
        self.right = QHBoxLayout()
        self.right.setSpacing(8)
        lay.addLayout(self.right)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        if not self.bg.isNull():
            # "cover": keep the asset's aspect ratio, crop the excess (no stretched moon)
            scale = max(w / self.bg.width(), h / self.bg.height())
            sw, sh = w / scale, h / scale
            src = QRectF((self.bg.width() - sw) * 0.5, (self.bg.height() - sh) * 0.5, sw, sh)
            p.drawPixmap(QRectF(0, 0, w, h), self.bg, src)
        if not self.branch.isNull():
            bw = int(h * 2.6)
            bh = int(bw * self.branch.height() / self.branch.width())
            p.setOpacity(0.85)
            p.drawPixmap(QRectF(w * 0.40, -bh * 0.22, bw, bh).toRect(), self.branch)
            p.setOpacity(1)
        p.drawPixmap(16, (h - 38) // 2, self.logo)
        if not self.wordmark.isNull():
            wh = 26
            ww = int(self.wordmark.width() * wh / self.wordmark.height())
            p.drawPixmap(QRectF(64, (h - wh) / 2 - 2, ww, wh).toRect(), self.wordmark)
        line = QLinearGradient(0, 0, w, 0)
        g = QColor(C["gold"])
        g.setAlpha(0)
        line.setColorAt(0, g)
        g.setAlpha(110)
        line.setColorAt(0.5, g)
        g.setAlpha(0)
        line.setColorAt(1, g)
        p.setPen(QPen(QBrush(line), 1))
        p.drawLine(0, h - 1, w, h - 1)
