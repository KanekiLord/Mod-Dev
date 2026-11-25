"""Audio devices: list microphones and outputs, detect plug/unplug, resolve the user's choice.

Choices are stored by **name** (PortAudio indices change when a headset is plugged in).
On Windows each physical device appears once per host API (MME, DirectSound, WASAPI…); only the
default host API is listed so the user sees each device once, and it accepts any sample rate.
"""
from __future__ import annotations

from dataclasses import dataclass
import threading
import time

_lock = threading.Lock()


@dataclass(frozen=True)
class Device:
    index: int
    name: str
    kind: str            # "entrada" | "saida"
    default: bool = False
    samplerate: float = 0.0


def available() -> bool:
    try:
        import sounddevice  # noqa: F401
        import numpy  # noqa: F401
        return True
    except Exception:
        return False


def _query(refresh: bool):
    import sounddevice as sd
    with _lock:
        if refresh:
            # PortAudio only sees hot-plugged devices after re-initialising.
            try:
                sd._terminate()
                sd._initialize()
            except Exception:
                pass
        devices = sd.query_devices()
        default_api = sd.default.hostapi if sd.default.hostapi is not None and sd.default.hostapi >= 0 else 0
        din, dout = sd.default.device if isinstance(sd.default.device, (list, tuple)) else (None, None)
    return devices, default_api, din, dout


def parse(devices, default_api: int, default_in, default_out) -> tuple[list[Device], list[Device]]:
    ins, outs, seen_in, seen_out = [], [], set(), set()
    for i, d in enumerate(devices):
        if d.get("hostapi", 0) != default_api:
            continue
        name = str(d.get("name", f"Dispositivo {i}")).strip()
        if d.get("max_input_channels", 0) > 0 and name not in seen_in:
            seen_in.add(name)
            ins.append(Device(i, name, "entrada", i == default_in, float(d.get("default_samplerate") or 0)))
        if d.get("max_output_channels", 0) > 0 and name not in seen_out:
            seen_out.add(name)
            outs.append(Device(i, name, "saida", i == default_out, float(d.get("default_samplerate") or 0)))
    return ins, outs


def list_devices(refresh: bool = False) -> tuple[list[Device], list[Device]]:
    """(microphones, outputs). Empty lists when sounddevice is unavailable."""
    if not available():
        return [], []
    try:
        return parse(*_query(refresh))
    except Exception:
        return [], []


def resolve(name: str | None, devices: list[Device]) -> Device | None:
    """Find the stored choice; ``None`` means the Windows default (or the choice disappeared)."""
    if not name:
        return None
    for d in devices:
        if d.name == name:
            return d
    low = name.lower()
    return next((d for d in devices if d.name.lower().startswith(low[:20]) or low.startswith(d.name.lower()[:20])), None)


@dataclass
class Change:
    added: list[str]
    removed: list[str]
    kind: str


def diff(before: list[Device], after: list[Device], kind: str) -> Change | None:
    a, b = {d.name for d in before}, {d.name for d in after}
    added, removed = sorted(b - a), sorted(a - b)
    return Change(added, removed, kind) if added or removed else None


def level_of(block) -> float:
    """0..1 loudness for the UI meter."""
    import numpy as np
    if block is None or len(block) == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(np.square(block.astype("float32")))))
    return max(0.0, min(1.0, rms * 8))


def resample(audio, src_rate: float, dst_rate: int = 16000):
    import numpy as np
    if audio is None or len(audio) == 0 or not src_rate or int(src_rate) == dst_rate:
        return audio
    n = int(round(len(audio) * dst_rate / float(src_rate)))
    x_old = np.linspace(0.0, 1.0, num=len(audio), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n, endpoint=False)
    return np.interp(x_new, x_old, audio).astype("float32")


def play_wav(path: str, device: int | None, stop_event: threading.Event | None = None) -> None:
    """Play a WAV on a chosen output (blocking, interruptible)."""
    import sounddevice as sd
    import wave
    import numpy as np
    with wave.open(path, "rb") as w:
        rate, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        frames = w.readframes(w.getnframes())
    dtype = {1: np.int8, 2: np.int16, 4: np.int32}.get(width, np.int16)
    data = np.frombuffer(frames, dtype=dtype).reshape(-1, ch)
    sd.play(data, rate, device=device)
    while sd.get_stream().active:
        if stop_event is not None and stop_event.is_set():
            sd.stop()
            return
        time.sleep(0.05)
