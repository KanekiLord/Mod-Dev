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
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

SAMPLE_RATE = 16000
MODELS = {"tiny": "≈75 MB, rápido, menos preciso", "base": "≈145 MB, bom equilíbrio",
          "small": "≈480 MB, mais preciso (recomendado para pt-BR)", "medium": "≈1,5 GB, lento em CPU"}
MODEL_BYTES = {"tiny": 75_000_000, "base": 145_000_000, "small": 484_000_000, "medium": 1_530_000_000}
INSTALL_CMD = "pip install faster-whisper sounddevice numpy"


class ModelMissing(RuntimeError):
    """The transcription model was never downloaded (the UI asks before downloading)."""


def model_cached(model_dir: Path, model: str) -> bool:
    root = Path(model_dir)
    return root.exists() and any(root.glob(f"**/*faster-whisper-{model}/**/model.bin"))


def _bytes(root: Path) -> int:
    total = 0
    for p in root.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            pass
    return total


def model_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--baixar-modelo"]
    return [sys.executable, "-m", "kaguya.voice.stt"]


def download(model_dir: Path, model: str, progress=None, cancel: threading.Event | None = None,
             stall_s: float = 120) -> None:
    """Download the model in a separate process (real cancel), reporting bytes; a stalled
    download is stopped with an explanation instead of waiting forever."""
    from ..procutil import kill_tree
    root = Path(model_dir)
    root.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, HF_HUB_DISABLE_TELEMETRY="1", HF_HUB_DISABLE_PROGRESS_BARS="1",
               HF_HUB_DOWNLOAD_TIMEOUT="30", HF_HUB_ETAG_TIMEOUT="20",
               HF_HUB_DISABLE_XET="1")   # plain HTTPS into this folder: real progress, nothing cached elsewhere
    if not getattr(sys, "frozen", False):
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2]) + os.pathsep + env.get("PYTHONPATH", "")
    log = root / f".baixando-{model}.log"
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    with log.open("w", encoding="utf-8") as fh:
        proc = subprocess.Popen([*model_command(), model, str(root)], stdout=fh, stderr=fh, stdin=subprocess.DEVNULL,
                                env=env, creationflags=flags, start_new_session=(os.name != "nt"))
    start = last = _bytes(root)
    last_t = time.monotonic()
    total = MODEL_BYTES.get(model)
    while True:
        try:
            proc.wait(0.5)
            break
        except subprocess.TimeoutExpired:
            pass
        now = _bytes(root)
        if now != last:
            last, last_t = now, time.monotonic()
        if progress:
            progress(max(0, now - start), total)
        if cancel is not None and cancel.is_set():
            kill_tree(proc)
            raise RuntimeError("Download cancelado.")
        if time.monotonic() - last_t > stall_s:
            kill_tree(proc)
            raise RuntimeError(f"O download parou há {int(stall_s)} s sem receber nada. Verifique a internet ou se o "
                               "antivírus/firewall bloqueia huggingface.co, e tente de novo.")
    if proc.returncode != 0 or not model_cached(root, model):
        try:
            tail = [l for l in log.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()][-3:]
        except OSError:
            tail = []
        raise RuntimeError("Não foi possível baixar o modelo de transcrição." + (" " + " | ".join(tail)[-400:] if tail else ""))
    try:
        log.unlink()
    except OSError:
        pass


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
    cached = model_cached(model_dir, model)
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


# what Whisper "hears" in fan noise, wind or silence (it learned these from subtitled videos)
HALLUCINATIONS = re.compile(
    r"(legendas? (pela|por)|amara\.org|obrigad[oa] por assistir|inscreva-se|se inscreva|deixe (seu|o seu) like|"
    r"ative o sininho|tchau,? tchau|^\W*(\.|…)+\W*$|^\W*m[uú]sica\W*$|^\W*\[.*\]\W*$)", re.I)


def clean_segments(segments) -> str:
    """Join Whisper segments, dropping the ones the model itself marks as non-speech and known hallucinations."""
    out = []
    for seg in segments:
        text = (getattr(seg, "text", "") or "").strip()
        if not text:
            continue
        nsp = getattr(seg, "no_speech_prob", 0.0) or 0.0
        logp = getattr(seg, "avg_logprob", 0.0) or 0.0
        if nsp > 0.6 and logp < -0.7:
            continue
        if HALLUCINATIONS.search(text):
            continue
        out.append(text)
    return " ".join(out).strip()


class Transcriber:
    def __init__(self, model_dir: Path, model: str = "small"):
        self.model_dir, self.model_name = Path(model_dir), model
        self._model = None
        self._lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self):
        """Load from disk only — never from the internet (a cached model used to be re-checked online on
        every start, which froze with a slow network or a firewall). Download first with ``download``."""
        with self._lock:
            if self._model is None:
                if not model_cached(self.model_dir, self.model_name):
                    raise ModelMissing(f"O modelo de transcrição '{self.model_name}' ainda não foi baixado.")
                from faster_whisper import WhisperModel
                self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8",
                                           download_root=str(self.model_dir), local_files_only=True)
        return self._model

    def transcribe(self, audio, prompt: str | None = None) -> str:
        if audio is None or len(audio) < SAMPLE_RATE // 4:
            return ""
        segments, _info = self.load().transcribe(audio, language="pt", vad_filter=True, beam_size=1,
                                                 initial_prompt=prompt)
        return clean_segments(segments)


def main(argv: list[str] | None = None) -> int:
    """``--baixar-modelo <tamanho> <pasta>``: the download process started by ``download``."""
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] not in MODELS:
        print("uso: <tiny|base|small|medium> <pasta>", file=sys.stderr)
        return 2
    from faster_whisper.utils import download_model
    print(download_model(argv[0], cache_dir=argv[1]), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
