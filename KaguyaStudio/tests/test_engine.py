"""Engine tests with fake CLIs: single turns, Team feedback loop, limits, parallel worktrees,
DEPOIS/IDEIA never interrupting, learnings captured into the outbox."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.helpers import make_fake_clis, fake_env, calls, git_init  # noqa: E402
from kaguya.messages import classify_message  # noqa: E402
from kaguya.orchestrator.engine import Engine  # noqa: E402
from kaguya.store import Store  # noqa: E402


@unittest.skipUnless(shutil.which("git"), "git necessário")
class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        make_fake_clis(self.bin)
        self.project = self.root / "D Projetos" / "Naruto CD"
        git_init(self.project)
        self.vault = self.root / "Segundo Cérebro"
        (self.vault / ".obsidian").mkdir(parents=True)
        (self.vault / "conhecimento").mkdir()
        (self.vault / "conhecimento" / "forge-eventos.md").write_text(
            "# Eventos Forge\nRegistrar handlers de missão no FMLInitializationEvent.\n", encoding="utf-8")
        self.store = Store(self.root / "home" / "studio.sqlite3")
        self.pid = self.store.add_project("Naruto CD", self.project)
        self.store.set_global_vault(self.vault)
        self.events = []
        self.verdicts = self.root / "verdicts.txt"

    def engine(self, **env):
        return Engine(self.store, self.events.append, home=self.root / "home",
                      env=fake_env(self.bin, FAKE_VERDICTS=str(self.verdicts), **env))

    def run_task(self, eng, text, **perms):
        tid = eng.submit(self.pid, classify_message(text, "equipe"), **perms)
        eng.wait(self.pid, 60)
        return self.store.get_task(tid)

    def test_single_codex_turn_streams_and_keeps_session(self):
        eng = self.engine()
        task = self.run_task(eng, "@codex: explique a classe de missões")
        self.assertEqual(task["status"], "executed", task["result"])
        kinds = {e["kind"] for e in self.events if e["type"] == "agent_event"}
        self.assertIn("text", kinds)
        self.assertEqual(self.store.session(self.pid, "codex"), "01a20fdf-0796-7d02-b7ef-05a8bbec3a05")
        prompt_call = [c for c in calls(self.bin) if c["cli"] == "codex" and "exec" in c["args"] and "--help" not in c["args"]][-1]
        self.assertFalse(prompt_call["has_api_key"])
        # second message resumes the same conversation
        self.run_task(eng, "@codex: e agora resuma")
        last = [c for c in calls(self.bin) if c["cli"] == "codex" and "exec" in c["args"] and "--help" not in c["args"]][-1]
        self.assertIn("resume", last["args"])

    def test_memory_from_vault_is_sent_as_data(self):
        eng = self.engine()
        self.run_task(eng, "@claude: como registrar eventos forge de missão?")
        logs = list((self.root / "home" / "logs").rglob("claude.log"))
        self.assertTrue(logs)
        msgs = [e["message"] for e in self.store.events(self.store.tasks(self.pid)[0]["id"])]
        self.assertTrue(any("Resposta do Claude" in m for m in msgs))

    def test_team_feedback_loop_until_approved(self):
        self.verdicts.write_text("reprovado\naprovado\n", encoding="utf-8")
        eng = self.engine(FAKE_CODEX_WRITE="1")
        task = self.run_task(eng, "@equipe: implementar missões rank S", write=True)
        self.assertEqual(task["status"], "approved", task["result"])
        stages = [e["stage"] for e in self.events if e["type"] == "stage"]
        self.assertEqual(stages[:4], ["implementacao", "verificacao", "revisao", "correcao"])
        self.assertIn("final", stages)
        codex_calls = [c for c in calls(self.bin) if c["cli"] == "codex" and "exec" in c["args"] and "--help" not in c["args"]]
        self.assertEqual(len(codex_calls), 2)  # implement + one fix
        self.assertIn("resume", codex_calls[1]["args"])  # fix continues the same thread
        claude_calls = [c for c in calls(self.bin) if c["cli"] == "claude" and "-p" in c["args"]]
        self.assertEqual(len(claude_calls), 2)
        for c in claude_calls:  # reviewer is read-only
            self.assertIn("dontAsk", c["args"])
        self.assertIn("testes não executados", task["result"])

    def test_team_never_loops_forever(self):
        self.verdicts.write_text("reprovado\nreprovado\nreprovado\nreprovado\n", encoding="utf-8")
        self.store.set_setting("team.max_cycles", 2)
        task = self.run_task(self.engine(), "@equipe: tarefa difícil")
        self.assertEqual(task["status"], "rejected")
        self.assertEqual(len([c for c in calls(self.bin) if c["cli"] == "claude" and "-p" in c["args"]]), 2)

    def test_failure_with_exit_zero_is_error_and_pauses_queue(self):
        eng = self.engine(FAKE_CODEX_FAIL="1")
        tid1 = eng.submit(self.pid, classify_message("@codex: primeira", "equipe"))
        tid2 = eng.submit(self.pid, classify_message("@codex: segunda", "equipe"))
        eng.wait(self.pid, 60)
        self.assertEqual(self.store.get_task(tid1)["status"], "error")
        self.assertIn("401", self.store.get_task(tid1)["result"])
        self.assertEqual(self.store.get_task(tid2)["status"], "queued")  # not burned

    def test_limit_reached_blocks_next_tasks(self):
        eng = self.engine(FAKE_CLAUDE_LIMIT="1")
        task = self.run_task(eng, "@claude: algo")
        self.assertEqual(task["status"], "blocked_limit")
        snap = self.store.latest_usage("claude")
        self.assertTrue(snap["payload"]["blocked"])

    def test_later_and_idea_do_not_run_or_interrupt(self):
        eng = self.engine()
        tid = eng.submit(self.pid, classify_message("DEPOIS: criar HUD de chakra", "equipe"))
        idea = eng.submit(self.pid, classify_message("IDEIA: modo sharingan", "equipe"))
        self.assertFalse(eng.is_running(self.pid))
        self.assertEqual(self.store.get_task(tid)["status"], "parked")
        self.assertEqual(calls(self.bin), [])
        drafts = eng.outbox(self.pid).drafts()
        self.assertTrue(any(d["kind"] == "ideia" for d in drafts))
        # persisted after "restart"
        store2 = Store(self.root / "home" / "studio.sqlite3")
        self.assertEqual(store2.get_task(tid)["status"], "parked")
        self.assertEqual(store2.get_task(idea)["kind"], "idea")

    def test_learnings_become_outbox_drafts_not_vault_writes(self):
        eng = self.engine()
        before = sorted(p.as_posix() for p in self.vault.rglob("*"))
        self.run_task(eng, "@claude: revise o registro de eventos")
        drafts = eng.outbox(self.pid).drafts()
        self.assertTrue(any("FMLInitializationEvent" in d["body"] for d in drafts))
        self.assertEqual(before, sorted(p.as_posix() for p in self.vault.rglob("*")))  # vault untouched

    def test_write_requires_git(self):
        plain = self.root / "sem git"
        plain.mkdir()
        pid = self.store.add_project("Sem Git", plain)
        eng = self.engine()
        tid = eng.submit(pid, classify_message("@codex: edite", "equipe"), write=True)
        eng.wait(pid, 30)
        t = self.store.get_task(tid)
        self.assertEqual(t["status"], "error")
        self.assertIn("Git", t["result"])
        # read-only work in a folder without Git works (V3.4 failed here)
        tid = eng.submit(pid, classify_message("@codex: só analise", "equipe"))
        eng.wait(pid, 30)
        self.assertEqual(self.store.get_task(tid)["status"], "executed", self.store.get_task(tid)["result"])

    def test_parallel_uses_isolated_worktrees(self):
        eng = self.engine(FAKE_CODEX_WRITE="1")
        text = "PARALELO:\n@codex: criar classe Missao\n@claude: documentar API de missões"
        task = self.run_task(eng, text)
        self.assertEqual(task["status"], "pending_review", task["result"])
        wt_events = [json.loads(e["message"]) for e in self.store.events(task["id"]) if e["kind"] == "worktree"]
        self.assertEqual(len(wt_events), 2)
        for info in wt_events:
            self.assertNotEqual(Path(info["path"]).resolve(), self.project.resolve())
        self.assertFalse((self.project / "feito_pelo_codex.txt").exists())  # main tree untouched

    def test_stale_session_falls_back_to_new_conversation(self):
        self.store.set_session(self.pid, "claude", "3f1c2b6e-1111-4222-8333-944455556666")
        task = self.run_task(self.engine(FAKE_CLAUDE_STALE="1"), "@claude: continue")
        # fake keeps failing when --resume is used, the fresh retry has no --resume
        self.assertEqual(task["status"], "executed", task["result"])
        last = [c for c in calls(self.bin) if c["cli"] == "claude" and "-p" in c["args"]][-1]
        self.assertNotIn("--resume", last["args"])


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(shutil.which("git"), "git necessário")
class AutonomyTests(unittest.TestCase):
    setUp = EngineTests.setUp
    engine = EngineTests.engine
    run_task = EngineTests.run_task

    def test_autonomous_task_runs_without_asking_and_can_be_undone(self):
        (self.project / "Missao.java").write_text("class Missao {}\n", encoding="utf-8")  # user's uncommitted work
        eng = self.engine(FAKE_CODEX_WRITE="1")
        task = self.run_task(eng, "@codex: implementar recompensa em ryō", autonomous=True)
        self.assertEqual(task["status"], "executed", task["result"])
        self.assertTrue(task["autonomous"] and task["allow_write"] and task["allow_commands"] and task["run_tests"])
        self.assertTrue(task["checkpoint"].startswith("refs/kaguya/checkpoints/tarefa-"))
        call = [c for c in calls(self.bin) if c["cli"] == "codex" and "exec" in c["args"] and "--help" not in c["args"]][-1]
        self.assertIn("sandbox_workspace_write.network_access=true", call["args"])  # Gradle can download deps
        self.assertIn("workspace-write", call["args"])
        self.assertTrue((self.project / "feito_pelo_codex.txt").exists())
        self.assertEqual(eng.task_changes(task["id"]), ["feito_pelo_codex.txt"])
        changed = eng.undo_task(task["id"])
        self.assertEqual(changed, ["feito_pelo_codex.txt"])
        self.assertFalse((self.project / "feito_pelo_codex.txt").exists())
        self.assertEqual((self.project / "Missao.java").read_text(encoding="utf-8"), "class Missao {}\n")
        self.assertEqual(self.store.get_task(task["id"])["checkpoint"], "")
        with self.assertRaises(ValueError):
            eng.undo_task(task["id"])

    def test_autonomous_claude_keeps_dangerous_commands_blocked(self):
        eng = self.engine()
        self.run_task(eng, "@claude: rodar os testes do mod", autonomous=True)
        call = [c for c in calls(self.bin) if c["cli"] == "claude" and "-p" in c["args"]][-1]
        args = call["args"]
        allowed = args[args.index("--allowedTools") + 1]
        denied = args[args.index("--disallowedTools") + 1]
        self.assertIn("Bash", allowed.split(","))
        self.assertIn("Edit", allowed.split(","))
        self.assertIn("Bash(git push:*)", denied)
        self.assertIn("PowerShell(git push:*)", denied)
        self.assertIn("acceptEdits", args)
        self.assertNotIn("bypassPermissions", args)
        prompt_logs = list((self.root / "home" / "logs").rglob("claude.log"))
        self.assertTrue(prompt_logs)

    def test_autonomous_requires_git(self):
        plain = self.root / "sem git"
        plain.mkdir()
        pid = self.store.add_project("Sem Git", plain)
        eng = self.engine()
        tid = eng.submit(pid, classify_message("@codex: algo", "equipe"), autonomous=True)
        eng.wait(pid, 30)
        t = self.store.get_task(tid)
        self.assertNotEqual(t["status"], "executed")
        self.assertIn("Git", t["result"])

    def test_normal_tasks_have_no_autonomy(self):
        eng = self.engine()
        task = self.run_task(eng, "@claude: explique")
        self.assertFalse(task["autonomous"])
        self.assertEqual(task["checkpoint"], "")
        call = [c for c in calls(self.bin) if c["cli"] == "claude" and "-p" in c["args"]][-1]
        self.assertFalse(any("git push" in a for a in call["args"]))
