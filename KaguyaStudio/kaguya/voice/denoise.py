"""Microphone noise handling for fans, wind on the capsule, AC hum and room hiss — local, no downloads.

Three layers, used by the Live mode, the "call by name" listener and push-to-talk:

1. ``SpectralDenoiser`` — streaming STFT noise suppression (Wiener gain with decision-directed SNR) whose noise
   profile is learned continuously from the quiet moments, plus a low cut (fan rumble/hum lives below ~150 Hz) and a
   wind detector: a gust is a burst of energy concentrated in the low frequencies, and while it lasts the lows are
   attenuated hard. Latency ≈ 32 ms.
2. ``SpeechDetector`` — the Silero VAD neural model that ships inside faster-whisper (already installed for local
   transcription), run continuously. It tells speech from noise, so a fan or a gust no longer "starts" an utterance
   or interrupts the assistant.
3. ``has_speech`` — final check on a finished utterance before it is transcribed (noise-only clips are dropped,
   which also removes Whisper's famous hallucinations on noise).

Pure numpy; Silero needs onnxruntime (installed with faster-whisper). Without it, layers 1 and the energy/wind
heuristics still work.
"""
from __future__ import annotations

import os

import numpy as np

RATE = 16000
N_FFT = 512
HOP = 256

# per strength: low cut (Hz), gain floor (how much noise is left: lower = stronger), over-subtraction
STRENGTHS = {
    "normal": {"cut": 110.0, "floor": 0.14, "over": 1.4, "wind_floor": 0.10},
    "forte": {"cut": 160.0, "floor": 0.07, "over": 2.0, "wind_floor": 0.04},
}
LABELS = {"off": "Desligado", "normal": "Normal (recomendado)", "forte": "Forte (ventilador perto, vento no microfone)"}


def _window() -> np.ndarray:
    return np.sqrt(np.hanning(N_FFT + 1)[:-1]).astype("float32")   # sqrt-Hann, 50% overlap → perfect rebuild


class SpectralDenoiser:
    """Streaming: ``process(chunk)`` returns exactly ``len(chunk)`` samples (delayed by ≈ 32 ms)."""

    def __init__(self, strength: str = "normal", rate: int = RATE):
        self.p = STRENGTHS.get(strength, STRENGTHS["normal"])
        self.strength = strength
        self.win = _window()
        freqs = np.fft.rfftfreq(N_FFT, 1.0 / rate)
        self._cut = freqs < self.p["cut"]
        self._low = (freqs >= 20) & (freqs < 400)          # wind detection band (most gust energy is < 150 Hz)
        self._wind_bins = freqs < 600
        self._speech = (freqs >= 400) & (freqs < 4000)
        self.reset()

    def reset(self):
        bins = N_FFT // 2 + 1
        self._in = np.zeros(N_FFT - HOP, dtype="float32")
        self._ola = np.zeros(N_FFT, dtype="float32")
        self._out = np.zeros(HOP, dtype="float32")     # prefill: output is always available
        self.noise = np.full(bins, 1e-7)
        self._smooth = np.full(bins, 1e-7)
        self._prev_gain = np.ones(bins)
        self._prev_gamma = np.ones(bins)
        self._frames = 0
        self._wind_hold = 0
        self.wind = False                 # a gust is happening now
        self.speech_hint = False          # set by the caller (Silero) to freeze the noise profile

    # ------------------------------------------------------------------ core
    def _frame(self, X: np.ndarray) -> np.ndarray:
        P = (X.real ** 2 + X.imag ** 2).astype("float64")
        self._frames += 1
        self._smooth = 0.75 * self._smooth + 0.25 * P
        if self._frames <= 8:                                   # first ≈ 130 ms: bootstrap the profile
            self.noise = P.copy() if self._frames == 1 else 0.7 * self.noise + 0.3 * P
        else:
            down = self._smooth < self.noise
            self.noise[down] = 0.85 * self.noise[down] + 0.15 * self._smooth[down]
            if not self.speech_hint:                            # slow rise: follows a fan speeding up, not speech
                self.noise[~down] *= 1.012
        # wind: the lows jump far above their own background while the voice band barely moves
        low_r = P[self._low].sum() / (self.noise[self._low].sum() + 1e-12)
        sp_r = P[self._speech].sum() / (self.noise[self._speech].sum() + 1e-12)
        if low_r > 4.0 and low_r > 3.0 * sp_r:
            self._wind_hold = 6                                 # ≈ 100 ms after the gust
        else:
            self._wind_hold = max(0, self._wind_hold - 1)
        self.wind = self._wind_hold > 0
        # Wiener gain, decision-directed a-priori SNR (reduces "musical noise")
        gamma = P / (self.p["over"] * self.noise + 1e-12)
        xi = 0.96 * (self._prev_gain ** 2) * self._prev_gamma + 0.04 * np.maximum(gamma - 1.0, 0.0)
        gain = xi / (1.0 + xi)
        gain = np.convolve(gain, np.array([0.25, 0.5, 0.25]), mode="same")   # smooth across frequency
        gain = np.maximum(gain, self.p["floor"])
        if self.wind:
            gain[self._wind_bins] = np.minimum(gain[self._wind_bins], self.p["wind_floor"])
        gain[self._cut] = 0.0
        self._prev_gain, self._prev_gamma = gain, np.minimum(gamma, 1e3)
        return X * gain

    def process(self, chunk) -> np.ndarray:
        x = np.asarray(chunk, dtype="float32").reshape(-1)
        buf = np.concatenate([self._in, x])
        outs = [self._out]
        pos = 0
        while pos + N_FFT <= len(buf):
            frame = buf[pos:pos + N_FFT] * self.win
            y = np.fft.irfft(self._frame(np.fft.rfft(frame)), N_FFT).astype("float32") * self.win
            self._ola += y
            outs.append(self._ola[:HOP].copy())
            self._ola = np.concatenate([self._ola[HOP:], np.zeros(HOP, dtype="float32")])
            pos += HOP
        self._in = buf[pos:]
        out = np.concatenate(outs)
        self._out = out[len(x):]
        return out[:len(x)]


