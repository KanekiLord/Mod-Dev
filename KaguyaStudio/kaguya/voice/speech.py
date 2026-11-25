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


def split_sentences(buffer: str, final: bool = False, min_chars: int = 18) -> tuple[list[str], str]:
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
            out.append(piece)
        pending = ""
    rest = (pending + buffer[pos:]).lstrip()
    if final and rest.strip():
        out.append(re.sub(r"\s+", " ", rest).strip())
        rest = ""
    return out, rest


class SpeechQueue:
    """One synthesis worker + one playback worker, connected by a small queue."""

    def __init__(self, synth: Callable[[str, str], tuple], play: Callable[[object, int, threading.Event], None],
                 on_state: Callable[[str, str], None] | None = None):
        self._synth, self._play, self._on_state = synth, play, on_state
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
            except Exception:
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
            self._set(True, voice)
            try:
                self._play(audio, sr, self._stop)
            except Exception:
                pass
            if self._audio.empty() and self._texts.empty():
                self._set(False, voice)


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
            env = dict(os.environ, KAGUYA_TTS_VOICE=voice_name_getter(agent) or "", KAGUYA_TTS_RATE="1",
                       KAGUYA_TTS_VOLUME="100", KAGUYA_TTS_WAV=wav)
            subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_SPEAK], input=text,
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
