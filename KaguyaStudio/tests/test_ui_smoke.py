"""Optional graphical smoke test; skipped on headless Linux without DISPLAY."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core import Store

@unittest.skipIf(os.name!='nt' and not os.environ.get('DISPLAY'), 'Necessita X11 ou Windows desktop')
class VisualSmokeTests(unittest.TestCase):
    def test_sidebar_navigation_selects_correct_existing_page(self):
        from studio import Studio
        app=Studio()
        try:
            app._nav_to(app.tab_memory)
            app.update()
            self.assertEqual(app.tabs.select(),str(app.tab_memory))
            self.assertEqual(app.metric_agents.get(),'72 catalogados')
            app._nav_to(app.tab_chat)
            self.assertEqual(app.tabs.select(),str(app.tab_chat))
        finally:
            app.destroy()

    def test_team_job_enqueues_runs_and_does_not_edit_vault(self):
        from studio import Studio
        with tempfile.TemporaryDirectory() as root:
            base=Path(root);repo=base/'repo';vault=base/'vault'
            repo.mkdir();vault.mkdir()
            (vault/'tasks').mkdir()
            todo=vault/'tasks'/'todo.md';todo.write_text('tarefa original',encoding='utf-8')
            app=Studio()
            try:
                app.store=Store(base/'studio.sqlite3')
                app.pid=app.store.add_project('Projeto de teste',repo,vault)
                app._load_projects()
                with patch('studio.run_cli', side_effect=lambda target, *args, **kwargs:(0,f'{target} completou')) as call:
                    app.entry.insert('1.0','@Equipe: revisar o projeto')
                    app._send()
                    deadline=time.monotonic()+5
                    while time.monotonic()<deadline:
                        app.update()
                        if app.store.tasks(app.pid)[0]['status']=='executed':break
                        time.sleep(0.03)
                    self.assertEqual(app.store.tasks(app.pid)[0]['status'],'executed')
                    self.assertEqual([x.args[0] for x in call.call_args_list],['codex','claude'])
                    self.assertEqual(todo.read_text(encoding='utf-8'),'tarefa original')
            finally:app.destroy()

if __name__=='__main__':unittest.main()

@unittest.skipIf(os.name!='nt' and not os.environ.get('DISPLAY'), 'Necessita X11 ou Windows desktop')
class MascotVisualTests(unittest.TestCase):
    def test_floating_mascot_toggle_and_quick_chat_later(self):
        from studio import Studio
        with tempfile.TemporaryDirectory() as base:
            repo=Path(base)/'project';vault=Path(base)/'vault'
            repo.mkdir();vault.mkdir()
            app=Studio()
            try:
                app.store=Store(Path(base)/'tasks.sqlite3')
                app.pid=app.store.add_project('Test',repo,vault)
                app._load_projects();app.update()
                app.mascot.show()
                self.assertTrue(app.mascot.window.winfo_exists())
                app._toggle_float();self.assertFalse(app.mascot.settings.visible)
                app._toggle_float();self.assertTrue(app.mascot.settings.visible)
                with patch('studio.run_cli',side_effect=AssertionError('Nao deve iniciar CLI')):
                    ok=app._quick_message('analisar visual', 'Codex','DEPOIS')
                    self.assertTrue(ok)
                    task=app.store.tasks(app.pid)[0]
                    self.assertEqual(task['kind'],'later')
                    self.assertFalse(task['allow_write'])
                    self.assertEqual(task['target'],'codex')
            finally:app.destroy()
