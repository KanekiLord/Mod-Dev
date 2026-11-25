"""Builds the chibi (Live mode) and portrait (Kaguya V3) assets from the packages the user sent.

    python tools/recortar_chibis.py <kaguya_chibi_talk_v1 dir> <miwa_folha_A.png> <miwa_folha_B.png>
                                    <kaguya_retratos_1.png> <kaguya_retratos_2.png> <kaguya_retratos_3.png>

* Kaguya chibi: the package already has 7 sequences × 7 frames (128×128 RGBA) → copied as they are.
* Miwa chibi: two transparent sheets with rows of different lengths (9/9/8/8/9 and 10×5). Rows are found by the
  empty space between them; inside a row the cuts go through the emptiest column near where each drawing is
  expected (figures touch and effects like “?” or “♥” sit between them). Every frame is scaled by the same factor
  and placed on a 256×256 canvas, feet aligned, so the character never jumps between frames.
* Kaguya portraits: three 3×2 transparent sheets → one common framing for all 18 drawings, 320 px tall.
The originals are kept untouched under ``pacote_original/`` next to the generated files.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MASCOTS = ROOT / "assets" / "mascots"
CANVAS = 256

# sheet A rows: 9, 9, 8, 8, 9 drawings; sheet B: 10 per row  (reference: "A2.3" = sheet A, row 2, drawing 3)
MIWA_COUNTS = {"A": [9, 9, 8, 8, 9], "B": [10, 10, 10, 10, 10]}
MIWA_SEQUENCES = {
    "fala_neutra": ["B1.1", "B1.2", "B1.3", "B1.4", "B1.5", "B1.4", "B1.3"],
    "explicando": ["A1.2", "A1.3", "A1.4", "A1.5", "A1.6", "A1.7", "A1.8"],
    "explicando2": ["B2.3", "B2.5", "B2.6", "B2.5", "B2.3", "B1.6", "B1.7"],
    "animada": ["A2.1", "A2.2", "A2.3", "A2.4", "A2.5", "A2.6", "A2.7"],
    "carinhosa": ["B4.3", "B4.4", "B4.5", "B4.6", "B4.5", "B4.4", "B4.3"],
    "pensando": ["A3.1", "A3.2", "A3.3", "B3.1", "B3.2", "B3.3", "B3.2"],
    "trabalhando": ["A3.4", "A3.5", "A3.6", "A3.7"],
    "surpresa": ["A4.1", "A4.2", "B4.1", "B4.2", "A4.3", "A4.2", "A4.1"],
    "seria": ["B4.7", "B4.8", "A4.5", "A4.6", "B4.8", "B4.7", "B4.7"],
    "acenando": ["B5.6", "B5.7", "B5.8", "B5.9", "B5.10", "B5.8", "B5.6"],
    "parada": ["A1.1", "B1.1", "A1.1", "A5.2"],
}

# Kaguya portraits: sheet 1..3, drawing 1..6 (row-major)
PORTRAIT_EXPRESSIONS = {"neutra": (3, 1), "falando": (3, 3), "feliz": (1, 5), "surpresa": (2, 2), "explicando": (2, 3),
                        "carinhosa": (1, 4), "confiante": (1, 6), "sorriso": (2, 6), "oferecendo": (1, 3)}
PORTRAIT_TALK = {"retrato_fala": [(3, 1), (3, 2), (3, 3), (3, 4), (3, 5), (3, 6)],
                 "retrato_explicando": [(2, 1), (2, 2), (2, 3), (2, 4), (2, 5), (2, 6)],
                 "retrato_animada": [(1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (1, 6)]}


def _runs(v, gap=3):
    out, start, last = [], None, None
    for i, x in enumerate(v):
        if x:
            start = i if start is None else start
            last = i
        elif start is not None and i - last > gap:
            out.append((start, last))
            start = None
    if start is not None:
        out.append((start, last))
    return out


def split_sheet(img: Image.Image, counts: list[int]) -> list[list[tuple[int, int, int, int]]]:
    A = np.array(img.convert("RGBA"))[:, :, 3]
    bands = _runs((A > 200).any(1))
    if len(bands) != len(counts):
        raise SystemExit(f"esperava {len(counts)} linhas, achei {len(bands)}")
    cells = []
    for (b0, b1), n in zip(bands, counts):
        prof = np.convolve((A[b0:b1 + 1] > 120).sum(0).astype(float), np.ones(9) / 9, mode="same")
        xs = np.nonzero(prof > 0)[0]
        x0, x1 = int(xs[0]), int(xs[-1])
        w = (x1 - x0) / n
        cuts = [x0]
        for k in range(1, n):
            e = int(x0 + k * w)
            lo, hi = int(e - w * 0.35), int(e + w * 0.35)
            cuts.append(lo + int(np.argmin(prof[lo:hi])))
        cuts.append(x1 + 1)
        row = []
        for c0, c1 in zip(cuts[:-1], cuts[1:]):
            ys, xx = np.nonzero(A[b0:b1 + 1, c0:c1] > 20)
            row.append((c0 + int(xx.min()), b0 + int(ys.min()), c0 + int(xx.max()) + 1, b0 + int(ys.max()) + 1))
        cells.append(row)
    return cells


def _clean(img: Image.Image) -> Image.Image:
    """Drop near-invisible alpha (the generator leaves a faint haze) so the floating window has no halo."""
    a = np.array(img)
    a[a[:, :, 3] < 24] = 0
    return Image.fromarray(a, "RGBA")


def build_miwa(sheet_a: Path, sheet_b: Path, out: Path) -> dict:
    sheets = {"A": Image.open(sheet_a).convert("RGBA"), "B": Image.open(sheet_b).convert("RGBA")}
    boxes = {k: split_sheet(im, MIWA_COUNTS[k]) for k, im in sheets.items()}
    crops = {}
    for k, rows in boxes.items():
        for r, row in enumerate(rows, 1):
            for c, b in enumerate(row, 1):
                crops[f"{k}{r}.{c}"] = sheets[k].crop(b)
    # each sheet draws the character at its own size: bring both to sheet A's typical height first
    med = {k: float(np.median([im.height for ref, im in crops.items() if ref[0] == k])) for k in sheets}
    norm = {k: med["A"] / med[k] for k in sheets}
    tallest = max(im.height * norm[ref[0]] for ref, im in crops.items())
    widest = max(im.width * norm[ref[0]] for ref, im in crops.items())
    base = min((CANVAS - 10) / tallest, (CANVAS - 6) / widest)
    frames = out / "frames"
    if frames.exists():
        shutil.rmtree(frames)
    frames.mkdir(parents=True)
    manifest = {"name": "Miwa Chibi (Live)", "frame_size": CANVAS, "fps_suggested": 7,
                "source": "pacote_original/ (2 folhas transparentes enviadas pelo usuário)", "sequences": {}}
    for seq, refs in MIWA_SEQUENCES.items():
        names = []
        for i, ref in enumerate(refs, 1):
            im = crops[ref]
            scale = base * norm[ref[0]]
            im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.LANCZOS)
            canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
            canvas.alpha_composite(im, ((CANVAS - im.width) // 2, CANVAS - 4 - im.height))   # feet aligned
            name = f"frames/{seq}_{i:02d}.png"
            _clean(canvas).save(out / name, optimize=True)
            names.append(name)
        manifest["sequences"][seq] = {"frames": names, "from": refs}
    orig = out / "pacote_original"
    orig.mkdir(exist_ok=True)
    shutil.copy2(sheet_a, orig / "miwa_chibi_folha_A.png")
    shutil.copy2(sheet_b, orig / "miwa_chibi_folha_B.png")
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest


def build_kaguya_chibi(pack: Path, out: Path) -> dict:
    src = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    frames = out / "frames"
    if frames.exists():
        shutil.rmtree(frames)
    frames.mkdir(parents=True)
    manifest = {"name": "Kaguya Chibi (Live)", "frame_size": src.get("frame_width", 128),
                "fps_suggested": src.get("fps_suggested", 7), "frame_durations_ms": src.get("frame_durations_ms"),
                "source": "pacote_original/ (kaguya_chibi_talk_v1)", "sequences": {}}
    for seq, files in src["sequences"].items():
        names = []
        for f in files:
            shutil.copy2(pack / f, out / f)
            names.append(f)
        manifest["sequences"][seq] = {"frames": names}
    orig = out / "pacote_original"
    if orig.exists():
        shutil.rmtree(orig)
    orig.mkdir()
    for f in ("LEIA_ME.txt", "manifest.json"):
        if (pack / f).exists():
            shutil.copy2(pack / f, orig / f)
    shutil.copytree(pack / "sheets", orig / "sheets")
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest


def build_portraits(sheets: list[Path], out: Path, height: int = 320) -> None:
    ims = [Image.open(p).convert("RGBA") for p in sheets]
    cw, ch = ims[0].width // 3, ims[0].height // 2
    cell = {}
    for s, im in enumerate(ims, 1):
        for i in range(6):
            x, y = (i % 3) * cw, (i // 3) * ch
            cell[(s, i + 1)] = im.crop((x, y, x + cw, y + ch))
    # one framing for every drawing: union of what is visible in all cells
    union = None
    for c in cell.values():
        bb = Image.fromarray((np.array(c)[:, :, 3] > 24).astype("uint8") * 255).getbbox()
        if bb:
            union = bb if union is None else (min(union[0], bb[0]), min(union[1], bb[1]),
                                              max(union[2], bb[2]), max(union[3], bb[3]))
    scale = height / (union[3] - union[1])

    def render(key):
        im = _clean(cell[key].crop(union))
        return im.resize((round(im.width * scale), height), Image.LANCZOS)
    expr = out / "expressoes"
    expr.mkdir(parents=True, exist_ok=True)
    for name, key in PORTRAIT_EXPRESSIONS.items():
        render(key).save(expr / f"kaguya_{name}.png", optimize=True)
    for seq, keys in PORTRAIT_TALK.items():
        d = out / "fala" / seq
        d.mkdir(parents=True, exist_ok=True)
        for i, key in enumerate(keys, 1):
            render(key).save(d / f"{seq}_{i:02d}.png", optimize=True)
    orig = out / "pacote_original"
    orig.mkdir(exist_ok=True)
    for i, p in enumerate(sheets, 1):
        shutil.copy2(p, orig / f"kaguya_retratos_{i}.png")


def main(argv: list[str]) -> int:
    pack, ma, mb, p1, p2, p3 = (Path(a) for a in argv)
    k = build_kaguya_chibi(pack, MASCOTS / "kaguya_chibi")
    m = build_miwa(ma, mb, MASCOTS / "miwa_chibi")
    build_portraits([p1, p2, p3], MASCOTS / "kaguya_v3")
    print("Kaguya chibi:", {s: len(v["frames"]) for s, v in k["sequences"].items()})
    print("Miwa chibi:", {s: len(v["frames"]) for s, v in m["sequences"].items()})
    print("Kaguya V3:", len(PORTRAIT_EXPRESSIONS), "expressões,", len(PORTRAIT_TALK), "sequências de fala")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
