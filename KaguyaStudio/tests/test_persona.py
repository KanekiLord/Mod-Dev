"""Configurable personality: stored per assistant, reaches tasks and voice, never overrides the rules."""
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kaguya import persona  # noqa: E402
from kaguya.store import Store  # noqa: E402


class PersonaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "s.db")

    def test_defaults_save_and_text(self):
        self.assertEqual(persona.load(self.store, "codex").preset, "kaguya")
        self.assertEqual(persona.load(self.store, "claude").preset, "miwa")
        p = persona.Persona(preset="tsundere", nickname="senpai", formality="tu", humor=2, length="curta",
                            emoji=True, extra="chama os bugs de Akatsuki")
        persona.save(self.store, "claude", p)
        text = persona.for_agent(self.store, "claude")
        for part in ("Miwa", "n-não", "senpai", '"tu"', "Bastante humor", "curtas", "Akatsuki", "emojis",
                     "regras e permissões acima continuam valendo"):
            self.assertIn(part, text)
        voice = persona.for_agent(self.store, "claude", voice=True)
        self.assertNotIn("Pode usar alguns emojis", voice)
        self.assertIn("nada de emojis", voice)
        self.assertEqual(persona.for_agent(self.store, "equipe"), "")
        p.enabled = False
        persona.save(self.store, "claude", p)
        self.assertEqual(persona.for_agent(self.store, "claude"), "")

    @unittest.skipUnless(shutil.which("git"), "git necessário")
    def test_persona_reaches_the_agent_prompt_after_the_rules(self):
        from kaguya.messages import classify_message
        from kaguya.orchestrator.engine import Engine
        from tests.helpers import fake_env, git_init, make_fake_clis
        root = Path(self.tmp.name)
        make_fake_clis(root / "bin")
        git_init(root / "proj")
        pid = self.store.add_project("P", root / "proj")
        persona.save(self.store, "codex", persona.Persona(preset="gamer", nickname="player 1"))
        eng = Engine(self.store, home=root / "home", env=fake_env(root / "bin"))
        prompt = eng._with_persona("REGRAS...\n\nTAREFA:\nfaça x", "codex")
        self.assertLess(prompt.index("REGRAS"), prompt.index("PERSONALIDADE"))
        self.assertLess(prompt.index("PERSONALIDADE"), prompt.index("TAREFA:"))
        self.assertIn("player 1", prompt)
        from unittest import mock
        import kaguya.orchestrator.engine as engine_mod
        sent = []
        real = engine_mod.run_agent

        def spy(agent, exe, caps, cwd, prompt, *a, **kw):
            sent.append((agent, prompt))
            return real(agent, exe, caps, cwd, prompt, *a, **kw)
        with mock.patch.object(engine_mod, "run_agent", spy):
            tid = eng.submit(pid, classify_message("@codex: explique o projeto", "equipe"))
            eng.wait(pid, 60)
        self.assertEqual(self.store.get_task(tid)["status"], "executed")
        self.assertEqual(sent[0][0], "codex")
        self.assertIn("player 1", sent[0][1])                  # what really went to the CLI
        self.assertIn("REGRAS DO KAGUYA STUDIO", sent[0][1])


if __name__ == "__main__":
    unittest.main()
