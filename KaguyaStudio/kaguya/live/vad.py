"""Voice activity detection by energy with an adaptive noise floor (no extra downloads).

Feed 16 kHz mono float32 frames; get ``start`` when speech begins and ``end`` (with the whole
utterance, including a short pre-roll) after a pause. While the assistant is speaking, a higher
threshold is used so its own voice leaking from speakers is less likely to trigger barge-in
(headphones are still recommended).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

RATE = 16000


@dataclass
class VADConfig:
    frame_ms: int = 30
    start_ms: int = 180          # speech must last this long to count
    end_silence_ms: int = 750    # pause that ends the utterance
    preroll_ms: int = 300
    max_utterance_s: float = 30.0
    min_level: float = 0.012     # absolute floor (RMS)
    ratio: float = 3.0           # speech = noise * ratio
    barge_ratio: float = 6.0     # stricter while the assistant talks


class EnergyVAD:
    def __init__(self, cfg: VADConfig | None = None):
        self.cfg = cfg or VADConfig()
        self.noise = 0.005
        self.speaking = False
        self._voiced = 0
        self._silent = 0
        self._frames: list[np.ndarray] = []
        fpp = max(1, self.cfg.preroll_ms // self.cfg.frame_ms)
        self._pre: deque[np.ndarray] = deque(maxlen=fpp)
        self.assistant_talking = False
        self.level = 0.0

    def _threshold(self) -> float:
        ratio = self.cfg.barge_ratio if self.assistant_talking else self.cfg.ratio
        return max(self.cfg.min_level, self.noise * ratio)

    def feed(self, frame: np.ndarray) -> list[tuple[str, np.ndarray | None]]:
        """Returns events: ('start', None) and/or ('end', utterance_audio)."""
        frame = np.asarray(frame, dtype="float32").reshape(-1)
        rms = float(np.sqrt(np.mean(frame * frame))) if len(frame) else 0.0
        self.level = min(1.0, rms * 8)
        events = []
        loud = rms > self._threshold()
        fms = self.cfg.frame_ms
        if not self.speaking:
            self._pre.append(frame)
            if loud:
                self._voiced += 1
                if self._voiced * fms >= self.cfg.start_ms:
                    self.speaking = True
                    self._silent = 0
                    self._frames = list(self._pre)
                    events.append(("start", None))
            else:
                self._voiced = 0
                # adapt the noise floor only during silence
                self.noise = 0.95 * self.noise + 0.05 * max(rms, 1e-4)
        else:
            self._frames.append(frame)
            self._silent = 0 if loud else self._silent + 1
            too_long = len(self._frames) * fms / 1000 >= self.cfg.max_utterance_s
            if self._silent * fms >= self.cfg.end_silence_ms or too_long:
                audio = np.concatenate(self._frames)
                self.speaking = False
                self._voiced = 0
                self._frames = []
                self._pre.clear()
                events.append(("end", audio))
        return events

    def reset(self):
        self.speaking = False
        self._voiced = self._silent = 0
        self._frames = []
        self._pre.clear()