def denoise(audio, strength: str = "normal") -> np.ndarray:
    """Whole recording (push-to-talk). The noise profile starts from the quietest moments of the clip itself."""
    a = np.asarray(audio, dtype="float32").reshape(-1)
    if strength == "off" or len(a) < N_FFT * 2:
        return a
    d = SpectralDenoiser(strength)
    win = d.win
    frames = [np.fft.rfft(a[i:i + N_FFT] * win) for i in range(0, len(a) - N_FFT, HOP)]
    if frames:
        power = np.array([(f.real ** 2 + f.imag ** 2) for f in frames])
        prof = np.percentile(power, 20, axis=0)
        d.noise, d._smooth, d._frames = prof.copy(), prof.copy(), 99
    pad = np.concatenate([a, np.zeros(N_FFT, dtype="float32")])
    out = d.process(pad)
    delay = HOP + (N_FFT - HOP)
    return out[delay:delay + len(a)]


def rms_db(audio) -> float:
    a = np.asarray(audio, dtype="float64").reshape(-1)
    return float(20 * np.log10(np.sqrt(np.mean(a * a)) + 1e-9)) if len(a) else -180.0


# --------------------------------------------------------------------------- Silero VAD (bundled in faster-whisper)
def _silero_path() -> str | None:
    try:
        from faster_whisper.utils import get_assets_path
        path = os.path.join(get_assets_path(), "silero_vad_v6.onnx")
        return path if os.path.exists(path) else None
    except Exception:
        return None


class SpeechDetector:
    """Continuous speech probability (0..1) for 16 kHz audio, keeping the model state between chunks."""
    WIN, CTX = 512, 64

    def __init__(self, path: str | None = None):
        import onnxruntime
        path = path or _silero_path()
        if not path:
            raise RuntimeError("modelo Silero VAD não encontrado (faster-whisper ausente)")
        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = opts.intra_op_num_threads = 1
        opts.log_severity_level = 4
        self.session = onnxruntime.InferenceSession(path, providers=["CPUExecutionProvider"], sess_options=opts)
        self.reset()

    @staticmethod
    def available() -> bool:
        try:
            import onnxruntime  # noqa: F401
        except Exception:
            return False
        return _silero_path() is not None

    def reset(self):
        self._h = np.zeros((1, 1, 128), dtype="float32")
        self._c = np.zeros((1, 1, 128), dtype="float32")
        self._ctx = np.zeros(self.CTX, dtype="float32")
        self._buf = np.zeros(0, dtype="float32")
        self.prob = 0.0

    def feed(self, chunk) -> float:
        """Returns the highest probability among the windows completed by this chunk (or the last one)."""
        self._buf = np.concatenate([self._buf, np.asarray(chunk, dtype="float32").reshape(-1)])
        best = None
        while len(self._buf) >= self.WIN:
            w, self._buf = self._buf[:self.WIN], self._buf[self.WIN:]
            inp = np.concatenate([self._ctx, w])[None, :]
            out, self._h, self._c = self.session.run(None, {"input": inp, "h": self._h, "c": self._c})
            self._ctx = w[-self.CTX:]
            p = float(np.ravel(out)[0])
            best = p if best is None else max(best, p)
        if best is not None:
            self.prob = best
        return self.prob


