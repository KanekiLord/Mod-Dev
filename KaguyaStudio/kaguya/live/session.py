"""Live session: microphone → VAD → local transcription → persistent conversation → fluent speech.

Qt-independent; the UI receives dict events through ``on_event``. Barge-in: when the user starts
talking while the assistant speaks or thinks, speech stops and the running turn is interrupted.
Spoken commands: "falar com a Claude/Kaguya" switches assistant, "silêncio" stops the voice,
"encerrar" ends Live. Requests to change code become ``[[TAREFA: …]]`` → queued, never executed here.
"""
from __future__ import annotations

import queue
import re
import threading
import time
import unicodedata
from typing import Callable

import numpy as np

from ..voice.speech import split_sentences
from .vad import EnergyVAD, RATE

TASK = re.compile(r"\[\[\s*TAREFA\s*:\s*(.+?)\s*\]\]", re.S | re.I)
PC_TASK = re.compile(r"\[\[\s*PC\s*:\s*(.+?)\s*\]\]", re.S | re.I)
MARKERS = re.compile(r"\[\[\s*(?:TAREFA|PC)\s*:\s*.+?\s*\]\]", re.S | re.I)
NAMES_PROMPT = ("Kaguya, Miwa, Claude, Codex, Kaguya Studio, Minecraft, Forge, Fabric, NeoForge, Gradle, Blockbench, "
                "Obsidian, Segundo Cérebro, NarutoCD, Kodachi, mod, commit, GitHub.")


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    return "".join(c for c in t if not unicodedata.combining(c)).lower().strip(" .,!?")


def command_of(text: str) -> tuple[str, str]:
    """Spoken control commands (never sent to the AI)."""
    n = _norm(text)
    if re.search(r"^(encerrar|encerra|sair do (modo )?live|terminar (o )?live|tchau|ate (mais|logo))\b", n):
        return "end", ""
    if re.search(r"(falar|fala|conversar|passa) com a? ?(claude|clode|cloud|miwa|miua|mi wa)\b|^(claude|cloud|miwa)[, ]*$", n):
        return "switch", "claude"
    if re.search(r"(falar|fala|conversar|passa) com a? ?(kaguya|kaguia|caguia|codex)\b|^(kaguya|codex)[, ]*$", n):
        return "switch", "codex"
    if re.search(r"^(silencio|para de falar|pare de falar|chega)\b", n):
        return "silence", ""
    return "", ""


