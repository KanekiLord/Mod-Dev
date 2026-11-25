"""Design system: tokens, fonts, tinted SVG icons and the application style sheet."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from ..appdirs import ASSETS

# ---------------------------------------------------------------- tokens
C = {
    "ink": "#0E0A16", "night": "#130E1F", "sidebar": "#140F21", "surface": "#1B1430", "surface2": "#221A3A",
    "elevated": "#2A2046", "hover": "#30254F", "border": "#352A52", "border_soft": "#281F40",
    "text": "#F4EEF9", "muted": "#B3A6C9", "dim": "#85769F",
    "violet": "#B48CFF", "violet_d": "#7C4FD6", "violet_bg": "#2A1F4A",
    "amber": "#FF9F5A", "terra": "#E07A4A", "amber_bg": "#3A2224",
    "gold": "#E9C27A", "gold_d": "#C99A4B", "gold_bg": "#3A2E1E",
    "sakura": "#F4B6CF",
    "success": "#6FD6A8", "warning": "#F2C46B", "danger": "#F07A8E", "info": "#7FB8FF",
}
AGENT = {
    "codex": {"name": "Codex", "mascot": "Kaguya", "color": C["violet"], "bg": C["violet_bg"], "icon": "codex"},
    "claude": {"name": "Claude", "mascot": "Miwa", "color": C["amber"], "bg": C["amber_bg"], "icon": "claude"},
    "equipe": {"name": "Equipe", "mascot": "", "color": C["gold"], "bg": C["gold_bg"], "icon": "team"},
    "paralelo": {"name": "Paralelo", "mascot": "", "color": C["gold"], "bg": C["gold_bg"], "icon": "parallel"},
    "user": {"name": "Você", "mascot": "", "color": "#D9CCF0", "bg": C["surface2"], "icon": "chat"},
    "studio": {"name": "Studio", "mascot": "", "color": C["success"], "bg": "#173028", "icon": "moon"},
}
SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32}
RADIUS = {"sm": 8, "md": 12, "lg": 16, "pill": 999}

FONT_UI = "Inter"
FONT_DISPLAY = "Inter Display"
FONT_MONO = "JetBrains Mono"
FONT_SERIF = "Italiana"


def load_fonts() -> None:
    folder = ASSETS / "fonts"
    for f in sorted(folder.glob("*.[ot]tf")):
        QFontDatabase.addApplicationFont(str(f))


def font(size: float = 10, weight: QFont.Weight = QFont.Normal, family: str = FONT_UI) -> QFont:
    f = QFont(family)
    f.setPointSizeF(size)
    f.setWeight(weight)
    f.setHintingPreference(QFont.PreferNoHinting)
    return f


@lru_cache(maxsize=512)
def _svg_bytes(name: str, color: str) -> bytes:
    path = ASSETS / "icons" / f"{name}.svg"
    if not path.is_file():
        path = ASSETS / "icons" / "sparkle.svg"
    return path.read_text(encoding="utf-8").replace("currentColor", color).encode("utf-8")


def pixmap(name: str, color: str = C["muted"], size: int = 18, dpr: float = 2.0) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(_svg_bytes(name, color)))
    img = QImage(int(size * dpr), int(size * dpr), QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    renderer.render(p, QRectF(0, 0, size * dpr, size * dpr))
    p.end()
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name: str, color: str = C["muted"], active: str | None = None, size: int = 18) -> QIcon:
    ic = QIcon()
    ic.addPixmap(pixmap(name, color, size), QIcon.Normal, QIcon.Off)
    ic.addPixmap(pixmap(name, active or color, size), QIcon.Normal, QIcon.On)
    ic.addPixmap(pixmap(name, active or color, size), QIcon.Active, QIcon.Off)
    ic.addPixmap(pixmap(name, C["dim"], size), QIcon.Disabled, QIcon.Off)
    return ic


def asset(rel: str) -> Path:
    return ASSETS / rel


def svg_pixmap(rel: str, w: int, h: int, dpr: float = 2.0) -> QPixmap:
    r = QSvgRenderer(str(ASSETS / rel))
    img = QImage(int(w * dpr), int(h * dpr), QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    r.render(p, QRectF(0, 0, w * dpr, h * dpr))
    p.end()
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(dpr)
    return pm


def qcolor(name: str, alpha: int | None = None) -> QColor:
    c = QColor(C.get(name, name))
    if alpha is not None:
        c.setAlpha(alpha)
    return c


def stylesheet() -> str:
    c = C
    return f"""
