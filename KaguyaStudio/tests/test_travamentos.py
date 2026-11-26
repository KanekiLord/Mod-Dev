"""Regressions for the report of 26/11/2026: Live stuck in "Preparando…", voice stuck in "Transcrevendo…",
queue blocked by a task that Cancelar could not stop. Nothing may wait forever."""
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.helpers import make_fake_clis, fake_env, git_init  # noqa: E402
from kaguya import packs  # noqa: E402
from kaguya.messages import Intent  # noqa: E402
from kaguya.orchestrator.engine import Engine  # noqa: E402
from kaguya.store import Store  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        make_fake_clis(self.bin)
        self.project = self.root / "proj"
        git_init(self.project)
        self.store = Store(self.root / "home" / "studio.sqlite3")
        self.pid = self.store.add_project("Proj", self.project)
        self.events = []

    def engine(self, **env):
        eng = Engine(self.store, self.events.append, home=self.root / "home", env=fake_env(self.bin, **env))
        self.addCleanup(lambda: eng.wait(self.pid, 30))
        return eng


@unittest.skipUnless(shutil.which("git"), "git necessário")
class Queue(Base):
    def test_cancel_stops_a_cli_check_that_never_answers(self):
        eng = self.engine(FAKE_CLAUDE_AUTH_HANG="1")
        tid = eng.submit(self.pid, Intent("execute", "claude", "analise o projeto"))
        self.assertTrue(self._until(lambda: (self.store.get_task(tid).get("stage") or "").startswith("verificando")))
        t0 = time.monotonic()
        self.assertTrue(eng.cancel(self.pid))
        self.assertTrue(self._until(lambda: not eng.is_running(self.pid), 15))
        self.assertLess(time.monotonic() - t0, 15)
        self.assertEqual(self.store.get_task(tid)["status"], "cancelled")

    def test_a_task_that_ignores_cancel_is_released_and_the_next_one_runs(self):
        eng = self.engine()
        stuck = threading.Event()
        real = eng._run_single

        def frozen(pid, task, cancel):
            if "travada" in task["title"]:
                stuck.wait(60)                       # ignores Cancelar (like a hung external program)
                return "executed", "tarde demais"
            return real(pid, task, cancel)
        eng._run_single = frozen
        first = eng.submit(self.pid, Intent("execute", "codex", "tarefa travada"))
        self.assertTrue(self._until(lambda: eng.current_task(self.pid) == first))
        second = eng.submit(self.pid, Intent("execute", "codex", "explique o projeto"))
        self.assertEqual(self.store.get_task(second)["status"], "queued")      # waits behind the stuck one
        eng.cancel(self.pid, grace=1)
        self.assertTrue(self._until(lambda: self.store.get_task(first)["status"] == "cancelled", 10))
        self.assertFalse(eng.is_running(self.pid))
        eng.start_worker(self.pid)                                             # (a new message does this)
        self.assertTrue(self._until(lambda: self.store.get_task(second)["status"] == "executed", 60),
                        self.store.get_task(second)["result"])
        stuck.set()                                                            # the abandoned thread wakes up…
        time.sleep(0.5)
        self.assertEqual(self.store.get_task(first)["status"], "cancelled")    # …and changes nothing

    @staticmethod
    def _until(cond, timeout=20):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if cond():
                return True
            time.sleep(0.05)
        return False


class Speech(unittest.TestCase):
    def test_model_is_never_fetched_from_the_internet_on_load(self):
        from kaguya.voice import stt
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(stt.ModelMissing):
                stt.Transcriber(Path(d), "small").load()       # missing → asks the UI, never downloads silently
            self.assertFalse(stt.model_cached(Path(d), "small"))
            fake = Path(d) / "models--Systran--faster-whisper-small" / "snapshots" / "x" / "model.bin"
            fake.parent.mkdir(parents=True)
            fake.write_bytes(b"0")
            self.assertTrue(stt.model_cached(Path(d), "small"))
            self.assertFalse(stt.model_cached(Path(d), "base"))   # "small" must not count as "base" (old glob did)


