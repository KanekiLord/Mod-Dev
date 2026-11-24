"""Local text-to-speech, interruptible. Windows: System.Speech (SAPI) through PowerShell —
no extra install, no paid API. Other systems: espeak-ng / spd-say / say when present."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading

_PS_SPEAK = (
    "[Console]::InputEncoding=[Text.Encoding]::UTF8;"
    "Add-Type -AssemblyName System.Speech;"
    "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
    "$v=$env:KAGUYA_TTS_VOICE; if($v){try{$s.SelectVoice($v)}catch{}}"
    "else{$pt=$s.GetInstalledVoices()|?{$_.VoiceInfo.Culture.Name -like 'pt*'}|select -First 1;"
    "if($pt){$s.SelectVoice($pt.VoiceInfo.Name)}};"
    "$s.Rate=[int]$env:KAGUYA_TTS_RATE; $s.Volume=[int]$env:KAGUYA_TTS_VOLUME;"
    "$s.Speak([Console]::In.ReadToEnd())"
)
_PS_VOICES = ("Add-Type -AssemblyName System.Speech;"
              "(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices()|"
              "%{$_.VoiceInfo.Name+'|'+$_.VoiceInfo.Culture.Name}")


def clean_for_speech(text: str, limit: int = 1800) -> str:
    t = re.sub(r"```.*?```", " (trecho de código omitido) ", text or "", flags=re.S)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"https?://\S+", " link ", t)
    t = re.sub(r"[#*_>|~]+", " ", t)
    t = re.sub(r"^\s*[-•]\s*", "", t, flags=re.M)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:limit]


def _flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


class Speaker:
    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self.voice = ""
        self.rate = 1
        self.volume = 100

    @staticmethod
    def backend() -> str | None:
        if os.name == "nt":
            return "Windows SAPI (System.Speech)"
        for exe in ("espeak-ng", "espeak", "spd-say", "say"):
            if shutil.which(exe):
                return exe
        return None

    def voices(self) -> list[tuple[str, str]]:
        if os.name != "nt":
            return []
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_VOICES],
                                 capture_output=True, text=True, timeout=20, creationflags=_flags()).stdout
        except (OSError, subprocess.TimeoutExpired):
            return []
        return [tuple(l.strip().split("|", 1)) for l in out.splitlines() if "|" in l]

    @property
    def speaking(self) -> bool:
        return bool(self.proc and self.proc.poll() is None)

    def stop(self) -> None:
        with self._lock:
            if self.proc and self.proc.poll() is None:
                try:
                    self.proc.terminate()
                except OSError:
                    pass
            self.proc = None

    def speak(self, text: str, on_done=None) -> bool:
        text = clean_for_speech(text)
        if not text:
            return False
        self.stop()
        backend = self.backend()
        if backend is None:
            return False
        env = dict(os.environ)
        if os.name == "nt":
            env.update(KAGUYA_TTS_VOICE=self.voice or "", KAGUYA_TTS_RATE=str(self.rate), KAGUYA_TTS_VOLUME=str(self.volume))
            cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_SPEAK]
            stdin = text
        elif backend in ("espeak-ng", "espeak"):
            cmd, stdin = [backend, "-v", "pt-br", "--stdin"], text
        elif backend == "spd-say":
            cmd, stdin = [backend, "-l", "pt", "-w", text], None
        else:
            cmd, stdin = ["say", text], None
        try:
            with self._lock:
                self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE if stdin else subprocess.DEVNULL,
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
                                             text=True, encoding="utf-8", creationflags=_flags())
                proc = self.proc
            if stdin:
                proc.stdin.write(stdin)
                proc.stdin.close()
        except OSError:
            return False

        def wait():
            proc.wait()
            if on_done:
                on_done()
        threading.Thread(target=wait, daemon=True).start()
        return True