* {{ font-family: "{FONT_UI}", "Segoe UI", sans-serif; color: {c['text']}; }}
QMainWindow, QWidget#Root {{ background: {c['ink']}; }}
QToolTip {{ background: {c['elevated']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 6px 8px; border-radius: 6px; }}
QLabel {{ background: transparent; }}
QSlider::groove:horizontal {{ height: 6px; background: {c['border']}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {c['violet_d']}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: {c['gold']}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}
QSlider::handle:horizontal:hover {{ background: {c['violet']}; }}
QLabel[role="muted"] {{ color: {c['muted']}; }}
QLabel[role="dim"] {{ color: {c['dim']}; }}
QLabel[role="section"] {{ color: {c['dim']}; font-size: 8pt; font-weight: 600; letter-spacing: 1.5px; }}
QLabel[role="h1"] {{ font-family: "{FONT_DISPLAY}"; font-size: 17pt; font-weight: 600; }}
QLabel[role="h2"] {{ font-family: "{FONT_DISPLAY}"; font-size: 12.5pt; font-weight: 600; }}
QLabel[role="code"] {{ font-family: "{FONT_MONO}"; font-size: 8.5pt; color: {c['muted']}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c['violet_d']}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {c['border']}; border-radius: 4px; min-width: 30px; }}
QPushButton {{ background: {c['surface2']}; border: 1px solid {c['border']}; border-radius: 9px; padding: 7px 14px;
              font-weight: 600; font-size: 9pt; color: {c['text']}; }}
QPushButton:hover {{ background: {c['hover']}; border-color: {c['violet_d']}; }}
QPushButton:pressed {{ background: {c['violet_bg']}; }}
QPushButton:disabled {{ color: {c['dim']}; background: {c['surface']}; border-color: {c['border_soft']}; }}
QPushButton:focus {{ outline: none; border-color: {c['violet']}; }}
QPushButton[kind="primary"] {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #F2D293, stop:1 {c['gold_d']});
              color: #24170A; border: 1px solid #F7DDA6; }}
QPushButton[kind="primary"]:hover {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #F8DFA8, stop:1 #D7AA5C); }}
QPushButton[kind="primary"]:disabled {{ background: {c['gold_bg']}; color: {c['dim']}; border-color: {c['border']}; }}
QPushButton[kind="danger"] {{ background: #3A1824; border-color: #7A3044; color: #FFD3DC; }}
QPushButton[kind="danger"]:hover {{ background: #4A1E2E; border-color: {c['danger']}; }}
QPushButton[kind="ghost"] {{ background: transparent; border: 1px solid transparent; color: {c['muted']}; }}
QPushButton[kind="ghost"]:hover {{ background: {c['surface2']}; color: {c['text']}; border-color: {c['border']}; }}
QPushButton[kind="chip"] {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 14px; padding: 5px 12px;
              font-weight: 500; color: {c['muted']}; }}
QPushButton[kind="chip"]:checked {{ background: {c['violet_bg']}; border-color: {c['violet']}; color: {c['text']}; }}
QPushButton[kind="nav"] {{ background: transparent; border: none; border-radius: 10px; padding: 9px 12px; text-align: left;
              font-weight: 500; font-size: 10pt; color: {c['muted']}; }}
QPushButton[kind="nav"]:hover {{ background: {c['surface']}; color: {c['text']}; }}
QPushButton[kind="nav"]:checked {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #3B2A63, stop:1 #2A1F46);
              color: #FFFFFF; font-weight: 600; }}
QPushButton[kind="project"] {{ background: transparent; border: 1px solid transparent; border-radius: 9px; padding: 7px 10px;
              text-align: left; font-weight: 500; color: {c['muted']}; }}
QPushButton[kind="project"]:hover {{ background: {c['surface']}; color: {c['text']}; }}
QPushButton[kind="project"]:checked {{ background: {c['gold_bg']}; border-color: #6B5330; color: {c['gold']}; font-weight: 600; }}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {{ background: {c['night']}; border: 1px solid {c['border']};
              border-radius: 9px; padding: 7px 10px; selection-background-color: {c['violet_d']}; font-size: 9.5pt; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {c['violet']}; }}
QLineEdit[state="ok"] {{ border-color: #3E7A62; }}
QLineEdit[state="error"] {{ border-color: {c['danger']}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QSpinBox {{ padding-right: 24px; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 20px; background: {c['surface2']}; border: none; border-left: 1px solid {c['border']}; }}
QSpinBox::up-button {{ border-top-right-radius: 9px; }}
QSpinBox::down-button {{ border-bottom-right-radius: 9px; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {c['hover']}; }}
QSpinBox::up-arrow {{ width: 0; height: 0; border-left: 4px solid transparent; border-right: 4px solid transparent; border-bottom: 5px solid {c['muted']}; }}
QSpinBox::down-arrow {{ width: 0; height: 0; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid {c['muted']}; }}
QComboBox QAbstractItemView {{ background: {c['elevated']}; border: 1px solid {c['border']}; selection-background-color: {c['violet_d']};
              outline: none; padding: 4px; }}
QCheckBox {{ spacing: 8px; color: {c['muted']}; font-size: 9pt; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 5px; border: 1px solid {c['border']}; background: {c['night']}; }}
QCheckBox::indicator:checked {{ background: {c['violet_d']}; border-color: {c['violet']}; image: none; }}
QTableWidget, QTreeWidget, QListWidget {{ background: {c['surface']}; border: 1px solid {c['border_soft']}; border-radius: 12px;
              gridline-color: {c['border_soft']}; font-size: 9pt; alternate-background-color: #1E1734; outline: none; }}
QTableWidget::item, QTreeWidget::item, QListWidget::item {{ padding: 6px 8px; border: none; }}
QTableWidget::item:selected, QTreeWidget::item:selected, QListWidget::item:selected {{ background: {c['violet_bg']}; color: #fff; }}
QHeaderView::section {{ background: {c['surface2']}; color: {c['gold']}; border: none; border-bottom: 1px solid {c['border']};
              padding: 8px; font-weight: 600; font-size: 8.5pt; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; color: {c['muted']}; padding: 8px 14px; border-bottom: 2px solid transparent; font-weight: 600; }}
QTabBar::tab:selected {{ color: {c['text']}; border-bottom-color: {c['gold']}; }}
QMenu {{ background: {c['elevated']}; border: 1px solid {c['border']}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {c['violet_d']}; }}
QMenu::separator {{ height: 1px; background: {c['border']}; margin: 5px 8px; }}
QProgressBar {{ background: {c['night']}; border: none; border-radius: 4px; height: 8px; text-align: center; font-size: 1px; color: transparent; }}
QProgressBar::chunk {{ border-radius: 4px; background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {c['violet_d']}, stop:1 {c['violet']}); }}
QSplitter::handle {{ background: transparent; }}
QDialog {{ background: {c['night']}; }}
QMessageBox {{ background: {c['night']}; }}
"""
