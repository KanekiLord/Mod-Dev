"""Mouse, keyboard, windows and screen capture.

* ``WindowsBackend``: Windows API through ctypes (SendInput, EnumWindows, GDI BitBlt). No extra
  packages, nothing installed. The process is made DPI-aware so coordinates are physical pixels.
* ``FakeBackend``: deterministic stand-in for tests (records every action, fake windows, fake screen).
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import sys
import time

from .png import bgra_to_rgb_rows, encode_rgb


@dataclass
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    def contains(self, x: int, y: int) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom


@dataclass
class Window:
    handle: int
    title: str
    rect: Rect


KEY_ALIASES = {"control": "ctrl", "ctl": "ctrl", "return": "enter", "escape": "esc", "del": "delete",
               "pgup": "pageup", "pgdn": "pagedown", "windows": "win", "cmd": "win", "super": "win",
               "seta para cima": "up", "seta para baixo": "down", "espaco": "space", "espaço": "space"}


def parse_keys(combo: str) -> list[str]:
    parts = [p.strip().lower() for p in (combo or "").replace(" + ", "+").split("+") if p.strip()]
    if not parts:
        raise ValueError("Nenhuma tecla informada.")
    return [KEY_ALIASES.get(p, p) for p in parts]


class Backend:
    name = "base"

    def screen(self) -> Rect: ...
    def cursor(self) -> tuple[int, int]: ...
    def move(self, x: int, y: int) -> None: ...
    def click(self, x: int, y: int, button: str = "left", count: int = 1) -> None: ...
    def drag(self, x1: int, y1: int, x2: int, y2: int) -> None: ...
    def scroll(self, x: int, y: int, amount: int) -> None: ...
    def type_text(self, text: str) -> None: ...
    def keys(self, names: list[str]) -> None: ...
    def windows(self) -> list[Window]: ...
    def focus(self, w: Window) -> bool: ...
    def foreground(self) -> int: ...
    def capture(self, rect: Rect, max_width: int = 1280) -> tuple[bytes, int, int, int]:
        """PNG bytes, image width, image height, downscale step."""


# --------------------------------------------------------------------------- fake (tests)
class FakeBackend(Backend):
    name = "fake"

    def __init__(self, log_path: str | None = None):
        self.log_path = log_path or os.environ.get("KAGUYA_DESKTOP_FAKE_LOG")
        self.pos = (400, 300)
        self.focused = None
        self.wins = [Window(1, "Minecraft 1.7.10", Rect(100, 50, 900, 650)),
                     Window(2, "Navegador — banco", Rect(0, 0, 1920, 1080)),
                     Window(3, "Kaguya Studio", Rect(200, 100, 1600, 1000))]

    def _log(self, **kw):
        if self.log_path:
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(kw, ensure_ascii=False) + "\n")

    def screen(self) -> Rect:
        return Rect(0, 0, 1920, 1080)

    def cursor(self):
        return self.pos

    def move(self, x, y):
        self.pos = (x, y)
        self._log(action="move", x=x, y=y)

    def click(self, x, y, button="left", count=1):
        self.pos = (x, y)
        self._log(action="click", x=x, y=y, button=button, count=count)

    def drag(self, x1, y1, x2, y2):
        self.pos = (x2, y2)
        self._log(action="drag", x1=x1, y1=y1, x2=x2, y2=y2)

    def scroll(self, x, y, amount):
        self._log(action="scroll", x=x, y=y, amount=amount)

    def type_text(self, text):
        self._log(action="type", text=text)

    def keys(self, names):
        self._log(action="keys", keys=names)

    def hold(self, names, seconds):
        self._log(action="hold", keys=names, seconds=seconds)

    def windows(self):
        return list(self.wins)

    def focus(self, w):
        self.focused = w.handle
        self._log(action="focus", title=w.title)
        return True

    def foreground(self):
        return self.focused or 0

    def capture(self, rect, max_width=1280):
        step = 1
        while rect.width // step > max_width:
            step += 1
        w, h = max(1, rect.width // step), max(1, rect.height // step)
        row = bytes((i % 200) for i in range(w * 3))
        rows = [row] * h
        return encode_rgb(w, h, rows, level=1), w, h, step


# --------------------------------------------------------------------------- Windows
class WindowsBackend(Backend):
    name = "windows"

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ct, self.wt = ctypes, wintypes
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        try:  # physical pixels everywhere (per-monitor v2), otherwise system-aware
            self.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                self.user32.SetProcessDPIAware()
        self._define()

    def _define(self):
        ct, wt = self.ct, self.wt
        ULONG_PTR = ct.c_size_t

        class MOUSEINPUT(ct.Structure):
            _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD),
                        ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]

        class KEYBDINPUT(ct.Structure):
            _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                        ("dwExtraInfo", ULONG_PTR)]

        class HARDWAREINPUT(ct.Structure):
            _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]

        class _U(ct.Union):
            _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

        class INPUT(ct.Structure):
            _anonymous_ = ("u",)
            _fields_ = [("type", wt.DWORD), ("u", _U)]

        self.INPUT, self.MOUSEINPUT, self.KEYBDINPUT = INPUT, MOUSEINPUT, KEYBDINPUT
        self.user32.SendInput.argtypes = (wt.UINT, ct.POINTER(INPUT), ct.c_int)
        self.user32.GetWindowTextLengthW.argtypes = (wt.HWND,)
        self.user32.GetWindowTextW.argtypes = (wt.HWND, wt.LPWSTR, ct.c_int)
        self.user32.GetWindowRect.argtypes = (wt.HWND, ct.POINTER(wt.RECT))
        self.user32.IsWindowVisible.argtypes = (wt.HWND,)
        self.user32.IsIconic.argtypes = (wt.HWND,)
        self.user32.SetForegroundWindow.argtypes = (wt.HWND,)
        self.user32.ShowWindow.argtypes = (wt.HWND, ct.c_int)
        self.user32.GetDC.argtypes = (wt.HWND,)
        self.user32.GetDC.restype = wt.HDC
        self.user32.ReleaseDC.argtypes = (wt.HWND, wt.HDC)
        self.gdi32.CreateCompatibleDC.argtypes = (wt.HDC,)
        self.gdi32.CreateCompatibleDC.restype = wt.HDC
        self.gdi32.CreateCompatibleBitmap.argtypes = (wt.HDC, ct.c_int, ct.c_int)
        self.gdi32.CreateCompatibleBitmap.restype = wt.HBITMAP
        self.gdi32.SelectObject.argtypes = (wt.HDC, wt.HGDIOBJ)
        self.gdi32.SelectObject.restype = wt.HGDIOBJ
        self.gdi32.BitBlt.argtypes = (wt.HDC, ct.c_int, ct.c_int, ct.c_int, ct.c_int, wt.HDC, ct.c_int, ct.c_int,
                                      wt.DWORD)
        self.gdi32.GetDIBits.argtypes = (wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ct.c_void_p, ct.c_void_p, wt.UINT)
        self.gdi32.DeleteObject.argtypes = (wt.HGDIOBJ,)
        self.gdi32.DeleteDC.argtypes = (wt.HDC,)

    # ----------------------------------------------------------------- input
    def _send(self, *inputs):
        arr = (self.INPUT * len(inputs))(*inputs)
        if self.user32.SendInput(len(inputs), arr, self.ct.sizeof(self.INPUT)) != len(inputs):
            raise OSError("O Windows bloqueou a entrada simulada (por exemplo, numa janela de administrador).")

    def _mouse(self, flags, data=0):
        i = self.INPUT(type=0)
        i.mi = self.MOUSEINPUT(0, 0, data & 0xFFFFFFFF, flags, 0, 0)
        return i

    def _key(self, vk=0, scan=0, flags=0):
        i = self.INPUT(type=1)
        i.ki = self.KEYBDINPUT(vk, scan, flags, 0, 0)
        return i

    def screen(self) -> Rect:
        g = self.user32.GetSystemMetrics
        x, y = g(76), g(77)  # virtual screen (all monitors)
        return Rect(x, y, x + g(78), y + g(79))

    def cursor(self):
        p = self.wt.POINT()
        self.user32.GetCursorPos(self.ct.byref(p))
        return p.x, p.y

    def move(self, x, y):
        self.user32.SetCursorPos(int(x), int(y))

    BUTTONS = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010), "middle": (0x0020, 0x0040)}

    def click(self, x, y, button="left", count=1):
        down, up = self.BUTTONS.get(button, self.BUTTONS["left"])
        self.move(x, y)
        time.sleep(0.03)
        for _ in range(max(1, min(3, count))):
            self._send(self._mouse(down), self._mouse(up))
            time.sleep(0.05)

    def drag(self, x1, y1, x2, y2):
        self.move(x1, y1)
        time.sleep(0.05)
        self._send(self._mouse(0x0002))
        steps = 12
        for i in range(1, steps + 1):
            self.move(x1 + (x2 - x1) * i // steps, y1 + (y2 - y1) * i // steps)
            time.sleep(0.015)
        self._send(self._mouse(0x0004))

    def scroll(self, x, y, amount):
        self.move(x, y)
        self._send(self._mouse(0x0800, int(amount) * 120))

    def type_text(self, text):
        KEYUP, UNICODE = 0x0002, 0x0004
        for ch in text:
            if ch == "\n":
                self._send(self._key(0x0D), self._key(0x0D, flags=KEYUP))
            elif ch == "\t":
                self._send(self._key(0x09), self._key(0x09, flags=KEYUP))
            else:
                for unit in _utf16_units(ch):
                    self._send(self._key(0, unit, UNICODE), self._key(0, unit, UNICODE | KEYUP))
            time.sleep(0.008)

    VK = {"ctrl": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B, "enter": 0x0D, "esc": 0x1B, "tab": 0x09,
          "backspace": 0x08, "delete": 0x2E, "space": 0x20, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
          "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "insert": 0x2D, "printscreen": 0x2C,
          **{f"f{i}": 0x6F + i for i in range(1, 13)}}
    EXTENDED = {0x26, 0x28, 0x25, 0x27, 0x24, 0x23, 0x21, 0x22, 0x2D, 0x2E}

    def _vk(self, name: str) -> int:
        if name in self.VK:
            return self.VK[name]
        if len(name) == 1 and name.isalnum():
            return ord(name.upper())
        raise ValueError(f"Tecla desconhecida: {name}")

    def keys(self, names):
        vks = [self._vk(n) for n in names]
        KEYUP, EXT = 0x0002, 0x0001
        down = [self._key(v, flags=EXT if v in self.EXTENDED else 0) for v in vks]
        up = [self._key(v, flags=KEYUP | (EXT if v in self.EXTENDED else 0)) for v in reversed(vks)]
        self._send(*down)
        time.sleep(0.04)
        self._send(*up)

    def hold(self, names, seconds):
        """Hold keys down (e.g. W to walk in a game), then release."""
        vks = [self._vk(n) for n in names]
        KEYUP, EXT = 0x0002, 0x0001
        self._send(*[self._key(v, flags=EXT if v in self.EXTENDED else 0) for v in vks])
        try:
            time.sleep(seconds)
        finally:
            self._send(*[self._key(v, flags=KEYUP | (EXT if v in self.EXTENDED else 0)) for v in reversed(vks)])

    # --------------------------------------------------------------- windows
    def windows(self):
        ct, wt = self.ct, self.wt
        out: list[Window] = []
        proto = ct.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

        def cb(hwnd, _):
            if not self.user32.IsWindowVisible(hwnd) or self.user32.IsIconic(hwnd):
                return True
            n = self.user32.GetWindowTextLengthW(hwnd)
            if n <= 0:
                return True
            buf = ct.create_unicode_buffer(n + 1)
            self.user32.GetWindowTextW(hwnd, buf, n + 1)
            r = wt.RECT()
            self.user32.GetWindowRect(hwnd, ct.byref(r))
            if r.right - r.left > 40 and r.bottom - r.top > 40:
                out.append(Window(int(hwnd), buf.value, Rect(r.left, r.top, r.right, r.bottom)))
            return True
        self.user32.EnumWindows(proto(cb), 0)
        return out

    def focus(self, w):
        self.user32.ShowWindow(w.handle, 9)  # SW_RESTORE
        # Windows only lets the foreground process change focus; a harmless Alt tap unlocks it.
        self._send(self._key(0x12), self._key(0x12, flags=0x0002))
        ok = bool(self.user32.SetForegroundWindow(w.handle))
        time.sleep(0.15)
        return ok

    def foreground(self):
        return int(self.user32.GetForegroundWindow() or 0)

    # --------------------------------------------------------------- capture
    def capture(self, rect, max_width=1280):
        ct, wt = self.ct, self.wt
        w, h = rect.width, rect.height
        if w <= 0 or h <= 0:
            raise ValueError("Área de captura vazia.")
        screen_dc = self.user32.GetDC(None)
        mem_dc = self.gdi32.CreateCompatibleDC(screen_dc)
        bmp = self.gdi32.CreateCompatibleBitmap(screen_dc, w, h)
        old = self.gdi32.SelectObject(mem_dc, bmp)
        try:
            SRCCOPY, CAPTUREBLT = 0x00CC0020, 0x40000000
            if not self.gdi32.BitBlt(mem_dc, 0, 0, w, h, screen_dc, rect.left, rect.top, SRCCOPY | CAPTUREBLT):
                raise OSError("Falha ao capturar a tela.")

            class BITMAPINFOHEADER(ct.Structure):
                _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                            ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                            ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                            ("biClrImportant", wt.DWORD)]
            bih = BITMAPINFOHEADER(ct.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)  # top-down
            buf = ct.create_string_buffer(w * h * 4)
            # the header is followed by an (unused for 32 bpp) colour table; give GetDIBits room for it
            info = ct.create_string_buffer(ct.sizeof(BITMAPINFOHEADER) + 16)
            ct.memmove(info, ct.byref(bih), ct.sizeof(BITMAPINFOHEADER))
            if not self.gdi32.GetDIBits(mem_dc, bmp, 0, h, buf, info, 0):
                raise OSError("Falha ao ler a captura de tela.")
            data = buf.raw
        finally:
            self.gdi32.SelectObject(mem_dc, old)
            self.gdi32.DeleteObject(bmp)
            self.gdi32.DeleteDC(mem_dc)
            self.user32.ReleaseDC(None, screen_dc)
        step = 1
        while w // step > max_width:
            step += 1
        iw, ih, rows = bgra_to_rgb_rows(data, w, h, step)
        return encode_rgb(iw, ih, rows), iw, ih, step


def _utf16_units(ch: str) -> list[int]:
    """Characters outside the BMP are sent as two UTF-16 code units (surrogates)."""
    raw = ch.encode("utf-16-le")
    return [int.from_bytes(raw[i:i + 2], "little") for i in range(0, len(raw), 2)]


def get_backend() -> Backend:
    kind = os.environ.get("KAGUYA_DESKTOP_BACKEND", "")
    if kind == "fake":
        return FakeBackend()
    if sys.platform == "win32":
        return WindowsBackend()
    raise RuntimeError("O controle do computador só está disponível no Windows.")