# stands in for PowerShell + System.Speech: same line protocol, writes a real WAV
FAKE_SAPI = r"""
import json, sys, time, wave
time.sleep(0.3)                                    # startup cost paid once
print("pronto", flush=True)
for line in sys.stdin:
    r = json.loads(line)
    with wave.open(r["wav"], "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(b"\x00\x10" * 1600 * max(1, len(r["text"]) // 10))
    print("ok", flush=True)
"""


class WindowsVoice(unittest.TestCase):
    def test_one_process_serves_every_sentence(self):
        import wave
        from kaguya.voice.speech import SapiWorker
        with tempfile.TemporaryDirectory() as d:
            script = Path(d) / "sapi.py"
            script.write_text(FAKE_SAPI, encoding="utf-8")
            wk = SapiWorker([sys.executable, str(script)])
            self.addCleanup(wk.close)
            t0 = time.monotonic()
            for i in range(10):
                out = Path(d) / f"{i}.wav"
                wk.render(f"Frase número {i} da resposta.", "Microsoft Maria", str(out))
                with wave.open(str(out)) as w:
                    self.assertGreater(w.getnframes(), 0)
            self.assertLess(time.monotonic() - t0, 3)      # 10 sentences, one startup
            pid = wk.proc.pid
            wk.render("mais uma", "", str(Path(d) / "x.wav"))
            self.assertEqual(wk.proc.pid, pid)                  # same process, not one per sentence

    @unittest.skipUnless(sys.platform == "win32", "PowerShell/System.Speech só no Windows")
    def test_real_windows_voice_renders_sentences_quickly(self):
        import wave
        from kaguya.voice.speech import SapiWorker
        wk = SapiWorker()
        self.addCleanup(wk.close)
        with tempfile.TemporaryDirectory() as d:
            t0 = time.monotonic()
            wk.warm()
            startup = time.monotonic() - t0
            t1 = time.monotonic()
            for i in range(5):
                out = Path(d) / f"{i}.wav"
                wk.render(f"Esta é a frase {i} da resposta.", "", str(out))
                with wave.open(str(out)) as w:
                    self.assertGreater(w.getnframes(), 1000)
            per = (time.monotonic() - t1) / 5
            print(f"\nvoz do Windows: abertura {startup:.1f} s, {per:.2f} s por frase")
            self.assertLess(per, 3)

    def test_engine_choice_never_lists_voices(self):
        from kaguya.voice.engines import VoiceEngines, VoiceProfile, WindowsEngine
        eng = VoiceEngines(mock.Mock(ready=False))
        import types
        with mock.patch.object(WindowsEngine, "probe", side_effect=AssertionError("listou vozes por frase")), \
                mock.patch("kaguya.voice.engines.sys", types.SimpleNamespace(platform="win32")), \
                mock.patch("kaguya.voice.tts.Speaker.backend", return_value="Windows SAPI (System.Speech)"):
            self.assertEqual(eng.resolve(VoiceProfile()).id, "windows")


class Packs(unittest.TestCase):
    def test_choices_offer_the_install_folder_and_free_space(self):
        with tempfile.TemporaryDirectory() as d:
            home, inst = Path(d) / "dados", Path(d) / "D" / "Kaguya Studio"
            inst.mkdir(parents=True)
            found = packs.choices(home, install=inst)
            self.assertEqual([c.key for c in found], ["recomendada", "instalacao"])
            self.assertEqual(found[1].path, inst / "Pacotes")
            self.assertIsNotNone(found[1].free)

    def test_move_keeps_what_was_installed(self):
        with tempfile.TemporaryDirectory() as d:
            old, new = Path(d) / "a", Path(d) / "b"
            (old / "modelos" / "kokoro").mkdir(parents=True)
            (old / "modelos" / "kokoro" / "v.bin").write_bytes(b"voz")
            (old / "vozes" / "qwen3").mkdir(parents=True)
            self.assertEqual(packs.move(old, new), ["modelos", "vozes"])
            self.assertEqual((new / "modelos" / "kokoro" / "v.bin").read_bytes(), b"voz")
            self.assertFalse((old / "modelos").exists())
            (old / "modelos").mkdir()
            (old / "modelos" / "x").write_text("y")
            with self.assertRaises(FileExistsError):
                packs.move(old, new)                          # never overwrites


if __name__ == "__main__":
    unittest.main()
