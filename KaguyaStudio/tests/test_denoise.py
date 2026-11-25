"""Noise filter: fan + wind on the microphone must not count as speech; real speech must still get through."""
from pathlib import Path
import sys
import unittest
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from kaguya.voice.denoise import (HOP, MicFrontEnd, SpeechDetector, SpectralDenoiser, analyze, denoise,  # noqa: E402
                                  has_speech, rms_db)

R = 16000
ROOT = Path(__file__).resolve().parents[1]
NEURAL = SpeechDetector.available()


def _rng():
    return np.random.default_rng(11)


def _colored(n, alpha, rng):
    X = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / R)
    f[0] = 1
    y = np.fft.irfft(X / f ** (alpha / 2), n)
    return (y / np.std(y)).astype("float32")


def fan(sec, db=-27, rng=None):
    rng = rng or _rng()
    n = int(sec * R)
    t = np.arange(n) / R
    blade = sum(np.sin(2 * np.pi * h * 58 * t + h) / h for h in (1, 2, 3, 4))
    x = 0.6 * _colored(n, 1.0, rng) * (1 + 0.15 * np.sin(2 * np.pi * 0.7 * t)) + 0.5 * blade + 0.3 * rng.standard_normal(n)
    return (x / np.sqrt(np.mean(x ** 2)) * 10 ** (db / 20)).astype("float32")


def wind(sec, peak_db=-8, gusts=20, rng=None):
    rng = rng or _rng()
    n = int(sec * R)
    X = np.fft.rfft(_colored(n, 2.0, rng))
    f = np.fft.rfftfreq(n, 1 / R)
    X[f > 250] *= np.exp(-((f[f > 250] - 250) / 60) ** 2)
    x = np.fft.irfft(X, n)
    env = np.zeros(n)
    for _ in range(gusts):
        c, w = rng.uniform(0, n), rng.uniform(0.25, 1.2) * R
        env += np.exp(-0.5 * ((np.arange(n) - c) / (w / 2.5)) ** 2) * rng.uniform(0.5, 1)
    y = x * env
    y = y / (np.max(np.abs(y)) + 1e-9) * 10 ** (peak_db / 20)
    return np.clip(y * 1.3, -0.4, 0.4).astype("float32")


def speech_sample():
    from kaguya.voice.devices import resample
    with wave.open(str(ROOT / "docs" / "amostras_voz" / "kaguya_natural.wav")) as w:
        sr = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype("float32") / 32768
    a = resample(a, sr, R)
    return (a / np.sqrt(np.mean(a ** 2)) * 0.1).astype("float32")   # ≈ -20 dBFS


