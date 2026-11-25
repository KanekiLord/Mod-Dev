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
        p = persona.Persona(preset="tsundere", nickname="senpai", address="tu", humor=90, detail=10,
                            emoji=True, extra="chama os bugs de Akatsuki", third_person=True, proactive="erros")
        persona.save(self.store, "claude", p)
        text = persona.for_agent(self.store, "claude")
        for part in ("Miwa", "n-não", "senpai", '"tu"', "bastante humor", "respostas curtas", "Akatsuki", "emojis",
                     "terceira pessoa", "Só falar por conta própria em erros",
                     "regras e permissões acima continuam valendo", "nunca dentro de comandos"):
            self.assertIn(part, text)
        voice = persona.for_agent(self.store, "claude", voice=True)
        self.assertNotIn("Pode usar alguns emojis", voice)
        self.assertIn("nada de emojis", voice)
        self.assertNotIn("nunca dentro de comandos", voice)          # chat context: no task rule
        self.assertEqual(persona.for_agent(self.store, "equipe"), "")
        self.assertIn("princesa da lua", persona.for_agent(self.store, "codex"))  # Kaguya untouched
        p.enabled = False
        persona.save(self.store, "claude", p)
        self.assertEqual(persona.for_agent(self.store, "claude"), "")

    def test_profiles_from_4_9_are_converted(self):
        self.store.set_setting("persona.codex", {"preset": "engracada", "nickname": "chefe", "formality": "tu",
                                                 "humor": 2, "length": "detalhada", "emoji": False, "extra": "",
                                                 "enabled": True})
        p = persona.load(self.store, "codex")
        self.assertEqual((p.preset, p.address, p.nickname), ("descontraida", "tu", "chefe"))
        self.assertGreaterEqual(p.value("humor"), 67)
        self.assertGreaterEqual(p.value("detail"), 67)

    def test_project_override_name_export_import_reset(self):
        from kaguya.live.wake import detect_name, set_custom_name
        persona.save(self.store, "codex", persona.Persona(preset="kaguya", name="Hime"))
        persona.save(self.store, "codex", persona.Persona(preset="profissional"), pid=7)
        self.assertEqual(persona.load(self.store, "codex", 7).preset, "profissional")
        self.assertEqual(persona.load(self.store, "codex", 8).preset, "kaguya")   # other projects use global
        self.assertTrue(persona.has_project_override(self.store, "codex", 7))
        persona.clear_project(self.store, "codex", 7)
        self.assertFalse(persona.has_project_override(self.store, "codex", 7))
        self.assertEqual(persona.display_name(self.store, "codex"), "Hime")
        self.assertIn("você é a Hime", persona.for_agent(self.store, "codex"))
        set_custom_name("codex", "Hime")
        self.assertEqual(detect_name("Hime, abre o projeto")[0], "codex")
        set_custom_name("codex", "")
        exported = persona.export_json(self.store)
        self.assertNotIn("token", exported.lower())
        other = Store(Path(self.tmp.name) / "outro.db")
        self.assertEqual(sorted(persona.import_json(other, exported)), ["claude", "codex"])
        self.assertEqual(persona.load(other, "codex").name, "Hime")
        # the example format shipped in the requirements package
        example = {"schema_version": 1, "profiles": [{"id": "miwa", "name": "Miwa", "provider_default": "claude_code",
                   "style": {"formality": 0.55, "humor": 0.35, "initiative": 0.7, "warmth": 0.55, "verbosity": 0.5,
                             "self_reference_third_person": False, "address_user": "Você",
                             "behavior": "Investigativa e curiosa."}}]}
        import json as _json
        self.assertEqual(persona.import_json(other, _json.dumps(example)), ["claude"])
        m = persona.load(other, "claude")
        self.assertEqual((m.formality, m.initiative, m.extra), (55, 70, "Investigativa e curiosa."))
        self.assertEqual(persona.reset(other, "claude").preset, "miwa")

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
