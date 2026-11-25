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
        self.assertIn("arquivado", HEAVY["chatterbox"].status)
        from kaguya.voice.engines import QwenEngine
        qwen = QwenEngine(Path(self.tmp.name)).probe()
        self.assertFalse(qwen.installed)                      # nothing installed until the user confirms
        self.assertIn("confirmação", qwen.status)
        with self.assertRaises(RuntimeError):
            QwenEngine(Path(self.tmp.name)).synth("oi", VoiceProfile(engine="qwen3"), "codex")

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


class HeavyInstall(unittest.TestCase):
    """Installer + worker client, end to end with a fake uv and the worker's test double (no download)."""

    def setUp(self):
        import os
        from unittest import mock
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "dados"
        self.calls = Path(self.tmp.name) / "uv_calls.txt"
        fake = Path(self.tmp.name) / "fake_uv.py"
        fake.write_text(f"""import os, sys
from pathlib import Path
open({str(self.calls)!r}, "a").write(" ".join(sys.argv[1:]) + "\\n")
if sys.argv[1] == "venv":
    (Path(sys.argv[2]) / "lib").mkdir(parents=True, exist_ok=True)
    print("criado")
elif sys.argv[1] == "pip":
    print("instalando " + sys.argv[-1])
    if os.environ.get("FAKE_UV_FAIL"): sys.exit(3)
    if os.environ.get("FAKE_UV_SLEEP"):
        import time; time.sleep(float(os.environ["FAKE_UV_SLEEP"]))
""", encoding="utf-8")
        from kaguya.voice import heavy
        # the stand-in runs through this Python on every system (Windows cannot run a script named "uv"),
        # and the environment's interpreter is this Python too (the worker's test double needs only numpy)
        for p in (mock.patch.dict(os.environ, {"KAGUYA_TTS_WORKER_FAKE": "1"}),
                  mock.patch.object(heavy.Installer, "uv_command", lambda _self: [sys.executable, str(fake)]),
                  mock.patch.object(heavy, "venv_python", lambda _home, _eid: Path(sys.executable))):
            p.start()
            self.addCleanup(p.stop)

    def test_install_writes_marker_only_after_real_load_and_engine_speaks(self):
        from kaguya.voice import heavy
        from kaguya.voice.engines import QwenEngine
        lines = []
        info = heavy.Installer(self.home, "qwen3", log=lines.append).install()
        self.assertEqual(info["speakers"], ["serena", "vivian"])
        calls = self.calls.read_text()
        self.assertIn("venv", calls)
        self.assertIn("--index-url https://download.pytorch.org/whl/cpu", calls)   # CPU build, never CUDA
        self.assertIn("qwen-tts==0.1.1", calls)
        self.assertEqual(heavy.status(self.home, "qwen3")["model"], heavy.SPECS["qwen3"].model)
        eng = QwenEngine(self.home)
        cap = eng.probe()
        self.assertTrue(cap.installed)
        self.assertIn(("vivian", "Vivian"), cap.voices)
        try:
            audio, sr = eng.synth("Olá, Miwa aqui.", VoiceProfile(engine="qwen3", style="animado"), "claude")
            self.assertEqual(sr, 24000)
            self.assertGreater(len(audio), 2400)
            self.assertLessEqual(float(np.abs(audio).max()), 0.51)
            audio2, _ = eng.synth("Mais uma frase, mesmo processo.", VoiceProfile(engine="qwen3"), "codex")
            self.assertGreater(len(audio2), len(audio))
            with self.assertRaises(RuntimeError):            # worker errors are surfaced, process survives
                eng.synth("por favor falhe", VoiceProfile(engine="qwen3"), "codex")
            eng.synth("ainda vivo", VoiceProfile(engine="qwen3"), "codex")
        finally:
            eng.close()
        heavy.Installer(self.home, "qwen3").uninstall()
        self.assertFalse(heavy.engine_dir(self.home, "qwen3").exists())
        self.assertFalse(QwenEngine(self.home).probe().installed)

    def test_failed_step_leaves_no_marker(self):
        import os
        from unittest import mock
        from kaguya.voice import heavy
        with mock.patch.dict(os.environ, {"FAKE_UV_FAIL": "1"}):
            with self.assertRaises(RuntimeError):
                heavy.Installer(self.home, "qwen3", log=lambda _l: None).install()
        self.assertEqual(heavy.status(self.home, "qwen3"), {})

    def test_cancel_stops_install(self):
        from kaguya.voice import heavy
        inst = heavy.Installer(self.home, "qwen3", log=lambda _l: None)
        inst.cancel.set()
        with self.assertRaises(RuntimeError):
            inst.install()
        self.assertEqual(heavy.status(self.home, "qwen3"), {})

    def test_cancel_during_a_silent_download_is_immediate(self):
        import os
        from unittest import mock
        from kaguya.voice import heavy
        inst = heavy.Installer(self.home, "qwen3", log=lambda _l: None)
        threading.Timer(0.5, inst.cancel.set).start()
        t0 = time.monotonic()
        with mock.patch.dict(os.environ, {"FAKE_UV_SLEEP": "60"}):
            with self.assertRaises(RuntimeError) as ctx:
                inst.install()
        self.assertLess(time.monotonic() - t0, 10)
        self.assertIn("cancelada", str(ctx.exception))
        self.assertEqual(heavy.status(self.home, "qwen3"), {})

    def test_uv_checksum_mismatch_installs_nothing(self):
        import io as _io
        import zipfile as _zip
        from unittest import mock
        from kaguya.voice import heavy
        buf = _io.BytesIO()
        with _zip.ZipFile(buf, "w") as z:
            z.writestr("uv.exe", b"MZ adulterado")
        with mock.patch.object(heavy.shutil, "which", return_value=None), \
                mock.patch.dict(heavy.UV_ASSETS, {sys.platform: ("uv.zip", "0" * 64)}), \
                mock.patch.object(heavy.urllib.request, "urlopen",
                                  return_value=mock.Mock(read=lambda: buf.getvalue())):
            with self.assertRaises(RuntimeError) as ctx:
                heavy.Installer(self.home, "qwen3", log=lambda _l: None).uv()
        self.assertIn("checksum", str(ctx.exception))
        self.assertFalse((heavy.engine_dir(self.home, "qwen3") / "uv").exists())
