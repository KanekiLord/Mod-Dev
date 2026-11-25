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
class UiSmoke(unittest.TestCase):
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
        self.addCleanup(w.deleteLater)
        self.addCleanup(w.detach)
        self.addCleanup(self._wait_bg)
        self.addCleanup(lambda: [self.engine.wait(p["id"], 30) for p in self.store.projects()])
        return w

    def _wait_bg(self):
        from kaguya.ui.common import wait_background
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
        for key in ("chat", "queue", "memory", "agents", "usage", "diag", "settings"):
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
