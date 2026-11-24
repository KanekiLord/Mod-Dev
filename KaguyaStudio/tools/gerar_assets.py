#!/usr/bin/env python3
"""Generate Kaguya Studio's visual assets as separate files (SVG sources + PNG/ICO renders).

Run:  python tools/gerar_assets.py
Needs PySide6 (rendering/outlining text) and Pillow (ICO). Output goes to assets/.
Everything is drawn from code: no mock-up screenshot is cut or reused.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import random
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
A = ROOT / "assets"

# ---- palette (mirrors kaguya/ui/theme.py)
INK = "#0E0A16"
NIGHT = "#151022"
NIGHT2 = "#1D1432"
VIOLET = "#B48CFF"
VIOLET_D = "#7C4FD6"
AMBER = "#FF9F5A"
TERRA = "#E07A4A"
GOLD = "#E9C27A"
GOLD_D = "#C99A4B"
SAKURA = "#F4B6CF"
SAKURA_D = "#D98AAE"
MOON = "#F7E9CC"

ICONS = {
    "home": '<path d="M3.5 10.5 12 3.5l8.5 7V19a1.5 1.5 0 0 1-1.5 1.5h-4.5v-6h-5v6H5A1.5 1.5 0 0 1 3.5 19z"/>',
    "chat": '<path d="M5 4.5h14A1.5 1.5 0 0 1 20.5 6v9a1.5 1.5 0 0 1-1.5 1.5h-8.5L6 20v-3.5H5A1.5 1.5 0 0 1 3.5 15V6A1.5 1.5 0 0 1 5 4.5z"/><path d="M8 9.5h8M8 12.5h5"/>',
    "queue": '<path d="M9.5 6.5h10.5M9.5 12h10.5M9.5 17.5h10.5"/><circle cx="5" cy="6.5" r="1.2"/><circle cx="5" cy="12" r="1.2"/><circle cx="5" cy="17.5" r="1.2"/>',
    "brain": '<path d="M12 5.5a3 3 0 1 0-5.9.6 3.8 3.8 0 0 0-2.4 5.5 3.8 3.8 0 0 0 .6 6.2A3.6 3.6 0 0 0 12 18.5z"/><path d="M12 5.5a3 3 0 1 1 5.9.6 3.8 3.8 0 0 1 2.4 5.5 3.8 3.8 0 0 1-.6 6.2A3.6 3.6 0 0 1 12 18.5z"/><path d="M12 5.5v13M8.5 10.5c1.2 0 2 .8 2 2M15.5 10.5c-1.2 0-2 .8-2 2"/>',
    "agents": '<circle cx="9" cy="8" r="3.3"/><path d="M3 19.5c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5"/><path d="M15.5 4.9a3.3 3.3 0 0 1 0 6.3M18 14.4c1.8.7 3 2.5 3 5.1"/>',
    "pulse": '<path d="M3 12h4l2.5-6.5 5 13L17 12h4"/>',
    "gauge": '<path d="M4 17.5a8 8 0 1 1 16 0"/><path d="M12 17.5l3.6-6"/><circle cx="12" cy="17.5" r="1.2"/><path d="M6.6 11.3l1 .9M12 7.6v1.3M17.4 11.3l-1 .9"/>',
    "settings": '<path d="M4 6.5h9M17 6.5h3M4 12h3M11 12h9M4 17.5h11M19 17.5h1"/><circle cx="15" cy="6.5" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="17.5" r="2"/>',
    "folder": '<path d="M3.5 7A1.5 1.5 0 0 1 5 5.5h4.2l2 2H19A1.5 1.5 0 0 1 20.5 9v8.5A1.5 1.5 0 0 1 19 19H5a1.5 1.5 0 0 1-1.5-1.5z"/>',
    "folder-plus": '<path d="M3.5 7A1.5 1.5 0 0 1 5 5.5h4.2l2 2H19A1.5 1.5 0 0 1 20.5 9v8.5A1.5 1.5 0 0 1 19 19H5a1.5 1.5 0 0 1-1.5-1.5z"/><path d="M12 10.5v5.5M9.25 13.25h5.5"/>',
    "folder-open": '<path d="M3.5 17.5V7A1.5 1.5 0 0 1 5 5.5h4.2l2 2H18A1.5 1.5 0 0 1 19.5 9v1.5"/><path d="M3.5 17.5l2.3-6A1.5 1.5 0 0 1 7.2 10.5H20a1 1 0 0 1 .9 1.4L18.7 18a1.5 1.5 0 0 1-1.4 1H5a1.5 1.5 0 0 1-1.5-1.5z"/>',
    "link": '<path d="M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1 1"/><path d="M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 5.66 5.66l1-1"/>',
    "send": '<path d="M20.5 3.5 3.5 10.5l6.8 2.7 2.7 6.8z"/><path d="M10.3 13.2 20.5 3.5"/>',
    "mic": '<rect x="9" y="3" width="6" height="11.5" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M9 21h6"/>',
    "mic-off": '<path d="M15 10V6a3 3 0 0 0-5.7-1.3M9 9v2.5a3 3 0 0 0 4.6 2.5"/><path d="M5.5 11a6.5 6.5 0 0 0 10.3 5.3M18.5 11c0 .8-.1 1.5-.4 2.2M12 17.5V21M9 21h6M3.5 3.5l17 17"/>',
    "volume": '<path d="M4 9.5h3.5L12.5 5v14l-5-4.5H4z"/><path d="M16 9a4.2 4.2 0 0 1 0 6M18.6 6.4a8 8 0 0 1 0 11.2"/>',
    "volume-off": '<path d="M4 9.5h3.5L12.5 5v14l-5-4.5H4z"/><path d="M16.5 9.5l5 5M21.5 9.5l-5 5"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2.5"/>',
    "play": '<path d="M7.5 5.5v13l11-6.5z"/>',
    "pause": '<path d="M8.5 5.5v13M15.5 5.5v13"/>',
    "check": '<path d="M5 12.5 9.8 17 19 7"/>',
    "x": '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
    "alert": '<path d="M12 3.8 2.8 19.5h18.4z"/><path d="M12 10v4.2M12 16.9v.1"/>',
    "info": '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5M12 7.8v.1"/>',
    "refresh": '<path d="M19.5 11a7.5 7.5 0 0 0-13.4-4.4L4.5 8.3"/><path d="M4.5 4.3v4h4M4.5 13a7.5 7.5 0 0 0 13.4 4.4l1.6-1.7"/><path d="M19.5 19.7v-4h-4"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>',
    "globe": '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.4 2.5 3.5 5.3 3.5 8.5s-1.1 6-3.5 8.5c-2.4-2.5-3.5-5.3-3.5-8.5S9.6 6 12 3.5z"/>',
    "git": '<circle cx="6.5" cy="5.5" r="2"/><circle cx="6.5" cy="18.5" r="2"/><circle cx="17.5" cy="7.5" r="2"/><path d="M6.5 7.5v9M17.5 9.5c0 4.5-6 3.5-10 7.3"/>',
    "shield": '<path d="M12 3.2 4.8 6v5.8c0 4.4 3 7.6 7.2 9 4.2-1.4 7.2-4.6 7.2-9V6z"/><path d="M9 12l2.2 2.2L15.2 10"/>',
    "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3.2 2"/>',
    "sparkle": '<path d="M11 3.5l1.7 4.8 4.8 1.7-4.8 1.7L11 16.5l-1.7-4.8L4.5 10l4.8-1.7z"/><path d="M18 14.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z"/>',
    "terminal": '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M7.5 9.5l3 2.5-3 2.5M13 15h4"/>',
    "external": '<path d="M14 4.5h5.5V10M19.5 4.5l-8.5 8.5"/><path d="M17.5 14v4A1.5 1.5 0 0 1 16 19.5H6A1.5 1.5 0 0 1 4.5 18V8A1.5 1.5 0 0 1 6 6.5h4"/>',
    "trash": '<path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 12.5h9L17.5 7M10 11v5.5M14 11v5.5"/>',
    "edit": '<path d="M4.5 19.5h4l10-10-4-4-10 10z"/><path d="M13 7l4 4"/>',
    "file": '<path d="M14 3.5H6.5A1.5 1.5 0 0 0 5 5v14a1.5 1.5 0 0 0 1.5 1.5h11A1.5 1.5 0 0 0 19 19V8.5z"/><path d="M14 3.5v5h5M8.5 13h7M8.5 16.5h5"/>',
    "layers": '<path d="M12 3.5 3 8l9 4.5L21 8z"/><path d="M3 12l9 4.5 9-4.5M3 16l9 4.5 9-4.5"/>',
    "moon": '<path d="M19.5 14.6A8 8 0 1 1 9.4 4.5a6.3 6.3 0 0 0 10.1 10.1z"/>',
    "sakura": "".join(f'<path transform="rotate({a} 12 12)" d="M12 11.2c-2.1-1.6-2.9-4.3-1.6-6.7l.9.9.7-1.1.7 1.1.9-.9c1.3 2.4.5 5.1-1.6 6.7z"/>'
                      for a in (0, 72, 144, 216, 288)) + '<circle cx="12" cy="12" r="1"/>',
    "lightbulb": '<path d="M9.5 18h5M10.5 21h3"/><path d="M12 3.5a5.8 5.8 0 0 0-3.4 10.5c.6.5.9 1.1.9 1.9v.1h5v-.1c0-.8.3-1.4.9-1.9A5.8 5.8 0 0 0 12 3.5z"/>',
    "inbox": '<path d="M3.5 13l2.7-7.5h11.6l2.7 7.5v5.5a1.5 1.5 0 0 1-1.5 1.5H5a1.5 1.5 0 0 1-1.5-1.5z"/><path d="M3.5 13h5l1.5 2.5h4l1.5-2.5h5"/>',
    "chevron-right": '<path d="M9.5 6l6 6-6 6"/>',
    "chevron-down": '<path d="M6 9.5l6 6 6-6"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "bug": '<rect x="8" y="7" width="8" height="12.5" rx="4"/><path d="M12 11v8.5M8 11.5H4.5M19.5 11.5H16M8 16H5M19 16h-3M9.5 7L7.5 4M14.5 7l2-3"/>',
    "book": '<path d="M4.5 5.5a2 2 0 0 1 2-2h12.5v15H6.5a2 2 0 0 0-2 2z"/><path d="M4.5 20.5a2 2 0 0 1 2-2H19v2"/>',
    "pin": '<path d="M9 3.5h6l-1 5 3.5 3.5v1.5h-11V12L10 8.5z"/><path d="M12 13.5v7"/>',
    "window": '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><rect x="12" y="11" width="6.5" height="6" rx="1"/>',
    "codex": '<path d="M12 2.8l8 4.6v9.2l-8 4.6-8-4.6V7.4z"/><path d="M10 9.5 7.5 12l2.5 2.5M14 9.5l2.5 2.5-2.5 2.5"/>',
    "claude": '<path d="M12 3.5v4M12 16.5v4M3.5 12h4M16.5 12h4M6 6l2.8 2.8M15.2 15.2 18 18M18 6l-2.8 2.8M8.8 15.2 6 18"/><circle cx="12" cy="12" r="2.2"/>',
    "team": '<circle cx="7.5" cy="12" r="3.5"/><circle cx="16.5" cy="12" r="3.5"/><path d="M11 12h2"/>',
    "parallel": '<path d="M6 4.5v15M18 4.5v15"/><path d="M3.5 8h5M15.5 8h5M3.5 16h5M15.5 16h5"/>',
    "eye": '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.8"/>',
    "download": '<path d="M12 4v11M7.5 10.5 12 15l4.5-4.5M4.5 19.5h15"/>',
    "key": '<circle cx="8" cy="14" r="4"/><path d="M11 11.5 19.5 3.5M16 7l2.5 2.5M14 9l2 2"/>',
    "wave": '<path d="M3 12c1.5 0 1.5-3 3-3s1.5 6 3 6 1.5-9 3-9 1.5 12 3 12 1.5-6 3-6 1.5 3 3 3"/>',
}


def icon_svg(body: str, color: str = "currentColor") -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" '
            f'stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">{body}</svg>\n')


def petal(cx, cy, r, angle, fill, stroke=None, opacity=1.0):
    """Rounded sakura petal with the characteristic notch at the tip."""
    a = math.radians(angle)

    def pt(dist, da):
        return (cx + r * dist * math.cos(a + da), cy + r * dist * math.sin(a + da))
    c1, c2 = pt(0.55, -0.95), pt(1.0, -0.42)
    tl, notch, tr = pt(1.0, -0.2), pt(0.84, 0.0), pt(1.0, 0.2)
    c3, c4 = pt(1.0, 0.42), pt(0.55, 0.95)
    f = lambda p: f"{p[0]:.1f} {p[1]:.1f}"
    d = (f"M{cx:.1f} {cy:.1f} C{f(c1)} {f(c2)} {f(tl)} L{f(notch)} L{f(tr)} C{f(c3)} {f(c4)} {cx:.1f} {cy:.1f}Z")
    s = f' stroke="{stroke}" stroke-width="0.8"' if stroke else ""
    return f'<path d="{d}" fill="{fill}" opacity="{opacity}"{s}/>'


def blossom(cx, cy, r, rot=0.0, light=SAKURA, dark=SAKURA_D, opacity=1.0):
    parts = [petal(cx, cy, r, rot + k * 72, "url(#petal)", None, opacity) for k in range(5)]
    parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r * 0.22:.1f}" fill="{dark}" opacity="{opacity}"/>')
    for k in range(5):
        a = math.radians(rot + k * 72 + 36)
        parts.append(f'<circle cx="{cx + r * 0.36 * math.cos(a):.1f}" cy="{cy + r * 0.36 * math.sin(a):.1f}" r="{r * 0.06:.1f}" fill="{GOLD}" opacity="{opacity}"/>')
    return "".join(parts)


PETAL_GRAD = (f'<radialGradient id="petal" cx="50%" cy="50%" r="60%"><stop offset="0" stop-color="#FFE3EE"/>'
              f'<stop offset="0.55" stop-color="{SAKURA}"/><stop offset="1" stop-color="{SAKURA_D}"/></radialGradient>')


def sakura_branch(w=520, h=220, seed=7, mirror=False) -> str:
    rnd = random.Random(seed)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">',
             f'<defs>{PETAL_GRAD}<linearGradient id="wood" x1="0" x2="1"><stop offset="0" stop-color="#2B1A33"/>'
             f'<stop offset="1" stop-color="#4A2D47"/></linearGradient></defs>']
    g = f'<g transform="translate({w} 0) scale(-1 1)">' if mirror else "<g>"
    parts.append(g)
    parts.append(f'<path d="M{w} 18 C{w*0.78} 30 {w*0.62} 52 {w*0.45} 92 S{w*0.2} 150 {w*0.04} 168" fill="none" '
                 f'stroke="url(#wood)" stroke-width="7" stroke-linecap="round"/>')
    parts.append(f'<path d="M{w*0.62} 52 C{w*0.58} 22 {w*0.5} 14 {w*0.4} 10" fill="none" stroke="url(#wood)" '
                 f'stroke-width="4" stroke-linecap="round"/>')
    parts.append(f'<path d="M{w*0.45} 92 C{w*0.4} 120 {w*0.36} 140 {w*0.3} 196" fill="none" stroke="url(#wood)" '
                 f'stroke-width="3.5" stroke-linecap="round"/>')
    parts.append(f'<path d="M{w*0.78} 30 C{w*0.74} 60 {w*0.78} 84 {w*0.72} 110" fill="none" stroke="url(#wood)" '
                 f'stroke-width="3" stroke-linecap="round"/>')
    spots = [(0.92, 22), (0.8, 30), (0.7, 40), (0.62, 52), (0.55, 30), (0.47, 16), (0.4, 11), (0.5, 76), (0.44, 96),
             (0.38, 118), (0.33, 150), (0.31, 186), (0.25, 132), (0.16, 152), (0.08, 164), (0.77, 66), (0.73, 104)]
    for fx, y in spots:
        r = rnd.uniform(9, 15)
        parts.append(blossom(w * fx + rnd.uniform(-4, 4), y + rnd.uniform(-5, 5), r, rnd.uniform(0, 72)))
    for _ in range(10):
        x, y = rnd.uniform(0, w), rnd.uniform(h * 0.3, h)
        parts.append(petal(x, y, rnd.uniform(4, 7), rnd.uniform(0, 360), "url(#petal)", None, rnd.uniform(0.45, 0.9)))
    parts.append("</g></svg>\n")
    return "".join(parts)


def moon_svg(size=220) -> str:
    c = size / 2
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}">'
            f'<defs><radialGradient id="glow"><stop offset="0.35" stop-color="{MOON}" stop-opacity="0.55"/>'
            f'<stop offset="1" stop-color="{MOON}" stop-opacity="0"/></radialGradient>'
            f'<linearGradient id="m" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFF6E2"/>'
            f'<stop offset="1" stop-color="{GOLD}"/></linearGradient>'
            f'<mask id="cut"><rect width="{size}" height="{size}" fill="#fff"/><circle cx="{c + size*0.14}" cy="{c - size*0.1}" r="{size*0.27}" fill="#000"/></mask></defs>'
            f'<circle cx="{c}" cy="{c}" r="{size*0.48}" fill="url(#glow)"/>'
            f'<circle cx="{c}" cy="{c}" r="{size*0.3}" fill="url(#m)" mask="url(#cut)"/></svg>\n')


def divider_svg(w=420, h=18) -> str:
    c = w / 2
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'<defs><linearGradient id="l" x1="0" x2="1"><stop offset="0" stop-color="{GOLD}" stop-opacity="0"/>'
            f'<stop offset="0.5" stop-color="{GOLD}" stop-opacity="0.85"/><stop offset="1" stop-color="{GOLD}" stop-opacity="0"/></linearGradient></defs>'
            f'<path d="M0 {h/2}H{c-16}M{c+16} {h/2}H{w}" stroke="url(#l)" stroke-width="1"/>'
            f'<path d="M{c} {h/2-6} L{c+6} {h/2} L{c} {h/2+6} L{c-6} {h/2}Z" fill="none" stroke="{GOLD}" stroke-width="1.2"/>'
            f'<circle cx="{c}" cy="{h/2}" r="1.6" fill="{GOLD}"/><circle cx="{c-12}" cy="{h/2}" r="1.2" fill="{GOLD}" opacity="0.8"/>'
            f'<circle cx="{c+12}" cy="{h/2}" r="1.2" fill="{GOLD}" opacity="0.8"/></svg>\n')


def corner_svg(s=72) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {s} {s}" width="{s}" height="{s}"><defs>{PETAL_GRAD}</defs>'
            f'<path d="M4 {s-6} V14 Q4 4 14 4 H{s-6}" fill="none" stroke="{GOLD}" stroke-opacity="0.7" stroke-width="1.4"/>'
            f'<path d="M10 {s-14} V18 Q10 10 18 10 H{s-14}" fill="none" stroke="{GOLD}" stroke-opacity="0.3" stroke-width="1"/>'
            f'{blossom(15, 15, 8, 18)}</svg>\n')


def seigaiha_svg(w=48, h=24, color=VIOLET, opacity=0.09) -> str:
    rings = []
    for cx, cy in ((0, h), (w / 2, h / 2), (w, h), (w / 2, h * 1.5), (0, 0), (w, 0)):
        for r in (12, 9, 6, 3):
            rings.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="0.9"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'<g opacity="{opacity}">{"".join(rings)}</g></svg>\n')


def night_svg(w=1600, h=900, seed=3, header=False) -> str:
    rnd = random.Random(seed)
    stars = "".join(f'<circle cx="{rnd.uniform(0, w):.0f}" cy="{rnd.uniform(0, h * 0.62):.0f}" r="{rnd.choice((0.6, 0.8, 1, 1.3)):.1f}" '
                    f'fill="#fff" opacity="{rnd.uniform(0.15, 0.6):.2f}"/>' for _ in range(int(w * h / 9000)))
    mx, my, mr = w * (0.585 if header else 0.80), h * (0.42 if header else 0.2), (h * 0.38 if header else 70)
    mountains = ""
    if not header:
        mountains = (f'<path d="M0 {h*0.78} L{w*0.12} {h*0.66} L{w*0.2} {h*0.71} L{w*0.33} {h*0.6} L{w*0.46} {h*0.72} L{w*0.6} {h*0.63} '
                     f'L{w*0.74} {h*0.7} L{w*0.88} {h*0.61} L{w} {h*0.68} V{h} H0Z" fill="#170F26"/>'
                     f'<path d="M0 {h*0.86} L{w*0.18} {h*0.77} L{w*0.32} {h*0.83} L{w*0.5} {h*0.75} L{w*0.66} {h*0.84} '
                     f'L{w*0.82} {h*0.76} L{w} {h*0.82} V{h} H0Z" fill="#120B1E"/>'
                     + pagoda(w * 0.665, h * 0.635, 1.0))
    else:
        mountains = (f'<path d="M{w*0.42} {h} L{w*0.5} {h*0.62} L{w*0.7} {h*0.78} L{w*0.78} {h*0.5} L{w*0.87} {h*0.74} '
                     f'L{w*0.95} {h*0.58} L{w} {h*0.66} V{h}Z" fill="#170F26" opacity="0.9"/>' + pagoda(w * 0.9, h * 0.62, 0.55))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'<defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#120C1F"/>'
            f'<stop offset="0.55" stop-color="#1E1233"/><stop offset="1" stop-color="{INK}"/></linearGradient>'
            f'<radialGradient id="halo"><stop offset="0" stop-color="{MOON}" stop-opacity="0.35"/><stop offset="0.25" stop-color="#C8A6FF" stop-opacity="0.12"/>'
            f'<stop offset="1" stop-color="#C8A6FF" stop-opacity="0"/></radialGradient>'
            f'<radialGradient id="mface" cx="40%" cy="35%"><stop offset="0" stop-color="#FFF8EA"/><stop offset="1" stop-color="#E8D3AE"/></radialGradient>'
            f'<linearGradient id="mist" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2A1A44" stop-opacity="0"/>'
            f'<stop offset="1" stop-color="#2A1A44" stop-opacity="0.55"/></linearGradient></defs>'
            f'<rect width="{w}" height="{h}" fill="url(#sky)"/>{stars}'
            f'<circle cx="{mx}" cy="{my}" r="{mr*3.2}" fill="url(#halo)"/>'
            f'<circle cx="{mx}" cy="{my}" r="{mr*0.62}" fill="url(#mface)" opacity="0.92"/>'
            f'<circle cx="{mx-mr*0.18}" cy="{my-mr*0.1}" r="{mr*0.09}" fill="#D9C29A" opacity="0.35"/>'
            f'<circle cx="{mx+mr*0.2}" cy="{my+mr*0.16}" r="{mr*0.06}" fill="#D9C29A" opacity="0.3"/>'
            f'{mountains}<rect y="{h*0.55}" width="{w}" height="{h*0.45}" fill="url(#mist)"/></svg>\n')


def pagoda(x, y, s):
    fill = "#100A1A"
    tiers = []
    for i, (wd, ht) in enumerate(((80, 14), (64, 12), (50, 11), (38, 10))):
        ty = y - i * 26 * s
        tiers.append(f'<path d="M{x - wd*s/2} {ty} Q{x} {ty - ht*s*1.6} {x + wd*s/2} {ty} Z" fill="{fill}"/>'
                     f'<rect x="{x - wd*s*0.3}" y="{ty}" width="{wd*s*0.6}" height="{14*s}" fill="{fill}"/>')
    return "".join(tiers) + f'<rect x="{x-1.5*s}" y="{y - 130*s}" width="{3*s}" height="{30*s}" fill="{fill}"/>'


def logo_svg(size=256) -> str:
    s = size
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="{s}" height="{s}">'
            f'<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2A1A47"/>'
            f'<stop offset="1" stop-color="#120B1F"/></linearGradient>'
            f'<linearGradient id="moon" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFF4DA"/>'
            f'<stop offset="1" stop-color="{GOLD_D}"/></linearGradient>'
            f'<radialGradient id="glow" cx="40%" cy="40%"><stop offset="0" stop-color="{VIOLET}" stop-opacity="0.45"/>'
            f'<stop offset="1" stop-color="{VIOLET}" stop-opacity="0"/></radialGradient>{PETAL_GRAD}'
            f'<mask id="cut"><rect width="256" height="256" fill="#fff"/><circle cx="150" cy="96" r="70" fill="#000"/></mask></defs>'
            f'<rect x="8" y="8" width="240" height="240" rx="56" fill="url(#bg)"/>'
            f'<rect x="8.75" y="8.75" width="238.5" height="238.5" rx="55.5" fill="none" stroke="{GOLD}" stroke-opacity="0.45" stroke-width="1.5"/>'
            f'<circle cx="112" cy="124" r="96" fill="url(#glow)"/>'
            f'<circle cx="116" cy="128" r="78" fill="url(#moon)" mask="url(#cut)"/>'
            f'{blossom(176, 168, 34, -10)}'
            f'<path d="M196 70l4 11 11 4-11 4-4 11-4-11-11-4 11-4z" fill="{MOON}" opacity="0.9"/></svg>\n')


def state_svg(kind: str) -> str:
    base = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96" width="96" height="96">'
            '<defs><radialGradient id="g"><stop offset="0" stop-color="{c}" stop-opacity="0.35"/>'
            '<stop offset="1" stop-color="{c}" stop-opacity="0"/></radialGradient></defs>'
            '<circle cx="48" cy="48" r="46" fill="url(#g)"/>{body}</svg>\n')
    if kind == "carregando":
        body = (f'<circle cx="48" cy="48" r="22" fill="none" stroke="{VIOLET}" stroke-opacity="0.2" stroke-width="5"/>'
                f'<path d="M48 26a22 22 0 0 1 22 22" fill="none" stroke="{GOLD}" stroke-width="5" stroke-linecap="round"/>')
        return base.format(c=VIOLET, body=body)
    if kind == "sucesso":
        body = (f'<circle cx="48" cy="48" r="24" fill="#18332B" stroke="#6FD6A8" stroke-width="2.5"/>'
                f'<path d="M37 48.5l7.5 7.5L60 40" fill="none" stroke="#6FD6A8" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>')
        return base.format(c="#6FD6A8", body=body)
    if kind == "erro":
        body = (f'<circle cx="48" cy="48" r="24" fill="#3A1824" stroke="#F07A8E" stroke-width="2.5"/>'
                f'<path d="M39 39l18 18M57 39L39 57" stroke="#F07A8E" stroke-width="4" stroke-linecap="round"/>')
        return base.format(c="#F07A8E", body=body)
    if kind == "offline":
        body = (f'<path d="M30 60h36a12 12 0 0 0 0-24 16 16 0 0 0-30-4 12 12 0 0 0-6 28z" fill="#241A38" stroke="#8676A0" stroke-width="2.5"/>'
                f'<path d="M26 26l44 44" stroke="#F2C46B" stroke-width="3.5" stroke-linecap="round"/>')
        return base.format(c="#8676A0", body=body)
    # vazio: moon behind a cloud with sparkles
    body = (f'<circle cx="54" cy="40" r="17" fill="{MOON}" opacity="0.9"/><circle cx="62" cy="34" r="14" fill="#1C1530"/>'
            f'<path d="M24 66h40a10 10 0 0 0 0-20 13 13 0 0 0-25-3 10 10 0 0 0-15 23z" fill="#2A2043" stroke="{VIOLET}" stroke-opacity="0.6" stroke-width="2"/>'
            f'<path d="M24 26l1.6 4.4 4.4 1.6-4.4 1.6L24 38l-1.6-4.4L18 32l4.4-1.6z" fill="{GOLD}"/>'
            f'<circle cx="76" cy="62" r="1.8" fill="{SAKURA}"/>')
    return base.format(c=VIOLET, body=body)


def text_path_svg(text: str, font_file: Path, px: int, fill: str, letter_spacing: float = 0.0) -> tuple[str, float, float]:
    from PySide6.QtGui import QFont, QFontDatabase, QPainterPath
    fid = QFontDatabase.addApplicationFont(str(font_file))
    family = QFontDatabase.applicationFontFamilies(fid)[0]
    font = QFont(family)
    font.setPixelSize(px)
    if letter_spacing:
        font.setLetterSpacing(QFont.AbsoluteSpacing, letter_spacing)
    path = QPainterPath()
    path.addText(0, px, font, text)
    rect = path.boundingRect()
    d = []
    i = 0
    n = path.elementCount()
    while i < n:
        e = path.elementAt(i)
        if e.isMoveTo():
            d.append(f"M{e.x - rect.x():.2f} {e.y - rect.y():.2f}")
            i += 1
        elif e.isLineTo():
            d.append(f"L{e.x - rect.x():.2f} {e.y - rect.y():.2f}")
            i += 1
        else:  # CurveTo + 2 data points
            c2, end = path.elementAt(i + 1), path.elementAt(i + 2)
            d.append(f"C{e.x - rect.x():.2f} {e.y - rect.y():.2f} {c2.x - rect.x():.2f} {c2.y - rect.y():.2f} "
                     f"{end.x - rect.x():.2f} {end.y - rect.y():.2f}")
            i += 3
    return f'<path d="{" ".join(d)}" fill="{fill}"/>', rect.width(), rect.height()


def wordmark_svg() -> str:
    fonts = A / "fonts"
    title, tw, th = text_path_svg("KAGUYA STUDIO", fonts / "Italiana-Regular.ttf", 64, "url(#gold)", 6)
    jp_font = Path("/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf")
    jp = ""
    jw = 0
    if jp_font.exists():
        jp, jw, jh = text_path_svg("かぐや", jp_font, 30, SAKURA)
    w, h = int(tw + jw + 40), int(th + 8)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'<defs><linearGradient id="gold" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFF1D2"/>'
            f'<stop offset="1" stop-color="{GOLD_D}"/></linearGradient></defs>'
            f'<g transform="translate(0 4)">{title}</g>'
            + (f'<g transform="translate({tw + 30:.0f} {max(4, (h - 30) / 2):.0f})" opacity="0.9">{jp}</g>' if jp else "")
            + "</svg>\n")


def render(svg_path: Path, png_path: Path, w: int, h: int) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    r = QSvgRenderer(str(svg_path))
    img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    r.render(p)
    p.end()
    png_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(png_path))


def write(rel: str, content: str) -> Path:
    p = A / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def main() -> None:
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # noqa: F841
    for name, body in ICONS.items():
        write(f"icons/{name}.svg", icon_svg(body))
    logo = write("branding/logo.svg", logo_svg())
    for s in (16, 24, 32, 48, 64, 128, 256, 512):
        render(logo, A / "branding" / f"icone_{s}.png", s, s)
    try:
        from PIL import Image
        Image.open(A / "branding" / "icone_256.png").save(A / "branding" / "kaguya.ico",
                                                          sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    except ImportError:
        print("Pillow ausente: kaguya.ico não gerado")
    wm = write("branding/wordmark.svg", wordmark_svg())
    import re
    vb = re.search(r'viewBox="0 0 (\d+) (\d+)"', wm.read_text()).groups()
    render(wm, A / "branding" / "wordmark@2x.png", int(vb[0]) * 2, int(vb[1]) * 2)
    branch = write("ornaments/galho_sakura.svg", sakura_branch())
    render(branch, A / "ornaments" / "galho_sakura@2x.png", 1040, 440)
    branch_l = write("ornaments/galho_sakura_esquerda.svg", sakura_branch(seed=11, mirror=True))
    render(branch_l, A / "ornaments" / "galho_sakura_esquerda@2x.png", 1040, 440)
    moon = write("ornaments/lua.svg", moon_svg())
    render(moon, A / "ornaments" / "lua@2x.png", 440, 440)
    div = write("ornaments/divisor.svg", divider_svg())
    render(div, A / "ornaments" / "divisor@2x.png", 840, 36)
    cor = write("ornaments/canto.svg", corner_svg())
    render(cor, A / "ornaments" / "canto@2x.png", 144, 144)
    write("ornaments/seigaiha.svg", seigaiha_svg())
    write("ornaments/seigaiha_dourado.svg", seigaiha_svg(color=GOLD, opacity=0.07))
    write("ornaments/flor_sakura.svg", f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64"><defs>{PETAL_GRAD}</defs>{blossom(32, 32, 26, -18)}</svg>\n')
    render(A / "ornaments" / "flor_sakura.svg", A / "ornaments" / "flor_sakura@2x.png", 128, 128)
    bg = write("backgrounds/noite.svg", night_svg())
    render(bg, A / "backgrounds" / "noite.png", 1600, 900)
    hd = write("backgrounds/cabecalho.svg", night_svg(2400, 104, seed=9, header=True))
    render(hd, A / "backgrounds" / "cabecalho@2x.png", 4800, 208)
    for k in ("carregando", "sucesso", "erro", "offline", "vazio"):
        p = write(f"states/{k}.svg", state_svg(k))
        render(p, A / "states" / f"{k}@2x.png", 192, 192)
    print(f"Assets gerados em {A}")


if __name__ == "__main__":
    main()
