"""UI smoke tests (Qt offscreen) with fake CLIs. Skipped when PySide6 is not installed."""
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except Exception:  # pragma: no cover - environment without Qt
    HAVE_QT = False

from kaguya.voice.router import route  # noqa: E402
from kaguya.voice.tts import clean_for_speech  # noqa: E402
from tests.helpers import fake_env, git_init, make_fake_clis  # noqa: E402


class VoiceLogic(unittest.TestCase):
    def test_spoken_commands_never_interrupt(self):
        self.assertEqual(route("como está a tarefa?")[0], "status")
        self.assertEqual(route("Depois, criar HUD de chakra"), ("later", "criar HUD de chakra"))
        self.assertEqual(route("ideia: modo sharingan")[0], "idea")
        self.assertEqual(route("pare de falar")[0], "stop")
        self.assertEqual(route("implemente as missões")[0], "message")

    def test_speech_text_cleanup(self):
        t = clean_for_speech("**Feito** veja https://x.y\n```java\nclass A{}\n```\n- item")
        self.assertNotIn("```", t)
        self.assertNotIn("https", t)
        self.assertIn("código omitido", t)


@unittest.skipUnless(HAVE_QT and shutil.which("git"), "PySide6 e git necessários")
class UiBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from kaguya.ui import theme
        theme.load_fonts()
        cls.app.setStyleSheet(theme.stylesheet())

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        os.environ["KAGUYA_HOME"] = str(root / "home")
        self.addCleanup(os.environ.pop, "KAGUYA_HOME")
        make_fake_clis(root / "bin")
        self.project = root / "Projeto Ação"
        git_init(self.project)
        self.vault = root / "Segundo Cérebro"
        (self.vault / ".obsidian").mkdir(parents=True)
        (self.vault / "nota.md").write_text("# Forge\nEventos", encoding="utf-8")
        from kaguya.orchestrator.engine import Engine
        from kaguya.store import Store
        self.store = Store(root / "home" / "studio.sqlite3")
        self.engine = Engine(self.store, home=root / "home",
                             env=fake_env(root / "bin", FAKE_VERDICTS=str(root / "v.txt"), FAKE_CODEX_WRITE="1"))
        (root / "v.txt").write_text("aprovado\n", encoding="utf-8")

    def window(self):
        from kaguya.ui.main_window import MainWindow
        w = MainWindow(self.store, self.engine)
        w.resize(1366, 740)
        w.show()
        self.addCleanup(self._flush_deletes)  # runs last: really destroy the window now, not at interpreter exit
        self.addCleanup(w.deleteLater)
        self.addCleanup(self._wait_bg)   # cleanups run in reverse: detach first, then drain
        self.addCleanup(w.detach)
        self.addCleanup(lambda: [self.engine.wait(p["id"], 30) for p in self.store.projects()])
        return w

    def _flush_deletes(self):
        from PySide6.QtCore import QCoreApplication, QEvent
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()

    def _wait_bg(self):
        from kaguya.ui.common import wait_background
        for _ in range(3):  # callbacks delivered by processEvents may start more background work
            wait_background(30)
            self.app.processEvents()

    def pump(self, cond, timeout=30):
        end = time.time() + timeout
        while time.time() < end:
            self.app.processEvents()
            if cond():
                return True
            time.sleep(0.02)
        return False



