#!/usr/bin/env python3
"""Visual check of mascot transparency: original PNG vs. display-only crisp alpha, over light,
dark and Windows-like wallpapers. Output: assets/previews/transparencia_mascotes.png"""
from __future__ import annotations

import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter  # noqa: E402

app = QGuiApplication(sys.argv)
from kaguya.ui.widgets import load_sprite  # noqa: E402

M = ROOT / "assets" / "mascots"
SPRITES = [("Kaguya V2 (Codex)", M / "kaguya_v2" / "expressoes" / "kaguya_neutra.png"),
           ("Kaguya V1", M / "kaguya" / "expressoes" / "kaguya_neutra.png"),
           ("Claude", M / "claude" / "expressoes" / "claude_feminina_neutra.png")]
BGS = [("claro", QColor("#F3F0EA")), ("escuro", QColor("#101010")), ("papel de parede", None)]
S = 2
cell = 128 * S + 24
W = 240 + cell * len(BGS) * 2
H = 70 + (cell + 30) * len(SPRITES)
img = QImage(W, H, QImage.Format_ARGB32)
img.fill(QColor("#1B1430"))
p = QPainter(img)
p.setPen(QColor("#F4EEF9"))
p.setFont(QFont("Inter", 11, QFont.DemiBold))
p.drawText(20, 30, "Transparência das mascotes: PNG original × recorte de exibição (arquivo original não é alterado)")
for col, (bg_name, _) in enumerate(BGS):
    for k, mode in enumerate(("original", "recorte nítido")):
        x = 240 + (col * 2 + k) * cell
        p.setFont(QFont("Inter", 8))
        p.drawText(x, 56, f"{bg_name} • {mode}")
for row, (name, path) in enumerate(SPRITES):
    y = 70 + row * (cell + 30)
    p.setPen(QColor("#F4EEF9"))
    p.setFont(QFont("Inter", 10, QFont.DemiBold))
    p.drawText(20, y + cell // 2, name)
    for col, (_bg_name, color) in enumerate(BGS):
        for k, crisp in enumerate((False, True)):
            x = 240 + (col * 2 + k) * cell
            rect = QRectF(x, y, cell - 12, cell - 12)
            if color is None:
                g = QLinearGradient(rect.topLeft(), rect.bottomRight())
                g.setColorAt(0, QColor("#2D6CDF"))
                g.setColorAt(0.5, QColor("#9AD0F5"))
                g.setColorAt(1, QColor("#F6C177"))
                p.fillRect(rect, g)
            else:
                p.fillRect(rect, color)
            sprite = load_sprite(path, crisp)
            scaled = sprite.scaled(128 * S, 128 * S, Qt.KeepAspectRatio, Qt.FastTransformation)
            p.drawImage(int(x + 6), int(y + 6), scaled)
p.end()
out = ROOT / "assets" / "previews" / "transparencia_mascotes.png"
out.parent.mkdir(parents=True, exist_ok=True)
img.save(str(out))
print(out)
