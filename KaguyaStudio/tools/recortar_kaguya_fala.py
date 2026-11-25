"""Rebuild the Kaguya talk-pack frames from the ORIGINAL sheets with a cleaner cut-out.

The pack's 128 px frames are nearest-neighbour reductions of the 512 px cells of the original sheets
(verified: zero difference), but their transparency left background patches behind and opened holes in
the white hair. Here the background is removed on the original (it is a smooth gradient: a flood fill
from the border that only crosses small colour steps), then reduced the same way. The pack's files are
never modified; the result goes to a new folder.

Usage: python tools/recortar_kaguya_fala.py <pasta kaguya_talk_pack> <pasta de saída>
"""
from collections import deque
from pathlib import Path
import sys

from PIL import Image

CELL, SIZE, OFFSET, STEP = 512, 120, 4, 7


def matte(cell: Image.Image, step: int = STEP) -> Image.Image:
    rgb = cell.load()
    w, h = cell.size
    bg = bytearray(w * h)
    # seeds on the top and side borders only: the dress touches the bottom border
    q = deque((x, 0) for x in range(w))
    q.extend((x, y) for y in range(int(h * 0.8)) for x in (0, w - 1))
    for x, y in list(q):
        bg[y * w + x] = 1
    while q:
        x, y = q.popleft()
        c = rgb[x, y]
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and not bg[ny * w + nx]:
                n = rgb[nx, ny]
                if max(abs(n[0] - c[0]), abs(n[1] - c[1]), abs(n[2] - c[2])) <= step:
                    bg[ny * w + nx] = 1
                    q.append((nx, ny))
    mask = Image.frombytes("L", (w, h), bytes(0 if b else 255 for b in bg))
    return mask


def close_hem(img: Image.Image, rows: int = 14) -> Image.Image:
    """The dress fades into the dark vignette at the bottom border: fill the gaps of the last rows between
    the outermost opaque pixels (colours come from the original, so nothing is invented)."""
    out = img.copy()
    o = out.load()
    w, h = img.size
    for y in range(h - rows, h):
        xs = [x for x in range(w) if o[x, y][3]]
        if len(xs) > 2:
            for x in range(xs[0], xs[-1] + 1):
                if o[x, y][3] == 0:
                    r, g, b, _ = o[x, y]
                    o[x, y] = (r, g, b, 255)
    return out


def fill_small_holes(img: Image.Image, rgb: Image.Image, max_px: int = 45) -> Image.Image:
    """Small transparent pockets fully surrounded by the figure are cut-out mistakes: restore them with
    the original colours. Larger enclosed areas (real gaps between arm and body) stay transparent."""
    out = img.copy()
    o, c = out.load(), rgb.load()
    w, h = img.size
    seen = set()
    for sy in range(h):
        for sx in range(w):
            if o[sx, sy][3] or (sx, sy) in seen:
                continue
            comp, q, border = [], deque([(sx, sy)]), False
            seen.add((sx, sy))
            while q:
                x, y = q.popleft()
                comp.append((x, y))
                if x in (0, w - 1) or y in (0, h - 1):
                    border = True
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h and not o[nx, ny][3] and (nx, ny) not in seen:
                        seen.add((nx, ny))
                        q.append((nx, ny))
            if not border and len(comp) <= max_px:
                for x, y in comp:
                    o[x, y] = (*c[x, y][:3], 255)
    return out


def drop_specks(img: Image.Image, min_px: int = 20) -> Image.Image:
    """Remove small opaque islands left in the background (after the reduction)."""
    a = img.getchannel("A").load()
    w, h = img.size
    seen = set()
    out = img.copy()
    o = out.load()
    for sy in range(h):
        for sx in range(w):
            if a[sx, sy] == 0 or (sx, sy) in seen:
                continue
            comp, q = [], deque([(sx, sy)])
            seen.add((sx, sy))
            while q:
                x, y = q.popleft()
                comp.append((x, y))
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h and a[nx, ny] and (nx, ny) not in seen:
                        seen.add((nx, ny))
                        q.append((nx, ny))
            if len(comp) < min_px:
                for x, y in comp:
                    o[x, y] = (0, 0, 0, 0)
    return out


def rebuild(pack: Path, out: Path) -> list[Path]:
    made = []
    for seq in ("talk_basic", "talk_explaining", "talk_warm"):
        sheet = Image.open(pack / "sheets" / f"{seq}_sheet_original.png").convert("RGB")
        cols = sheet.width // CELL
        (out / seq).mkdir(parents=True, exist_ok=True)
        for i in range(sheet.width // CELL * (sheet.height // CELL)):
            cell = sheet.crop(((i % cols) * CELL, (i // cols) * CELL, (i % cols + 1) * CELL, (i // cols + 1) * CELL))
            m = matte(cell)
            small = cell.resize((SIZE, SIZE), Image.NEAREST).convert("RGBA")
            small.putalpha(m.resize((SIZE, SIZE), Image.NEAREST))
            rgb_small = cell.resize((SIZE, SIZE), Image.NEAREST)
            small = close_hem(Image.merge("RGBA", (*rgb_small.split(), small.getchannel("A"))))
            small = fill_small_holes(small, rgb_small)
            frame = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
            frame.paste(drop_specks(small), (OFFSET, OFFSET))
            p = out / seq / f"{seq}_{i + 1:02d}.png"
            frame.save(p)
            made.append(p)
    return made


if __name__ == "__main__":
    for p in rebuild(Path(sys.argv[1]), Path(sys.argv[2])):
        print(p)