class Filter(unittest.TestCase):
    def test_streaming_keeps_length_and_matches_one_shot(self):
        x = fan(3)
        d1, d2 = SpectralDenoiser(), SpectralDenoiser()
        whole = d1.process(x)
        parts, i = [], 0
        for size in (480, 100, 1, 777, 2048) * 40:
            if i >= len(x):
                break
            parts.append(d2.process(x[i:i + size]))
            i += size
        self.assertEqual(len(whole), len(x))
        self.assertEqual(sum(len(p) for p in parts), len(x))
        np.testing.assert_allclose(np.concatenate(parts), whole, atol=1e-5)   # chunking never changes the result

    def test_fan_noise_drops_a_lot_and_a_tone_survives(self):
        noise = fan(6)
        out = SpectralDenoiser("normal").process(noise)
        self.assertGreater(rms_db(noise[R:]) - rms_db(out[R:]), 12)           # ≥ 12 dB less fan
        # something that starts in the middle of the fan (like a voice) is kept; a tone present from the very first
        # instant would be learned as noise, exactly like a hum — that is the intended behaviour
        t = np.arange(R) / R
        tone = (0.1 * np.sin(2 * np.pi * 1000 * t)).astype("float32")
        x = fan(4)
        x[2 * R:3 * R] += tone
        kept = SpectralDenoiser("normal").process(x)
        self.assertGreater(rms_db(kept[2 * R + HOP * 2:3 * R]), rms_db(tone) - 3)

    def test_gusts_are_flagged_as_wind(self):
        d = SpectralDenoiser("forte")
        flags = []
        a = fan(1, -40)
        gust = wind(2, -6, gusts=3)
        for chunk in np.array_split(np.concatenate([a, gust + fan(2, -40)]), 200):
            d.process(chunk)
            flags.append(d.wind)
        self.assertFalse(any(flags[:60]))           # steady fan alone: no wind
        self.assertTrue(any(flags[100:]))           # gusts: wind detected

    def test_push_to_talk_offline_denoise(self):
        sp = speech_sample()
        noisy = np.concatenate([fan(1), sp + fan(len(sp) / R)[:len(sp)], fan(1)])
        out = denoise(noisy, "normal")
        self.assertEqual(len(out), len(noisy))
        self.assertLess(rms_db(out[:R // 2]), rms_db(noisy[:R // 2]) - 10)   # fan-only start much quieter
        np.testing.assert_array_equal(denoise(noisy, "off"), noisy)


@unittest.skipUnless(NEURAL, "Silero VAD (faster-whisper + onnxruntime) ausente")
class Neural(unittest.TestCase):
    def test_detector_tells_speech_from_fan_and_wind(self):
        sp = speech_sample()
        d = SpeechDetector()
        probs = [d.feed(sp[i:i + 480]) for i in range(0, len(sp) - 480, 480)]
        self.assertGreater(np.mean(np.array(probs) > 0.5), 0.4)
        d.reset()
        noise = fan(10) + wind(10)
        nprobs = [d.feed(noise[i:i + 480]) for i in range(0, len(noise) - 480, 480)]
        self.assertLess(np.mean(np.array(nprobs) > 0.5), 0.02)
        self.assertTrue(has_speech(sp))
        self.assertFalse(has_speech(noise))


class LiveWithNoise(unittest.TestCase):
    def session(self, noise="forte"):
        from kaguya.live.session import LiveSession
        self.events = []
        s = LiveSession(agent="codex", make_conversation=lambda a: None, transcribe=lambda a: "",
                        say=lambda t, a: True, stop_speech=lambda: None, speech_busy=lambda: False,
                        on_event=self.events.append, noise=noise)
        s.running = True
        return s

    def feed(self, s, audio):
        for i in range(0, len(audio) - 480 + 1, 480):
            s.feed(audio[i:i + 480])

    def queued(self, s):
        out = []
        while not s._utterances.empty():
            out.append(s._utterances.get_nowait())
        return out

    def test_old_behaviour_is_fooled_by_fan_and_wind(self):
        s = self.session("off")
        self.feed(s, fan(30) + wind(30, -6, 30))
        barged = sum(1 for e in self.events if e.get("type") == "state" and e.get("state") == "hearing")
        self.assertGreater(barged, 0)                # the problem the user reported

    def test_fan_and_wind_never_start_speech(self):
        s = self.session("forte")
        self.feed(s, fan(30) + wind(30, -6, 30))
        self.assertEqual(self.queued(s), [])
        if NEURAL:
            self.assertFalse(any(e.get("state") == "hearing" for e in self.events if e.get("type") == "state"))

    @unittest.skipUnless(NEURAL, "Silero VAD ausente")
    def test_speech_inside_fan_and_wind_still_gets_through_whole(self):
        s = self.session("forte")
        sp = speech_sample()
        noise = fan(len(sp) / R + 6) + wind(len(sp) / R + 6, -8, 25)
        audio = noise.copy()
        audio[2 * R:2 * R + len(sp)] += sp
        self.feed(s, audio)
        utts = self.queued(s)
        self.assertEqual(len(utts), 1)                                   # one sentence → one turn
        self.assertGreater(len(utts[0]) / R, len(sp) / R - 1.0)


class Hallucinations(unittest.TestCase):
    def test_noise_hallucinations_are_dropped(self):
        from types import SimpleNamespace as S
        from kaguya.voice.stt import clean_segments
        segs = [S(text=" Legendas pela comunidade Amara.org ", no_speech_prob=0.2, avg_logprob=-0.3),
                S(text=" Obrigado por assistir!", no_speech_prob=0.1, avg_logprob=-0.2),
                S(text=" Kaguya, abre o projeto.", no_speech_prob=0.05, avg_logprob=-0.2),
                S(text=" hmm", no_speech_prob=0.9, avg_logprob=-1.2)]
        self.assertEqual(clean_segments(segs), "Kaguya, abre o projeto.")


class Measure(unittest.TestCase):
    def test_room_measurement_reports_real_numbers_and_wind(self):
        res = analyze(fan(5) + wind(5, -6, 12), "normal")
        self.assertGreater(res["reduction_db"], 6)
        self.assertGreater(res["wind_pct"], 5)
        self.assertIn("vento", res["text"])
        self.assertIn(str(res["before_db"]), res["text"])
        self.assertEqual(len(res["clean"]), (5 * R // 480) * 480)
        self.assertLessEqual(res["starts_with_filter"], res["starts_without_filter"])
        self.assertGreater(HOP, 0)


if __name__ == "__main__":
    unittest.main()
