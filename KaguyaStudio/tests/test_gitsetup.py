import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kaguya.gitsetup import init_repository  # noqa: E402
from kaguya.paths import check_project_folder  # noqa: E402


@unittest.skipUnless(shutil.which("git"), "git necessário")
class GitSetup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.p = Path(self.tmp.name) / "Mods Desenvolvimento" / "- Kodachi"
        (self.p / "src").mkdir(parents=True)
        (self.p / "src" / "Kodachi.java").write_text("class Kodachi {}", encoding="utf-8")
        (self.p / "build").mkdir()
        (self.p / "build" / "lixo.jar").write_text("x", encoding="utf-8")
        (self.p / "run" / "saves").mkdir(parents=True)

    def test_creates_repo_gitignore_and_first_commit(self):
        self.assertIsNone(check_project_folder(str(self.p)).git_root)
        res = init_repository(self.p, name="Teste", email="teste@example.com")
        self.assertTrue(res.ok, res.error)
        self.assertEqual(res.error, "")
        self.assertTrue(check_project_folder(str(self.p)).is_git_root)
        files = subprocess.run(["git", "ls-files"], cwd=self.p, capture_output=True, text=True).stdout
        self.assertIn("src/Kodachi.java", files)
        self.assertNotIn("build/", files)
        self.assertIn(".gitignore", files)

    def test_never_overwrites_existing_gitignore_or_repo(self):
        (self.p / ".gitignore").write_text("meu-ignore\n", encoding="utf-8")
        res = init_repository(self.p, first_commit=False)
        self.assertTrue(res.ok)
        self.assertEqual((self.p / ".gitignore").read_text(encoding="utf-8"), "meu-ignore\n")
        again = init_repository(self.p)
        self.assertFalse(again.ok)
        self.assertIn("já tem", again.error)


if __name__ == "__main__":
    unittest.main()
