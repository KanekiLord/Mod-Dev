"""Fluid speech output: text is split into sentences and synthesised one sentence ahead of
playback, so the voice starts quickly and never waits between sentences. Interruptible at any
moment (barge-in). Uses neural voices when available, otherwise Windows SAPI rendered to WAV.
"""
from __future__ import annotations

import os
import queue
import re
import tempfile
import threading
from typing import Callable

from .tts import clean_for_speech

_END = re.compile(r"(.+?[.!?…:;](?:[\"')\]]*)(?=\s|$))|(.+?\n)", re.S)


def _chunk(piece: str, max_chars: int = 110, min_cut: int = 35) -> list[str]:
    """Long sentences are cut at a comma so the first audio starts sooner."""
    if len(piece) <= max_chars:
        return [piece]
    cut = piece.find(", ", min_cut)
    if cut == -1 or len(piece) - cut < 15:
        return [piece]
    return [piece[:cut + 1].strip()] + _chunk(piece[cut + 2:].strip(), max_chars)


def split_sentences(buffer: str, final: bool = False, min_chars: int = 18, first_max: int | None = None
                    ) -> tuple[list[str], str]:
    """Take complete sentences out of a streaming buffer. Very short fragments are joined to the
    next one so the voice does not stutter; with ``final`` the remainder is flushed too."""
    out, pos, pending = [], 0, ""
    for m in _END.finditer(buffer):
        piece = re.sub(r"\s+", " ", pending + m.group(0)).strip()
        pos = m.end()
        if len(piece) < min_chars and not final:
            pending = piece + " "
            continue
        if piece:
            out.extend(_chunk(piece))
        pending = ""
    rest = (pending + buffer[pos:]).lstrip()
    if final and rest.strip():
        out.extend(_chunk(re.sub(r"\s+", " ", rest).strip()))
        rest = ""
    if first_max and out and len(out[0]) > first_max:
        out = _chunk(out[0], first_max, 20) + out[1:]
    return out, rest


class SpeechQueue:
    """One synthesis worker + one playback worker, connected by a small queue."""

    def __init__(self, synth: Callable[[str, str], tuple], play: Callable[[object, int, threading.Event], None],
                 on_state: Callable[[str, str], None] | None = None, on_error: Callable[[str], None] | None = None):
        self._synth, self._play, self._on_state, self._on_error = synth, play, on_state, on_error
        self._env: list[float] = []          # loudness envelope (20 ms frames) of the sentence being played
        self._env_t0 = 0.0
        self._texts: "queue.Queue[tuple[int, str, str] | None]" = queue.Queue()
        self._audio: "queue.Queue[tuple[int, object, int, str] | None]" = queue.Queue(maxsize=3)
        self._gen = 0
        self._stop = threading.Event()
        self.active = False
        threading.Thread(target=self._synth_loop, daemon=True, name="kaguya-tts-synth").start()
        threading.Thread(target=self._play_loop, daemon=True, name="kaguya-tts-play").start()

    def say(self, text: str, voice: str) -> None:
        text = clean_for_speech(text, limit=4000)
        if text:
            self._texts.put((self._gen, text, voice))

    def stop(self) -> None:
        """Barge-in: drop everything queued and cut the current sentence."""
        self._gen += 1
        self._stop.set()
        for q in (self._texts, self._audio):
            try:
                while True:
                    q.get_nowait()
            except queue.Empty:
                pass
        self._set(False, "")

    @property
    def busy(self) -> bool:
        return self.active or not self._texts.empty() or not self._audio.empty()

    def level(self) -> float:
        """Loudness (0..1) of the audio being heard right now — drives the mascot's mouth."""
        import time as _t
        env = self._env
        if not env or not self.active:
            return 0.0
        i = int((_t.monotonic() - self._env_t0) / 0.02)
        return env[i] if 0 <= i < len(env) else 0.0

    def _set(self, active: bool, voice: str):
        if self.active != active:
            self.active = active
            if self._on_state:
                self._on_state("speaking" if active else "idle", voice)

    def _synth_loop(self):
        while True:
            item = self._texts.get()
            if item is None:
                return
            gen, text, voice = item
            if gen != self._gen:
                continue
            try:
                audio, sr = self._synth(text, voice)
            except Exception as exc:   # never silent: the UI shows it (and nothing stale plays later)
                if self._on_error:
                    self._on_error(f"A voz falhou: {exc}")
                continue
            if gen == self._gen and audio is not None and len(audio):
                self._audio.put((gen, audio, sr, voice))

    def _play_loop(self):
        while True:
            item = self._audio.get()
            if item is None:
                return
            gen, audio, sr, voice = item
            if gen != self._gen:
                continue
            self._stop.clear()
            self._env = envelope(audio, sr)
            import time as _t
            self._env_t0 = _t.monotonic()
            self._set(True, voice)
            try:
                self._play(audio, sr, self._stop)
            except Exception as exc:
                if self._on_error:
                    self._on_error(f"Não foi possível tocar a voz: {exc}")
            self._env = []
            if self._audio.empty() and self._texts.empty():
                self._set(False, voice)


def envelope(audio, sr: int, frame_s: float = 0.02) -> list[float]:
    """Normalised RMS per 20 ms frame (0..1)."""
    try:
        import numpy as np
        a = np.asarray(audio, dtype="float32").reshape(-1)
        n = max(1, int(sr * frame_s))
        frames = len(a) // n
        if frames == 0:
            return []
        rms = np.sqrt(np.mean(a[: frames * n].reshape(frames, n) ** 2, axis=1))
        peak = float(rms.max()) or 1.0
        return [float(x) / peak for x in rms]
    except Exception:
        return []


