"""Restore points for autonomous mode, with real Git."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kaguya import checkpoint  # noqa: E402
from tests.helpers import git_init  # noqa: E402


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


@unittest.skipUnless(shutil.which("git"), "git necessário")
class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "Mod Ação"
        git_init(self.repo)
        (self.repo / ".gitignore").write_text("build/\n", encoding="utf-8")
        (self.repo / "A.java").write_text("class A {}\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "base")

    def test_undo_restores_everything_and_keeps_user_state(self):
        r = self.repo
        # user state before the task: an uncommitted edit, a staged new file, an untracked file, ignored build
        (r / "A.java").write_text("class A { int x; }\n", encoding="utf-8")
        (r / "Staged.java").write_text("class S {}\n", encoding="utf-8")
        git(r, "add", "Staged.java")
        (r / "notas.txt").write_text("rascunho\n", encoding="utf-8")
        (r / "build").mkdir()
        (r / "build" / "out.jar").write_text("jar", encoding="utf-8")
        status_before = git(r, "status", "--porcelain")
        head_before = git(r, "rev-parse", "HEAD").strip()

        cp = checkpoint.create(r, "tarefa-7")
        self.assertEqual(git(r, "status", "--porcelain"), status_before)  # creating changes nothing
        self.assertEqual(checkpoint.from_text(checkpoint.to_text(cp)), cp)

        # the "agent": edits, deletes, creates, even commits
        (r / "A.java").write_text("class A { broken\n", encoding="utf-8")
        (r / "notas.txt").unlink()
        (r / "src").mkdir()
        (r / "src" / "Novo.java").write_text("class Novo {}\n", encoding="utf-8")
        git(r, "add", "-A")
        git(r, "commit", "-qm", "agente")
        (r / "build" / "out.jar").write_text("jar2", encoding="utf-8")

        changed = checkpoint.changes_since(r, cp)
        self.assertIn("A.java", changed)
        self.assertIn("src/Novo.java", changed)
        self.assertIn("notas.txt", changed)
        self.assertNotIn("build/out.jar", changed)

        checkpoint.restore(r, cp)
        self.assertEqual(git(r, "rev-parse", "HEAD").strip(), head_before)
        self.assertEqual((r / "A.java").read_text(encoding="utf-8"), "class A { int x; }\n")
        self.assertEqual((r / "notas.txt").read_text(encoding="utf-8"), "rascunho\n")
        self.assertFalse((r / "src" / "Novo.java").exists())
        self.assertEqual(git(r, "status", "--porcelain"), status_before)  # staged file still staged
        self.assertEqual((r / "build" / "out.jar").read_text(encoding="utf-8"), "jar2")  # ignored files untouched
        self.assertEqual(checkpoint.changes_since(r, cp), [])
        checkpoint.drop(r, cp)
        self.assertEqual(git(r, "for-each-ref", checkpoint.PREFIX), "")

    def test_repository_without_commits(self):
        r = Path(self.tmp.name) / "vazio"
        r.mkdir()
        git(r, "init", "-q")
        (r / "a.txt").write_text("1", encoding="utf-8")
        cp = checkpoint.create(r, "t1")
        (r / "a.txt").write_text("2", encoding="utf-8")
        (r / "b.txt").write_text("novo", encoding="utf-8")
        checkpoint.restore(r, cp)
        self.assertEqual((r / "a.txt").read_text(encoding="utf-8"), "1")
        self.assertFalse((r / "b.txt").exists())


if __name__ == "__main__":
    unittest.main()