def has_speech(audio, min_ms: int = 250, threshold: float = 0.5) -> bool | None:
    """True/False for a finished clip; None when the detector is not available (then the caller decides)."""
    if not SpeechDetector.available():
        return None
    try:
        from faster_whisper.vad import VadOptions, get_speech_timestamps
        a = np.asarray(audio, dtype="float32").reshape(-1)
        spans = get_speech_timestamps(a, VadOptions(threshold=threshold, min_speech_duration_ms=min_ms))
        return sum(s["end"] - s["start"] for s in spans) >= RATE * min_ms / 1000
    except Exception:
        return None


class MicFrontEnd:
    """What the Live mode and the name listener put between the microphone and the VAD."""

    def __init__(self, strength: str = "normal", neural: bool = True):
        self.strength = strength if strength in STRENGTHS or strength == "off" else "normal"
        self.denoiser = SpectralDenoiser(self.strength) if self.strength != "off" else None
        self.detector = None
        if neural and self.strength != "off" and SpeechDetector.available():
            try:
                self.detector = SpeechDetector()
            except Exception:
                self.detector = None

    @property
    def neural(self) -> bool:
        return self.detector is not None

    def process(self, frame) -> tuple[np.ndarray, float | None]:
        clean = self.denoiser.process(frame) if self.denoiser else np.asarray(frame, dtype="float32")
        prob = None
        if self.detector is not None:
            prob = self.detector.feed(clean)
            if self.denoiser is not None:
                self.denoiser.speech_hint = prob > 0.5
        elif self.denoiser is not None and self.denoiser.wind:
            prob = 0.0                       # no neural detector: a gust is never speech
        return clean, prob

    def reset(self):
        if self.denoiser is not None:
            self.denoiser.reset()
        if self.detector is not None:
            self.detector.reset()


def analyze(audio, strength: str = "normal") -> dict:
    """Measure a few seconds of the room (ideally without talking) before and after the filter, the way the Live
    mode would treat it. Used by 'Medir ruído do ambiente' in Settings."""
    from ..live.vad import EnergyVAD
    a = np.asarray(audio, dtype="float32").reshape(-1)
    res = {"strength": strength, "seconds": round(len(a) / RATE, 1), "before_db": round(rms_db(a), 1)}
    fe = MicFrontEnd(strength if strength != "off" else "normal")
    old, new = EnergyVAD(), EnergyVAD()
    clean_parts, wind_frames, frames, false_old, false_new = [], 0, 0, 0, 0
    for i in range(0, len(a) - 480 + 1, 480):
        f = a[i:i + 480]
        c, prob = fe.process(f)
        clean_parts.append(c)
        frames += 1
        wind_frames += bool(fe.denoiser and fe.denoiser.wind)
        false_old += sum(1 for k, _ in old.feed(f) if k == "start")
        false_new += sum(1 for k, _ in new.feed(c, prob) if k == "start")
    clean = np.concatenate(clean_parts) if clean_parts else a
    res.update(after_db=round(rms_db(clean[HOP * 2:]), 1), wind_pct=round(100 * wind_frames / max(1, frames)),
               starts_without_filter=false_old, starts_with_filter=false_new, neural=fe.neural)
    res["reduction_db"] = round(res["before_db"] - res["after_db"], 1)
    level = res["before_db"]
    room = ("silencioso" if level < -55 else "com pouco ruído" if level < -45 else "barulhento" if level < -32
            else "muito barulhento")
    tips = []
    if res["wind_pct"] >= 10:
        tips.append("há vento/sopro batendo no microfone: afaste o ventilador dele ou vire o microfone; "
                    "uma espuma (windscreen) ajuda muito")
    if level >= -32 and strength != "forte":
        tips.append("use o filtro Forte")
    if not res["neural"]:
        tips.append("o detector de fala neural não está disponível nesta cópia (só o filtro está ativo)")
    res["text"] = (f"Ambiente {room}: ruído {res['before_db']} dB → {res['after_db']} dB com o filtro "
                   f"({res['reduction_db']} dB a menos). Falsos inícios de fala em {res['seconds']} s: "
                   f"{false_old} sem filtro, {false_new} com filtro."
                   + (" Dicas: " + "; ".join(tips) + "." if tips else ""))
    res["clean"] = clean
    return res
