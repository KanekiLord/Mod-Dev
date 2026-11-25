"""Voice layer: pt-BR text preparation, engine registry (no fake capabilities), profiles, queue behaviour."""
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from kaguya.store import Store  # noqa: E402
from kaguya.voice.engines import HEAVY, VoiceEngines, VoiceProfile, benchmark, load_profile, save_profile  # noqa: E402
from kaguya.voice.normalize import normalize, number  # noqa: E402
from kaguya.voice.speech import SpeechQueue, envelope  # noqa: E402


class Normalize(unittest.TestCase):
    def test_numbers(self):
        for n, words in ((1, "um"), (21, "vinte e um"), (100, "cem"), (101, "cento e um"), (1001, "mil e um"),
                         (1100, "mil e cem"), (2005, "dois mil e cinco"), (2026, "dois mil e vinte e seis"),
                         (2500000, "dois milhões e quinhentos mil"),
                         (1234567, "um milhão duzentos e trinta e quatro mil quinhentos e sessenta e sete")):
            self.assertEqual(number(n), words)

    def test_benchmark_phrases_are_speakable(self):
        cases = {
            "O relatório foi gerado em 25/11/2026, às 14:35.":
                "vinte e cinco de novembro de dois mil e vinte e seis, às quatorze horas e trinta e cinco minutos",
            "A GPU tem 8 GB de VRAM": "gê pê u tem oito gigabytes de vê ram",
            "uso de 2,5%": "dois vírgula cinco por cento",
            "O arquivo main.py chama voice_synthesize": "main ponto pai chama voice synthesize",
            "Forge 1.7.10": "fórdj um ponto sete ponto dez",
            "R$ 1.234,50": "mil duzentos e trinta e quatro reais e cinquenta centavos",
            "o 1º lugar": "o primeiro lugar",
            "Veja https://exemplo.com/docs": "Veja link",
            "Windows 11": "uíndous onze",
            "500 ms": "quinhentos milissegundos",
        }
        for text, spoken in cases.items():
            self.assertIn(spoken, normalize(text), text)
        self.assertIn("trecho de código omitido", normalize("```py\nprint(1)\n```"))
        self.assertEqual(normalize("Paralelepípedo, extraordinariamente."), "Paralelepípedo, extraordinariamente.")


class FakeEngine:
    id = "kokoro"

    def __init__(self, fail=False):
        self.fail = fail

    def probe(self):
        from kaguya.voice.engines import Capabilities
        return Capabilities(id="kokoro", name="Fake", installed=True, voices=[("x", "X")])

    def synth(self, text, profile, agent):
        if self.fail:
            raise RuntimeError("modelo corrompido")
        return np.sin(np.linspace(0, 200, 8000 + 40 * len(text))).astype("float32"), 16000


class EnginesAndProfiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "s.db")

    def test_heavy_engines_never_claim_to_be_installed(self):
        for cap in HEAVY.values():
            self.assertFalse(cap.installed)
            self.assertIn("autorização", cap.status)
        self.assertIn("arquivado", HEAVY["chatterbox"].status)

    def test_profiles_are_independent_and_migrate(self):
        self.store.set_setting("voice.neural_claude", "suave")        # chosen in 4.x
        self.assertEqual(load_profile(self.store, "claude").voice, "suave")
        save_profile(self.store, "codex", VoiceProfile(engine="kokoro", voice="dora", style="formal", speed=1.1, volume=60))
        k, m = load_profile(self.store, "codex"), load_profile(self.store, "claude")
        self.assertEqual((k.style, k.speed, k.volume), ("formal", 1.1, 60))
        self.assertEqual((m.style, m.volume), ("natural", 90))      # Miwa untouched
        save_profile(self.store, "claude", VoiceProfile(speed=9, volume=500, style="???"))
        m = load_profile(self.store, "claude")
        self.assertEqual((m.speed, m.volume, m.style), (1.4, 100, "natural"))   # clamped, safe

    def test_volume_applied_and_fallback_and_benchmark(self):
        eng = VoiceEngines.__new__(VoiceEngines)
        eng.engines = {"kokoro": FakeEngine()}
        a_full, _sr, eid = eng.synth("oi", VoiceProfile(volume=100), "codex")
        a_half, _sr, _ = eng.synth("oi", VoiceProfile(volume=50), "codex")
        self.assertEqual(eid, "kokoro")
        self.assertAlmostEqual(float(np.abs(a_half).max()), float(np.abs(a_full).max()) / 2, places=3)
        res = benchmark(eng, VoiceProfile(), "codex", [{"id": "a", "text": "Olá. Tudo bem?"},
                                                         {"id": "b", "text": "Teste 25/11/2026."}])
        self.assertEqual((res["engine"], len(res["rows"]), res["errors"]), ("kokoro", 2, []))
        self.assertTrue(all(r["rtf"] is not None and r["audio_s"] > 0 for r in res["rows"]))
        eng.engines = {"kokoro": FakeEngine(fail=True)}
        res = benchmark(eng, VoiceProfile(), "codex", [{"id": "a", "text": "Olá."}])
        self.assertEqual(res["rows"], [])
        self.assertIn("modelo corrompido", res["errors"][0])       # errors reported, not hidden
        eng.engines = {}
        with self.assertRaises(RuntimeError):
            eng.synth("oi", VoiceProfile(), "codex")


class QueueBehaviour(unittest.TestCase):
    def test_cancel_drops_late_audio_errors_are_reported_and_level_follows_audio(self):
        played, errors, states = [], [], []
        gate = threading.Event()

        def synth(text, agent):
            if text.startswith("ERRO"):
                raise RuntimeError("falhou")
            if text.startswith("Lenta"):
                gate.wait(2)                       # still synthesising when the user interrupts
            audio = np.concatenate([np.zeros(1600), np.ones(3200) * 0.5]).astype("float32")
            return audio, 16000

        def play(audio, sr, stop):
            played.append(len(audio))
            end = time.monotonic() + len(audio) / sr
            while time.monotonic() < end and not stop.is_set():
                time.sleep(0.005)

        q = SpeechQueue(synth, play, lambda s, a: states.append(s), errors.append)
        q.say("Primeira frase completa.", "codex")
        deadline = time.monotonic() + 3
        while not q.active and time.monotonic() < deadline:
            time.sleep(0.01)
        time.sleep(0.03)
        self.assertLess(q.level(), 0.1)                             # leading silence → mouth closed
        time.sleep(0.12)
        self.assertGreater(q.level(), 0.9)                          # loud part → mouth moving
        q.say("Lenta frase que chega tarde.", "codex")
        q.stop()                                                    # barge-in while it is still being made
        gate.set()
        time.sleep(0.5)
        self.assertEqual(len(played), 1)                            # the late sentence never plays
        self.assertEqual(states[-1], "idle")
        q.say("ERRO aqui.", "codex")
        time.sleep(0.3)
        self.assertTrue(errors and "falhou" in errors[0])

    def test_envelope(self):
        env = envelope(np.concatenate([np.zeros(320), np.ones(320)]).astype("float32"), 16000)
        self.assertEqual(env, [0.0, 1.0])


if __name__ == "__main__":
    unittest.main()