@unittest.skipUnless(HAVE_QT and shutil.which("git"), "PySide6 e git necessários")
class UiSmoke(UiBase):
    def test_link_project_dialog_and_persistence(self):
        from kaguya.ui.dialogs import ProjectDialog
        w = self.window()
        dlg = ProjectDialog(self.store, w)
        self.assertFalse(dlg.save_btn.isEnabled())
        dlg.folder.edit.setText(f'"{self.project}"')  # pasted with quotes
        dlg.folder.verify()
        self.assertTrue(dlg.save_btn.isEnabled(), dlg.folder.status.text())
        dlg.r_own.setChecked(True)
        dlg.vault.edit.setText(str(self.vault))
        dlg.vault.verify()
        dlg.save()
        self.assertEqual(dlg.result(), 1)
        p = self.store.project(dlg.pid)
        self.assertEqual(Path(p["directory"]), self.project.resolve())
        self.assertEqual(Path(p["vault"]), self.vault.resolve())

    def test_team_task_from_ui_updates_chat_mascots_and_stepper(self):
        pid = self.store.add_project("Projeto", self.project)
        self.store.set_global_vault(self.vault)
        w = self.window()
        w.select_project(pid)
        before = w.chat.view.lay.count()
        self.assertTrue(w.send_message("implemente a classe Missao", "equipe", ""))
        self.assertTrue(self.pump(lambda: not w.engine.is_running(pid) and w.store.tasks(pid)[0]["status"] != "running"))
        self.pump(lambda: w.stepper.current == "final", 5)
        self.assertEqual(self.store.tasks(pid)[0]["status"], "approved")
        self.assertGreater(w.chat.view.lay.count(), before + 2)
        self.assertEqual(w.stepper.current, "final")
        self.assertIn(w.mascots["claude"].state, ("approved", "success"))
        self.assertFalse(w.mascots["codex"].image().isNull())

    def test_later_does_not_start_worker(self):
        pid = self.store.add_project("Projeto", self.project)
        w = self.window()
        w.select_project(pid)
        w.send_message("criar HUD", "equipe", "DEPOIS")
        self.assertFalse(w.engine.is_running(pid))
        self.assertEqual(self.store.tasks(pid)[0]["status"], "parked")

    def test_all_pages_render_without_projects(self):
        w = self.window()
        for key in ("chat", "webchats", "queue", "memory", "agents", "usage", "diag", "settings"):
            w.go(key)
            self.app.processEvents()
            self.assertFalse(w.grab().isNull())

    def test_responsive_modes(self):
        w = self.window()
        w.resize(1200, 720)
        self.app.processEvents()
        self.assertEqual(w._mode, "compact")
        self.assertEqual(w.nav_buttons["chat"].text(), "")
        w.resize(1600, 900)
        self.app.processEvents()
        self.assertEqual(w._mode, "wide")
        self.assertEqual(w.nav_buttons["chat"].text(), "Conversa")

    def test_kaguya_v2_is_default_and_v1_still_available(self):
        from kaguya.ui.mascot import Mascot
        home = Path(os.environ["KAGUYA_HOME"])
        m = Mascot("codex", home / "m.json")
        self.assertEqual(m.prefs.variant, "v2")
        self.assertIn("dormindo", m.profile["expressions"])
        m.set_state("limit")
        self.assertTrue(m.sprite_path(m.expression).name.endswith("kaguya_dormindo.png"))
        self.assertIn("kaguya_v2", str(m.sprite_path(m.expression)))
        for st in ("idle", "running", "success", "error", "cancelled", "limit", "speaking", "listening", "approved"):
            m.set_state(st)
            self.assertTrue(m.sprite_path(m.expression).is_file(), st)
            self.assertFalse(m.image().isNull())
        m.set_variant("v1")
        self.assertEqual(len(m.profile["expressions"]), 18)
        self.assertEqual(Mascot("codex", home / "m.json").prefs.variant, "v1")  # persisted

    def test_crisp_sprite_has_binary_alpha_and_files_untouched(self):
        from kaguya.appdirs import ASSETS
        from kaguya.ui.widgets import load_sprite
        src = ASSETS / "mascots" / "claude" / "expressoes" / "claude_feminina_neutra.png"
        before = src.read_bytes()
        img = load_sprite(src, True)
        alphas = {img.pixelColor(x, y).alpha() for x in range(0, 128, 3) for y in range(0, 128, 3)}
        self.assertTrue(alphas <= {0, 255})
        self.assertEqual(src.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(HAVE_QT and shutil.which("git"), "PySide6 e git necessários")
class LiveUi(UiBase):
    def test_live_window_full_turn_with_fake_claude(self):
        from unittest import mock
        from kaguya.live.session import LiveSession
        from kaguya.ui.live_window import LiveWindow
        pid = self.store.add_project("Projeto", self.project)
        w = self.window()
        w.select_project(pid)
        spoken = []
        w.voice.say = lambda text, agent: spoken.append((agent, text)) or True
        w.voice._ensure_queue = lambda: None  # no audio device in CI: speech is captured above instead
        w.live_window = LiveWindow(w)
        w.live_window.set_agent("claude")
        w.live_window.show()
        exes = {"claude": self.engine.ensure_ready("claude", str(self.project)),
                "codex": RuntimeError("codex indisponível")}
        with mock.patch.object(LiveSession, "_open_microphone", lambda self: None):
            w._live_ready(exes, "claude", str(self.project))
        self.assertIsNotNone(w.live_session)
        w.live_session.handle_text("Oi, tudo bem?")
        self.assertTrue(self.pump(lambda: bool(w.live_window.ai.text()), 30), w.live_window.err.text())
        self.assertIn("Oi, tudo bem?", w.live_window.you.text())
        self.assertTrue(self.pump(lambda: bool(spoken), 10))
        self.assertTrue(all(a == "claude" for a, _ in spoken))
        # the switch button reaches the session; the codex failure becomes a visible error
        w.live_window.switch_btn.click()
        self.assertTrue(self.pump(lambda: bool(w.live_window.err.text()), 10))
        w.live_window.close()
        self.assertIsNone(w.live_session)
        self.assertIsNone(w.live_window)

    def test_live_requires_transcription(self):
        from unittest import mock
        from kaguya.voice import stt
        w = self.window()
        fake = stt.VoiceStatus(recorder=False, transcriber=False, missing=["faster_whisper"], model_cached=False)
        with mock.patch.object(stt, "status", return_value=fake), \
                mock.patch("kaguya.ui.main_window.QMessageBox.information") as info:
            w.start_live(None)
        info.assert_called_once()
        self.assertIsNone(w.live_window)


@unittest.skipUnless(HAVE_QT and shutil.which("git"), "PySide6 e git necessários")
class AutonomyUi(UiBase):
    def test_autonomous_mode_toggle_send_and_undo(self):
        from unittest import mock
        from PySide6.QtWidgets import QMessageBox
        pid = self.store.add_project("Projeto", self.project)
        w = self.window()
        w.select_project(pid)
        comp = w.chat.composer
        self.assertFalse(comp.t_auto.isChecked())
        with mock.patch("kaguya.ui.main_window.QMessageBox.question", return_value=QMessageBox.No):
            comp.t_auto.click()  # user declines the explanation → stays off
        self.assertFalse(comp.t_auto.isChecked())
        self.assertFalse(self.store.autonomous(pid))
        with mock.patch("kaguya.ui.main_window.QMessageBox.question", return_value=QMessageBox.Yes) as q:
            comp.t_auto.click()
        q.assert_called_once()
        self.assertTrue(self.store.autonomous(pid))
        self.assertTrue(comp.t_write.isChecked() and not comp.t_write.isEnabled())
        self.assertTrue(comp.t_cmds.isChecked() and comp.t_tests.isChecked())
        # remembered per project, explanation not repeated
        w.select_project(None)
        self.assertFalse(comp.t_auto.isChecked())
        w.select_project(pid)
        self.assertTrue(comp.t_auto.isChecked())
        with mock.patch.object(w, "confirm_write", side_effect=AssertionError("não deveria pedir confirmação")):
            self.assertTrue(w.send_message("crie o arquivo de missões", "codex", ""))
        self.assertTrue(self.pump(lambda: self.store.tasks(pid)[0]["status"] not in ("queued", "running")))
        t = self.store.tasks(pid)[0]
        self.assertEqual(t["status"], "executed", t["result"])
        self.assertTrue(t["checkpoint"])
        self.assertTrue((self.project / "feito_pelo_codex.txt").exists())
        w.go("queue")
        w.queue.refresh()
        w.queue.table.selectRow(0)
        self.assertTrue(w.queue.b_undo.isEnabled())
        w.queue.undo(confirm=False)
        self.assertFalse((self.project / "feito_pelo_codex.txt").exists())
        self.assertFalse(w.queue.b_undo.isEnabled())
        # turning it off unlocks the manual toggles with their previous values
        comp.t_auto.click()
        self.assertFalse(self.store.autonomous(pid))
        self.assertTrue(comp.t_write.isEnabled())
        self.assertFalse(comp.t_write.isChecked())

    def test_autonomy_requires_git(self):
        from unittest import mock
        from PySide6.QtWidgets import QMessageBox
        plain = Path(self.tmp.name) / "sem git"
        plain.mkdir()
        pid = self.store.add_project("Sem Git", plain)
        w = self.window()
        w.select_project(pid)
        with mock.patch("kaguya.ui.main_window.QMessageBox.question", return_value=QMessageBox.No):
            w.chat.composer.t_auto.click()
        self.assertFalse(w.chat.composer.t_auto.isChecked())
        self.assertFalse(self.store.autonomous(pid))


@unittest.skipUnless(HAVE_QT and shutil.which("git"), "PySide6 e git necessários")
class DesktopUi(UiBase):
    def test_use_pc_consent_task_overlay_and_stop(self):
        from unittest import mock
        from PySide6.QtWidgets import QMessageBox
        from kaguya.desktop import control
        self.engine.env["KAGUYA_DESKTOP_BACKEND"] = "fake"
        pid = self.store.add_project("Projeto", self.project)
        w = self.window()
        w.select_project(pid)
        comp = w.chat.composer
        with mock.patch("kaguya.ui.main_window.QMessageBox.question", return_value=QMessageBox.No):
            comp.t_pc.click()
        self.assertFalse(comp.t_pc.isChecked())
        with mock.patch("kaguya.ui.main_window.QMessageBox.question", return_value=QMessageBox.Yes) as q:
            comp.t_pc.click()
        self.assertIn("Minecraft", q.call_args[0][2])          # explains the window restriction
        self.assertIn("OpenAI/Anthropic", q.call_args[0][2])   # and that screenshots go to the AI
        self.assertTrue(comp.t_pc.isChecked())
        w.select_project(None)
        w.select_project(pid)
        self.assertTrue(comp.t_pc.isChecked())  # remembered per project
        shown = []
        orig = w._desktop_event
        w._desktop_event = lambda ev: (shown.append(ev["active"]), orig(ev))
        self.assertTrue(w.send_message("abra o jogo e confira o HUD", "claude", ""))
        self.assertTrue(self.pump(lambda: self.store.tasks(pid)[0]["status"] not in ("queued", "running")))
        self.pump(lambda: shown == [True, False], 5)
        self.assertEqual(shown, [True, False])
        t = self.store.tasks(pid)[0]
        self.assertTrue(t["desktop"])
        self.assertFalse(w.desktop_overlay.isVisible())
        self.assertGreaterEqual(w.desktop_overlay.count, 2)  # screenshot + click seen by the overlay
        w.stop_desktop("botão Parar")
        self.assertIn("Parar", control.stop_reason(self.engine.home / "desktop"))


@unittest.skipUnless(HAVE_QT and shutil.which("git"), "PySide6 e git necessários")
class CallByNameUi(UiBase):
    def test_called_by_name_mascot_bubble_task_and_spoken_result(self):
        pid = self.store.add_project("Projeto", self.project)
        w = self.window()
        w.select_project(pid)
        spoken = []
        w.voice.say = lambda text, agent: spoken.append((agent, text)) or True
        wk = w.wake
        wk.on_event({"type": "called", "agent": "claude", "text": "Miwa, vê o log do servidor"})
        self.assertTrue(w.mascots["claude"].window.isVisible())    # Miwa pops up on the desktop
        self.assertTrue(wk.bubble.isVisible())
        wk.on_event({"type": "caption", "role": "assistant", "agent": "claude", "text": "Vi sim: o erro é no MissaoManager.",
                     "final": True})
        self.assertIn("MissaoManager", wk.bubble.text.text())
        self.assertIn("Miwa, vê o log", wk.bubble.who.text())
        wk.on_task("corrigir o MissaoManager", "claude")          # not autonomous → read-only analysis task
        t = self.store.tasks(pid)[0]
        self.assertEqual((t["kind"], t["target"], t["allow_write"]), ("execute", "claude", 0))
        self.assertIn("modo autônomo", spoken[-1][1])
        self.assertTrue(self.pump(lambda: self.store.get_task(t["id"])["status"] not in ("queued", "running")))
        self.assertTrue(self.pump(lambda: len(spoken) >= 2 and spoken[-1][1].startswith(("Terminei", "A tarefa")), 10))
        self.assertEqual(spoken[-1][0], "claude")
        self.assertNotIn("EVIDÊNCIAS", spoken[-1][1])
        wk.bubble.hide()

    def test_typed_name_routes_message_and_chat_bubbles(self):
        from kaguya.ui.page_chat import MessageCard
        pid = self.store.add_project("Projeto", self.project)
        w = self.window()
        w.select_project(pid)
        self.assertTrue(w.send_message("Miwa, poderia ver isso para mim?", "equipe", ""))
        self.assertEqual(self.store.tasks(pid)[0]["target"], "claude")
        cards = [w.chat.view.lay.itemAt(i).widget() for i in range(w.chat.view.lay.count())]
        cards = [c for c in cards if isinstance(c, MessageCard)]
        self.assertEqual(cards[0].side, "right")  # the user's own message on the right, like WhatsApp
        self.pump(lambda: any(c.side == "left" for c in [w.chat.view.lay.itemAt(i).widget()
                                                          for i in range(w.chat.view.lay.count())]
                              if isinstance(c, MessageCard)), 20)

    def test_webchats_page_never_loads_until_asked_and_copies_context(self):
        from PySide6.QtWidgets import QApplication
        pid = self.store.add_project("NarutoCD", self.project)
        w = self.window()
        w.select_project(pid)
        w.go("webchats")
        self.assertEqual(w.webchats.views, {})            # nothing opened (no network) until the user clicks
        from kaguya.ui.page_webchats import LIMITS_NOTE
        self.assertIn("<b>mesmo</b> limite", LIMITS_NOTE)  # honest: Claude chat and Claude Code share the limit
        w.webchats.copy_context()
        text = QApplication.clipboard().text()
        self.assertIn("NarutoCD", text)
        self.assertTrue(text.rstrip().endswith("Minha pergunta:"))

    def test_close_goes_to_background_when_tray_exists(self):
        w = self.window()

        class FakeTray:
            msgs = []

            def showMessage(self, *a):
                self.msgs.append(a)

            def hide(self):
                pass
        w.tray = FakeTray()
        w.close()
        self.assertFalse(w.isVisible())                     # hidden, still running
        self.assertFalse(w._detached)
        self.assertTrue(FakeTray.msgs)                      # explained once
        w.show_from_tray()
        self.assertTrue(w.isVisible())
        w.tray = None


@unittest.skipUnless(HAVE_QT and shutil.which("git"), "PySide6 e git necessários")
class PcModeUi(UiBase):
    def test_meu_computador_consent_tasks_confirm_and_alarm(self):
        from unittest import mock
        from PySide6.QtWidgets import QMessageBox
        from kaguya.desktop import assistant
        self.engine.env["KAGUYA_DESKTOP_BACKEND"] = "fake"
        home = Path(self.tmp.name) / "Usuario"
        (home / "Downloads").mkdir(parents=True)
        w = self.window()
        spoken = []
        w.voice.say = lambda text, agent: spoken.append((agent, text)) or True
        tid, note = w.spoken_task("abrir o WhatsApp e mandar mensagem", "claude", "pc")
        self.assertIsNone(tid)                                   # not enabled yet → explains instead
        self.assertIn("Meu computador", note)
        with mock.patch("pathlib.Path.home", return_value=home), \
                mock.patch("kaguya.ui.main_window.QMessageBox.question", return_value=QMessageBox.Yes) as q:
            w.open_pc_mode()
        self.assertIn("confirmação", q.call_args[0][2])
        pc = self.store.get_setting("pc.project_id")
        self.assertEqual(w.pid, pc)
        self.assertTrue(w.pc_btn.isChecked())
        self.assertIn("assistente pessoal", w.p_git.text())
        self.assertTrue(w.send_message("Kaguya, analise o arquivo Batata Game 2 nos Downloads", "equipe", ""))
        t = self.store.tasks(pc)[0]
        self.assertEqual((t["target"], t["allow_write"], t["desktop"]), ("codex", 1, 1))
        self.assertTrue(self.pump(lambda: self.store.get_task(t["id"])["status"] not in ("queued", "running")))
        self.assertEqual(self.store.get_task(t["id"])["status"], "executed", self.store.get_task(t["id"])["result"])
        tid, note = w.spoken_task("criar timer de 5 minutos", "claude", "pc")   # by voice, now enabled
        self.assertEqual(self.store.get_task(tid)["target"], "claude")
        # a confirmation asked by the assistant process appears with the mascot and returns the answer
        base = self.engine.home / "desktop"
        import threading
        result = {}
        th = threading.Thread(target=lambda: result.setdefault("ok", assistant.ask_user(base, "Enviar para Mamãe: oi", 10)))
        th.start()
        self.assertTrue(self.pump(lambda: bool(w.assistant.shown), 5))
        box = next(iter(w.assistant.shown.values()))
        self.assertIn("Enviar para Mamãe", box.text())
        box.button(QMessageBox.Yes).click()
        th.join(5)
        self.assertTrue(result["ok"])
        assistant.add_alarm(base, minutes=0.001, text="tirar o bolo", agent="claude")
        self.assertTrue(self.pump(lambda: any("tirar o bolo" in t for _, t in spoken), 5))
        self.assertTrue(w.mascots["claude"].window.isVisible())
        w.wake.bubble.hide()


def tearDownModule():
    """Destroy every top-level window while QApplication still exists (Qt objects that survive until
    interpreter shutdown are destroyed in arbitrary order, which can crash at exit)."""
    if not HAVE_QT:
        return
    import gc
    from PySide6.QtCore import QCoreApplication, QEvent
    app = QApplication.instance()
    if app is None:
        return
    for wdg in app.topLevelWidgets():
        wdg.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()
    gc.collect()