def sounddevice_player(device_getter: Callable[[], int | None]):
    """Play float32 audio on the chosen output, interruptible."""
    def play(audio, sr, stop: threading.Event):
        import sounddevice as sd
        import time
        sd.play(audio, sr, device=device_getter())
        while sd.get_stream().active:
            if stop.is_set():
                sd.stop()
                return
            time.sleep(0.02)
    return play


_PS_WORKER = (
    "[Console]::InputEncoding=[Text.Encoding]::UTF8;[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
    "Add-Type -AssemblyName System.Speech;"
    "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
    "$pt=$s.GetInstalledVoices()|?{$_.VoiceInfo.Culture.Name -like 'pt*'}|select -First 1;"
    "[Console]::Out.WriteLine('pronto');[Console]::Out.Flush();"
    "while(($line=[Console]::In.ReadLine()) -ne $null){"
    "try{$r=$line|ConvertFrom-Json;"
    "if($r.voice){try{$s.SelectVoice($r.voice)}catch{}}elseif($pt){$s.SelectVoice($pt.VoiceInfo.Name)};"
    "$s.Rate=[int]$r.rate;$s.Volume=100;$s.SetOutputToWaveFile($r.wav);$s.Speak($r.text);$s.SetOutputToNull();"
    "[Console]::Out.WriteLine('ok')}catch{[Console]::Out.WriteLine('erro '+$_.Exception.Message)};"
    "[Console]::Out.Flush()}"
)


class SapiWorker:
    """One PowerShell kept open with System.Speech loaded: each sentence takes a fraction of a second
    instead of starting PowerShell again (2–10 s each on Windows, minutes for a long answer)."""

    def __init__(self, command: list[str] | None = None, start_timeout: float = 40, timeout: float = 60):
        self.command = command or ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_WORKER]
        self.start_timeout, self.timeout = start_timeout, timeout
        self.proc = None
        self._lines: "queue.Queue[str | None]" = queue.Queue()
        self._lock = threading.Lock()

    def _start(self):
        import subprocess
        from .tts import _flags
        self.proc = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                                     bufsize=1, creationflags=_flags())
        lines, proc = queue.Queue(), self.proc
        self._lines = lines

        def reader():
            try:
                for line in proc.stdout:
                    lines.put(line.strip().lstrip("\ufeff"))
            except (OSError, ValueError):
                pass
            lines.put(None)
        threading.Thread(target=reader, daemon=True, name="kaguya-sapi").start()
        self._expect("pronto", self.start_timeout)

    def _expect(self, prefix: str, timeout: float) -> str:
        try:
            line = self._lines.get(timeout=timeout)
        except queue.Empty:
            self.close()
            raise RuntimeError("A voz do Windows não respondeu a tempo.")
        if line is None:
            self.close()
            raise RuntimeError("A voz do Windows encerrou.")
        if not line.startswith(prefix):
            raise RuntimeError(f"Voz do Windows: {line[:200]}")
        return line

    def warm(self) -> None:
        """Open PowerShell ahead of the first sentence (it is the slow part)."""
        with self._lock:
            if self.proc is None or self.proc.poll() is not None:
                self._start()

    def render(self, text: str, voice: str, wav: str, rate: int = 1) -> None:
        import json
        with self._lock:
            if self.proc is None or self.proc.poll() is not None:
                self._start()
            req = json.dumps({"text": text, "voice": voice or "", "rate": int(rate), "wav": wav}, ensure_ascii=False)
            try:
                self.proc.stdin.write(req + "\n")
                self.proc.stdin.flush()
            except OSError:
                self.close()
                raise RuntimeError("A voz do Windows encerrou.")
            self._expect("ok", self.timeout)

    def close(self):
        proc, self.proc = self.proc, None
        if proc is None:
            return
        if proc.poll() is None:
            try:
                proc.stdin.close()
                proc.wait(3)
            except Exception:
                try:
                    proc.kill()
                    proc.wait(3)
                except Exception:
                    pass
        for f in (proc.stdin, proc.stdout):
            try:
                f.close()
            except (OSError, ValueError):
                pass


_WORKER: SapiWorker | None = None


def sapi_worker() -> SapiWorker:
    global _WORKER
    if _WORKER is None:
        _WORKER = SapiWorker()
    return _WORKER


def sapi_synth(voice_name_getter: Callable[[str], str]):
    """Windows SAPI rendered to WAV (fallback when neural voices are not installed)."""
    def synth(text: str, agent: str):
        import subprocess
        import wave
        import numpy as np
        from .tts import _PS_SPEAK, _flags
        fd, wav = tempfile.mkstemp(suffix=".wav", prefix="kaguya-voz-")
        os.close(fd)
        try:
            voice = voice_name_getter(agent) or ""
            try:
                sapi_worker().render(text, voice, wav)          # fast path: PowerShell already open
            except Exception:
                from ..procutil import run
                env = dict(os.environ, KAGUYA_TTS_VOICE=voice, KAGUYA_TTS_RATE="1", KAGUYA_TTS_VOLUME="100",
                           KAGUYA_TTS_WAV=wav)
                run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_SPEAK], input=text,
                    text=True, encoding="utf-8", env=env, capture_output=True, timeout=120, creationflags=_flags())
            with wave.open(wav, "rb") as w:
                data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype("float32") / 32768.0
                return data, w.getframerate()
        finally:
            try:
                os.remove(wav)
            except OSError:
                pass
    return synth
