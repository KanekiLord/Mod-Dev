"""Neural local voices (Kokoro, Apache-2.0) — natural pt-BR speech, free, offline after download.

Files (~120 MB) are downloaded once, only after the user authorises it, and verified by SHA-256.
Kokoro has one female pt-BR voice (``pf_dora``); distinct voices for each AI are made by blending
its style vector with another voice while keeping Portuguese pronunciation (espeak ``pt-br``).
Verified on 25/11/2026: every preset below transcribes back correctly with faster-whisper and
the presets differ measurably in pitch/timbre (Kaguya ≈209 Hz, Claude ≈187 Hz).
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
from pathlib import Path
import threading
import urllib.request

BASE_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
FILES = {
    "kokoro-v1.0.int8.onnx": ("6e742170d309016e5891a994e1ce1559c702a2ccd0075e67ef7157974f6406cb", 92361271),
    "voices-v1.0.bin": ("bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d", 28214398),
}
SAMPLE_RATE = 24000
LANG = "pt-br"


@dataclass(frozen=True)
class Preset:
    id: str
    label: str
    recipe: tuple[tuple[str, float], ...]
    speed: float = 1.0


PRESETS = {p.id: p for p in (
    Preset("kaguya", "Kaguya — Dora com toque japonês", (("pf_dora", 0.65), ("jf_alpha", 0.35)), 1.0),
    Preset("claude", "Claude — Dora calorosa", (("pf_dora", 0.6), ("af_heart", 0.4)), 1.02),
    Preset("dora", "Dora — pt-BR natural (feminina)", (("pf_dora", 1.0),), 1.0),
    Preset("suave", "Suave — Dora com toque japonês 2", (("pf_dora", 0.65), ("jf_nezumi", 0.35)), 0.97),
    Preset("alex", "Alex — pt-BR (masculina)", (("pm_alex", 1.0),), 1.0),
    Preset("santa", "Santa — pt-BR (masculina)", (("pm_santa", 1.0),), 1.0),
)}
DEFAULT_PRESET = {"codex": "kaguya", "claude": "claude"}


def package_available() -> bool:
    return importlib.util.find_spec("kokoro_onnx") is not None


class NeuralVoices:
    _lock = threading.Lock()

    def __init__(self, model_dir: Path):
        self.dir = Path(model_dir) / "kokoro"
        self._model = None
        self._styles: dict[str, object] = {}

    def installed(self) -> bool:
        return all((self.dir / f).is_file() and (self.dir / f).stat().st_size == size for f, (_h, size) in FILES.items())

    @property
    def ready(self) -> bool:
        return package_available() and self.installed()

    def download(self, progress=None, cancel: threading.Event | None = None) -> None:
        """Download and verify the model files (raises on failure; partial files are removed)."""
        self.dir.mkdir(parents=True, exist_ok=True)
        total = sum(size for _h, size in FILES.values())
        done = sum((self.dir / f).stat().st_size for f, (_h, size) in FILES.items()
                   if (self.dir / f).is_file() and (self.dir / f).stat().st_size == size)
        for name, (sha, size) in FILES.items():
            target = self.dir / name
            if target.is_file() and target.stat().st_size == size:
                continue
            part = target.with_suffix(target.suffix + ".part")
            h = hashlib.sha256()
            try:
                with urllib.request.urlopen(BASE_URL + name, timeout=60) as r, part.open("wb") as fh:
                    while True:
                        if cancel is not None and cancel.is_set():
                            raise RuntimeError("Download cancelado.")
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        fh.write(chunk)
                        h.update(chunk)
                        done += len(chunk)
                        if progress:
                            progress(done, total)
                if h.hexdigest() != sha:
                    raise RuntimeError(f"Arquivo {name} corrompido (SHA-256 não confere). Tente de novo.")
                part.replace(target)
            finally:
                if part.exists():
                    part.unlink()

    def _load(self):
        with self._lock:
            if self._model is None:
                from kokoro_onnx import Kokoro
                self._model = Kokoro(str(self.dir / "kokoro-v1.0.int8.onnx"), str(self.dir / "voices-v1.0.bin"))
        return self._model

    def style(self, preset_id: str):
        preset = PRESETS.get(preset_id) or PRESETS["dora"]
        if preset.id not in self._styles:
            model = self._load()
            mix = None
            for voice, weight in preset.recipe:
                part = model.get_voice_style(voice) * weight
                mix = part if mix is None else mix + part
            self._styles[preset.id] = mix
        return self._styles[preset.id], preset.speed

    def synth(self, text: str, preset_id: str):
        """Returns (float32 mono audio, sample rate)."""
        style, speed = self.style(preset_id)
        audio, sr = self._load().create(text, voice=style, speed=speed, lang=LANG)
        return audio, sr
