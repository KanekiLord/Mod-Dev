"""Local speech-to-text (push-to-talk) with optional, user-approved dependencies.

* Recording: ``sounddevice`` (PortAudio) — microphone is opened only while the user holds /
  toggles the talk button.
* Transcription: ``faster-whisper`` running on CPU (int8). The model (e.g. ``small`` ≈ 0.5 GB,
  ``base`` ≈ 0.15 GB) is downloaded once, only after the user consents in Configurações.
Nothing is sent to a paid API. If a dependency is missing, the UI shows exactly what.
"""
from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from pathlib import Path
import threading
import time

SAMPLE_RATE = 16000
MODELS = {"tiny": "≈75 MB, rápido, menos preciso", "base": "≈145 MB, bom equilíbrio",
          "small": "≈480 MB, mais preciso (recomendado para pt-BR)", "medium": "≈1,5 GB, lento em CPU"}
INSTALL_CMD = "pip install faster-whisper sounddevice numpy"


@dataclass
class VoiceStatus:
    recorder: bool
    transcriber: bool
    missing: list[str]
    model_cached: bool

    @property
    def ready(self) -> bool:
        return self.recorder and self.transcriber


def status(model_dir: Path, model: str = "small") -> VoiceStatus:
    missing = [m for m in ("numpy", "sounddevice", "faster_whisper") if importlib.util.find_spec(m) is None]
    cached = any(Path(model_dir).glob(f"**/*{model}*/**/model.bin")) if Path(model_dir).exists() else False
    return VoiceStatus(recorder="sounddevice" not in missing and "numpy" not in missing,
                       transcriber="faster_whisper" not in missing, missing=missing, model_cached=cached)


def input_devices() -> list[tuple[int, str]]:
    from .devices import list_devices
    return [(d.index, d.name) for d in list_devices()[0]]


class Recorder:
    """Push-to-talk recorder. Records at the device's own rate and converts to 16 kHz.
    ``level`` receives 0..1 for the UI meter."""

    def __init__(self, device: int | None = None, max_seconds: int = 90, level=None):
        self.device, self.max_seconds, self.level = device, max_seconds, level
        self._chunks = []
        self._stream = None
        self._started = 0.0
        self.rate = SAMPLE_RATE

    def start(self) -> None:
        import sounddevice as sd
        from .devices import level_of
        self._chunks = []
        self._started = time.monotonic()
        try:
            info = sd.query_devices(self.device, "input")
            self.rate = int(info.get("default_samplerate") or SAMPLE_RATE)
        except Exception:
            self.rate = SAMPLE_RATE

        def cb(data, frames, t, status_):
            self._chunks.append(data.copy())
            if self.level:
                self.level(level_of(data))
            if time.monotonic() - self._started > self.max_seconds:
                raise sd.CallbackStop()
        self._stream = sd.InputStream(samplerate=self.rate, channels=1, dtype="float32", device=self.device,
                                      callback=cb)
        self._stream.start()

    def stop(self):
        import numpy as np
        from .devices import resample
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if not self._chunks:
            return np.zeros(0, dtype="float32")
        return resample(np.concatenate(self._chunks)[:, 0], self.rate, SAMPLE_RATE)


class Transcriber:
    _lock = threading.Lock()

    def __init__(self, model_dir: Path, model: str = "small"):
        self.model_dir, self.model_name = Path(model_dir), model
        self._model = None

    def load(self):
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel
                self.model_dir.mkdir(parents=True, exist_ok=True)
                self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8",
                                           download_root=str(self.model_dir))
        return self._model

    def transcribe(self, audio, prompt: str | None = None) -> str:
        if audio is None or len(audio) < SAMPLE_RATE // 4:
            return ""
        segments, _info = self.load().transcribe(audio, language="pt", vad_filter=True, beam_size=1,
                                                 initial_prompt=prompt)
        return " ".join(s.text.strip() for s in segments).strip()
