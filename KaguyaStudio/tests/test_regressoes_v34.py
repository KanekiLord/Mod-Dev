"""Regression tests: each test first demonstrates the defect in the V3.4 code (kept in
``legacy_v3_4/``) and then checks the V4 behaviour. They use fake CLIs that reproduce what
was observed on the real Codex/Claude binaries (see docs/AUDITORIA.md)."""
import importlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
LEGACY = ROOT / "legacy_v3_4"

from tests.helpers import make_fake_clis, fake_env, calls, git_init  # noqa: E402
from kaguya.cli.commands import RunOptions, build_command  # noqa: E402
from kaguya.cli.discovery import Capabilities, diagnose, READY  # noqa: E402
from kaguya.cli.runner import run_agent  # noqa: E402
from kaguya.env import child_env  # noqa: E402
from kaguya.paths import check_project_folder  # noqa: E402
from kaguya.store import Store  # noqa: E402


def legacy():
    sys.path.insert(0, str(LEGACY))
    try:
        core = importlib.import_module("core")
        runtime = importlib.import_module("runtime")
    finally:
        sys.path.remove(str(LEGACY))
    return core, runtime


@unittest.skipUnless(shutil.which("git"), "git necessário")
class RegressionV34(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.exe = make_fake_clis(self.bin)
        self.project = self.root / "Projetos Ç" / "NarutoCD"
        self.project.mkdir(parents=True)
        self.old_env = dict(os.environ)
        self.addCleanup(self._restore)

    def _restore(self):
        os.environ.clear()
        os.environ.update(self.old_env)

    def _use_fake_env(self, **extra):
        env = fake_env(self.bin, **extra)
        os.environ.clear()
        os.environ.update(env)

    # ---------------------------------------------------------------- Codex
    def test_codex_outside_git_failed_in_v34_and_works_in_v4(self):
        self._use_fake_env()
        core, runtime = legacy()
        code, output = runtime.run_cli("codex", self.project, "olá", False, False, lambda _: None,
                                       self.root / "v34.log", verify_login=False)
        self.assertEqual(code, 1)
        self.assertIn("Not inside a trusted directory", output)
        result = run_agent("codex", self.exe["codex"], Capabilities(), self.project, "olá",
                           RunOptions(in_git=False), lambda e: None)
        self.assertTrue(result.ok, result.failure_reason())
        self.assertIn("--skip-git-repo-check", calls(self.bin)[-1]["args"])

    def test_codex_exit_zero_with_errors_was_reported_as_success(self):
        self._use_fake_env(FAKE_CODEX_FAIL="1")
        git_init(self.project)
        core, runtime = legacy()
        code, _ = runtime.run_process(runtime._resolved(core.plan_command("codex", False, False)), self.project, "x",
                                      lambda _: None)
        self.assertEqual(code, 0)  # V3.4 would complete the task as 'executed'
        result = run_agent("codex", self.exe["codex"], Capabilities(), self.project, "x", RunOptions(), lambda e: None)
        self.assertFalse(result.ok)
        self.assertIn("401", result.failure_reason())

    # --------------------------------------------------------------- Claude
    def test_claude_positional_after_variadic_option(self):
        self._use_fake_env()
        core, runtime = legacy()
        captured = {}
        orig = runtime.run_process
        runtime.run_process = lambda cmd, *a, **k: captured.setdefault("cmd", cmd) and (0, "")
        try:
            runtime.run_cli("claude", self.project, "tarefa", False, False, lambda _: None, self.root / "l",
                            verify_login=False)
        finally:
            runtime.run_process = orig
        cmd = captured["cmd"]
        idx = cmd.index("--disallowedTools")
        self.assertGreater(len(cmd), idx + 2, "V3.4 colocava texto depois da opção variádica")
        self.assertIn("plan", cmd)  # plan mode: headless run could only plan
        new = build_command("claude", "claude", Capabilities(), RunOptions())
        variadic = [i for i, a in enumerate(new) if a in ("--allowedTools", "--disallowedTools", "--add-dir")]
        for i in variadic:
            nxt = new[i + 2] if i + 2 < len(new) else "--"
            self.assertTrue(nxt.startswith("-"), f"argumento solto após {new[i]}: {nxt}")
        self.assertNotIn("plan", new)
        self.assertIn("dontAsk", new)

    def test_write_mode_can_run_tests_only_with_permission(self):
        with_cmds = build_command("claude", "claude", Capabilities(), RunOptions(write=True, commands=True))
        allowed = with_cmds[with_cmds.index("--allowedTools") + 1]
        self.assertIn("Bash", allowed)
        without = build_command("claude", "claude", Capabilities(), RunOptions(write=True))
        self.assertNotIn("Bash", without[without.index("--allowedTools") + 1])
        self.assertIn("Bash", without[without.index("--disallowedTools") + 1])

    # -------------------------------------------------------- folder linking
    def test_project_could_not_be_saved_without_vault(self):
        core, _ = legacy()
        old_store = core.Store(self.root / "v34.sqlite")
        with self.assertRaises(ValueError):
            old_store.add_project("Naruto", self.project, self.root / "vault-inexistente")
        store = Store(self.root / "v4.sqlite")
        pid = store.add_project("Naruto", self.project)
        self.assertIsNone(store.effective_vault(pid))
        vault = self.root / "Segundo Cérebro"
        vault.mkdir()
        store.set_global_vault(str(vault))
        self.assertEqual(store.effective_vault(pid), str(vault.resolve()))

    def test_relinking_was_silently_ignored(self):
        core, _ = legacy()
        v1, v2 = self.root / "v1", self.root / "v2"
        v1.mkdir(); v2.mkdir()
        old = core.Store(self.root / "v34.sqlite")
        pid = old.add_project("A", self.project, v1)
        old.add_project("A", self.project, v2)
        self.assertEqual(old.project(pid)["vault"], str(v1.resolve()))  # stuck with the old vault
        store = Store(self.root / "v4.sqlite")
        pid = store.add_project("A", self.project, v1)
        store.add_project("A", self.project, v2)
        self.assertEqual(store.project(pid)["vault"], str(v2.resolve()))

    def test_git_subfolder_was_refused(self):
        git_init(self.root / "repo")
        sub = self.root / "repo" / "mods" / "naruto"
        sub.mkdir(parents=True)
        _, runtime = legacy()
        with self.assertRaises(ValueError):
            runtime.check_project_writable(sub)
        check = check_project_folder(str(sub))
        self.assertTrue(check.ok)
        self.assertEqual(Path(check.git_root), (self.root / "repo").resolve())
        self.assertFalse(check.is_git_root)

    # -------------------------------------------------------------- env
    def test_unrelated_cloud_variable_blocked_every_agent(self):
        core, _ = legacy()
        with self.assertRaises(ValueError):
            core.safe_env({"PATH": "x", "AWS_ACCESS_KEY_ID": "abc"})
        env, removed = child_env({"PATH": "x", "ANTHROPIC_API_KEY": "secret", "CLAUDE_CODE_USE_BEDROCK": "1"})
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        self.assertNotIn("CLAUDE_CODE_USE_BEDROCK", env)
        self.assertEqual(removed, ["ANTHROPIC_API_KEY", "CLAUDE_CODE_USE_BEDROCK"])

    def test_diagnosis_reports_ready_with_versions(self):
        env = fake_env(self.bin)
        for target in ("codex", "claude"):
            diag, caps = diagnose(target, str(self.project), env=env)
            self.assertEqual(diag.state, READY, diag.report())
            self.assertTrue(diag.version)
            self.assertTrue(caps.flags)


if __name__ == "__main__":
    unittest.main()