class LiveSession:
    def __init__(self, *, agent: str, make_conversation: Callable[[str], object], transcribe: Callable[[np.ndarray], str],
                 say: Callable[[str, str], bool], stop_speech: Callable[[], None], speech_busy: Callable[[], bool],
                 on_event: Callable[[dict], None], on_task: Callable[[str, str], None] | None = None,
                 input_device: int | None = None, wake: bool = False,
                 quick_transcribe: Callable[[np.ndarray], str] | None = None, follow_up_s: float = 12.0,
                 local_command: Callable[[str], str | None] | None = None, noise: str = "off"):
        self.agent = agent
        self._make, self._transcribe = make_conversation, transcribe
        self._say, self._stop_speech, self._speech_busy = say, stop_speech, speech_busy
        self._emit, self._on_task = on_event, on_task
        self.input_device = input_device
        self.convs: dict[str, object] = {}
        self.vad = EnergyVAD()
        # noise filter + neural speech detector (fan, wind on the microphone…); "off" keeps the raw signal
        from ..voice.denoise import MicFrontEnd
        self.front = MicFrontEnd(noise) if noise != "off" else None
        self.noise_dropped = 0   # finished clips that held no speech (not transcribed)
        self.muted = False
        self.running = False
        self._utterances: "queue.Queue[np.ndarray | None]" = queue.Queue()
        self._cancel = threading.Event()
        self._responding = False
        self._stream = None
        self._mic_thread = None
        # wake mode: only react when called by name ("Kaguya…", "Miwa…"); after an answer, a short
        # follow-up window lets the user keep talking without repeating the name
        self.wake = wake
        self._quick = quick_transcribe
        self._local = local_command   # e.g. music commands: answered without any AI call
        self.follow_up_s = follow_up_s
        self._awake_until = 0.0

    # ----------------------------------------------------------------- control
    def start(self, with_microphone: bool = True):
        self.running = True
        threading.Thread(target=self._brain_loop, daemon=True, name="kaguya-live-brain").start()
        if with_microphone:
            self._open_microphone()
        if not self.wake:
            self._emit({"type": "agent", "agent": self.agent})
            self.warm(self.agent)
        else:  # processes only; no message is sent until the user calls a name
            self.warm("codex")
            self.warm("claude")
        self._state("listening")

    def warm(self, agent: str):
        def run():
            try:
                conv = self._conversation(agent)
                if hasattr(conv, "warm"):
                    conv.warm()
            except Exception as exc:
                self._emit({"type": "error", "message": f"Não foi possível iniciar a conversa: {exc}"})
        threading.Thread(target=run, daemon=True).start()

    def stop(self):
        self.running = False
        self._cancel.set()
        self._stop_speech()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self._utterances.put(None)
        for c in self.convs.values():
            try:
                c.close()
            except Exception:
                pass
        self.convs.clear()
        self._emit({"type": "end"})

    def set_agent(self, agent: str):
        if agent != self.agent:
            self.agent = agent
            self._emit({"type": "agent", "agent": agent})
            self.warm(agent)

    def set_muted(self, muted: bool):
        self.muted = muted
        self.vad.reset()
        if self.front is not None:
            self.front.reset()
        self._state("muted" if muted else "listening")

    def barge_in(self):
        """User started talking over the assistant."""
        if self._speech_busy() or self._responding:
            self._stop_speech()
            self._cancel.set()
            self._emit({"type": "barge_in"})

    # -------------------------------------------------------------- microphone
    def _open_microphone(self):
        import sounddevice as sd
        from ..voice.devices import resample
        try:
            info = sd.query_devices(self.input_device, "input")
            rate = int(info.get("default_samplerate") or RATE)
        except Exception:
            rate = RATE
        block = int(rate * self.vad.cfg.frame_ms / 1000)
        frames: "queue.Queue[np.ndarray]" = queue.Queue()

        def cb(data, n, t, status):
            frames.put(data[:, 0].copy())
        self._stream = sd.InputStream(samplerate=rate, channels=1, dtype="float32", device=self.input_device,
                                      blocksize=block, callback=cb)
        self._stream.start()

        def pump():
            last_level = 0.0
            while self.running:
                try:
                    f = frames.get(timeout=0.2)
                except queue.Empty:
                    continue
                self.feed(resample(f, rate, RATE) if rate != RATE else f)
                if time.monotonic() - last_level > 0.08:
                    last_level = time.monotonic()
                    self._emit({"type": "level", "value": self.vad.level})
        self._mic_thread = threading.Thread(target=pump, daemon=True, name="kaguya-live-mic")
        self._mic_thread.start()

    def feed(self, frame16k: np.ndarray):
        """Push microphone audio (16 kHz mono). Public so tests can drive the session without hardware."""
        if self.muted:
            return
        self.vad.assistant_talking = self._speech_busy()
        prob = None
        if self.front is not None:
            frame16k, prob = self.front.process(frame16k)
        for kind, audio in self.vad.feed(frame16k, prob):
            if kind == "start":
                self.barge_in()
                self._state("hearing")
            elif kind == "end" and audio is not None and len(audio) >= RATE * 0.35:
                if self.front is not None and self.front.neural:
                    from ..voice.denoise import has_speech
                    if has_speech(audio) is False:     # only noise: never transcribed, never sent anywhere
                        self.noise_dropped += 1
                        self._emit({"type": "noise"})
                        self._state("listening")
                        continue
                self._utterances.put(audio)

    # ------------------------------------------------------------------ brain
    def _brain_loop(self):
        while self.running:
            audio = self._utterances.get()
            if audio is None or not self.running:
                return
            if self.wake and time.monotonic() > self._awake_until:
                self._wake_check(audio)
                continue
            self._state("transcribing")
            try:
                text = (self._transcribe(audio) or "").strip()
            except Exception as exc:
                self._emit({"type": "error", "message": f"Transcrição falhou: {exc}"})
                self._state("listening")
                continue
            if len(text) < 2:
                self._state("listening")
                continue
            if self.wake:
                from .wake import detect_name
                if detect_name(text)[0]:
                    self.called(detect_name(text)[0], text)
                    continue
            self.handle_text(text)

    def _wake_check(self, audio):
        """Cheap first pass (small model) only to find the name; nothing leaves the PC before that."""
        from .wake import detect_name
        try:
            quick = ((self._quick or self._transcribe)(audio) or "").strip()
        except Exception as exc:
            self._emit({"type": "error", "message": f"Transcrição falhou: {exc}"})
            return
        agent, _ = detect_name(quick)
        if agent is None:
            self._emit({"type": "ignored", "text": quick})
            return
        text = quick
        if self._quick is not None:  # accurate pass on the same audio for the actual request
            self._state("transcribing")
            try:
                full = (self._transcribe(audio) or "").strip()
                if full:
                    a2, _ = detect_name(full)
                    text, agent = full, a2 or agent
            except Exception:
                pass
        self.called(agent, text)

    def called(self, agent: str, text: str):
        """The user said the assistant's name (voice) — wake up, show the mascot and answer."""
        from .wake import detect_name
        _a, rest = detect_name(text)
        self.agent = agent
        self._emit({"type": "called", "agent": agent, "text": text})
        self._awake_until = time.monotonic() + self.follow_up_s + 60  # extended while answering
        if len(rest) < 3:
            self._emit({"type": "caption", "role": "user", "text": text, "final": True})
            self._say("Oi! Pode falar." if agent == "codex" else "Oi, estou ouvindo.", agent)
            self._awake_until = time.monotonic() + self.follow_up_s
            self._state("listening")
            return
        self.handle_text(text)
        self._awake_until = time.monotonic() + self.follow_up_s

    def handle_text(self, text: str):
        self._emit({"type": "caption", "role": "user", "text": text, "final": True})
        cmd, arg = command_of(text)
        if cmd == "end":
            self._say("Até mais!", self.agent)
            if self.wake:
                self._awake_until = 0.0
                self._emit({"type": "sleep"})
                self._state("listening")
                return
            self.running = False
            self._emit({"type": "request_end"})
            return
        if cmd == "switch":
            self.set_agent(arg)
            self._say("Oi, é a Miwa." if arg == "claude" else "Oi, é a Kaguya.", arg)
            self._state("listening")
            return
        if cmd == "silence":
            self._stop_speech()
            self._state("listening")
            return
        if self._local is not None:
            from .wake import detect_name
            reply = self._local(detect_name(text)[1] or text)
            if reply:
                self._emit({"type": "caption", "role": "assistant", "agent": self.agent, "text": reply, "final": True})
                self._say(reply, self.agent)
                self._state("listening")
                return
        self._respond(text)

    def _conversation(self, agent: str):
        if not self.running:                       # stop() already closed everything: never open a new CLI
            raise RuntimeError("O Live foi encerrado.")
        if agent not in self.convs:
            self.convs[agent] = self._make(agent)
        return self.convs[agent]

    def _respond(self, text: str):
        agent = self.agent
        self._cancel = threading.Event()
        cancel = self._cancel
        self._responding = True
        self._state("thinking")
        buf = {"text": "", "spoken": "", "full": "", "first": True}

        def on_delta(delta: str):
            buf["full"] += delta
            buf["text"] += delta
            self._emit({"type": "caption", "role": "assistant", "agent": agent, "text": buf["full"], "final": False})
            self._speak_ready(buf, agent, final=False)

        try:
            full = self._conversation(agent).ask(text, on_delta, cancel)
        except Exception as exc:
            self._responding = False
            self._emit({"type": "error", "message": str(exc)})
            self._state("listening")
            return
        self._responding = False
        if cancel.is_set():
            self._state("listening")
            return
        if full and not buf["full"]:
            buf["full"] = buf["text"] = full
        self._speak_ready(buf, agent, final=True)
        clean = MARKERS.sub("", buf["full"]).strip()
        self._emit({"type": "caption", "role": "assistant", "agent": agent, "text": clean, "final": True})
        for task in TASK.findall(buf["full"]):
            if self._on_task:
                self._on_task(task.strip(), agent)
        for task in PC_TASK.findall(buf["full"]):
            if self._on_task:
                self._on_task(task.strip(), agent, "pc")
        self._state("speaking" if self._speech_busy() else "listening")
        if self.wake:
            self._awake_until = time.monotonic() + self.follow_up_s

    def _speak_ready(self, buf: dict, agent: str, final: bool):
        text = buf["text"]
        # Never speak task markers; hold the buffer while a marker is still open.
        if "[[" in text and "]]" not in text[text.rfind("[["):]:
            if not final:
                return
        text = MARKERS.sub("", text)
        sentences, rest = split_sentences(text, final=final, first_max=55 if buf.get("first") else None)
        buf["text"] = rest
        if sentences:
            buf["first"] = False
        for s in sentences:
            if s.strip() and not self._cancel.is_set():
                if self._say(s, agent):
                    self._state("speaking")

    def _state(self, state: str):
        self._emit({"type": "state", "state": state, "agent": self.agent})
