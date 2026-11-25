"""Windows media keys: the same Play/Pause, Next and Previous keys a keyboard has.

They act on whatever app Windows considers the current media session (YouTube in a browser, Spotify, Amazon
Music…). The Studio cannot read what those apps play without the WinRT media-session API, so it never claims to.
Used only from the user's own buttons (Spotify's policy forbids voice assistants controlling it).
"""
from __future__ import annotations

import sys

VK = {"play_pause": 0xB3, "next": 0xB0, "previous": 0xB1, "stop": 0xB2}


def available() -> bool:
    return sys.platform == "win32"


def press(key: str) -> bool:
    if not available() or key not in VK:
        return False
    import ctypes
    user32 = ctypes.windll.user32
    KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP = 0x1, 0x2
    user32.keybd_event(VK[key], 0, KEYEVENTF_EXTENDEDKEY, 0)
    user32.keybd_event(VK[key], 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)
    return True
