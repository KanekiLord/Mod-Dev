"""Minimal PNG encoder for screen captures (no Pillow/numpy needed)."""
from __future__ import annotations

import struct
import zlib


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def encode_rgb(width: int, height: int, rows: list[bytes], level: int = 6) -> bytes:
    raw = b"".join(b"\x00" + r for r in rows)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(raw, level)) + _chunk(b"IEND", b""))


def bgra_to_rgb_rows(buf: bytes, width: int, height: int, step: int = 1, bottom_up: bool = False) -> tuple[int, int, list[bytes]]:
    """Convert a BGRA bitmap to RGB rows, keeping every ``step``-th pixel (fast slicing, no per-pixel loop)."""
    stride = width * 4
    rows = []
    ys = range(0, height, step)
    for y in ys:
        src_y = height - 1 - y if bottom_up else y
        row = buf[src_y * stride:(src_y + 1) * stride]
        b, g, r = row[0::4 * step], row[1::4 * step], row[2::4 * step]
        out = bytearray(len(b) * 3)
        out[0::3], out[1::3], out[2::3] = r, g, b
        rows.append(bytes(out))
    return (len(rows[0]) // 3 if rows else 0), len(rows), rows
