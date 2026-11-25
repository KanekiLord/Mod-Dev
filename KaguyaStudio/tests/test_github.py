"""GitHub integration with a fake `gh` and REAL git (local bare remotes behind github.com URLs)."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kaguya import github  # noqa: E402
from kaguya.gitsetup import init_repository  # noqa: E402
from tests.helpers import fake_env, make_fake_clis  # noqa: E402


@unittest.skipUnless(shutil.which("git"), "git necessário")
class GitHubIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.bin = root / "bin"
        self.exe = make_fake_clis(self.bin)
        (root / "remotes").mkdir()
        self.env = fake_env(self.bin, FAKE_GH_REMOTES=str(root / "remotes"))
        self.p = root / "Mods Desenvolvimento" / "- Kodachi"
        (self.p / "src").mkdir(parents=True)
        (self.p / "src" / "Kodachi.java").write_text("class Kodachi {}", encoding="utf-8")
        self.assertTrue(init_repository(self.p, name="Teste", email="t@example.com").ok)

    def test_diagnose_states_without_token(self):
        st = github.diagnose(env=self.env)
        self.assertTrue(st.ready, st.details)
        self.assertEqual(st.login, "kaguya-teste")
        st = github.diagnose(env=fake_env(self.bin, FAKE_GH_AUTH="none"))
        self.assertEqual(st.state, "nao_autenticado")
        self.assertTrue(st.fixes)
        st = github.diagnose(override=str(Path(self.tmp.name) / "nao-existe" / "gh.exe"), env=self.env)
        self.assertEqual(st.state, "nao_instalado")
        self.assertIn("winget", st.fixes[0])
        self.assertNotIn("--show-token", " ".join(map(str, Path(self.bin / "calls.jsonl").read_text().split())))

    def test_publish_commit_push_pull_and_pr(self):
        name = github.suggest_repo_name(self.p)
        self.assertEqual(name, "Kodachi")
        res = github.publish(self.p, self.exe["gh"], name, private=True, env=self.env)
        self.assertTrue(res.ok, res.message)
        rs = github.repo_status(self.p, env=self.env)
        self.assertEqual(rs.github_repo, "kaguya-teste/Kodachi")
        self.assertEqual((rs.ahead, rs.behind), (0, 0))
        again = github.publish(self.p, self.exe["gh"], name, env=self.env)
        self.assertFalse(again.ok)  # never re-publishes over an existing remote
        (self.p / "src" / "Novo.java").write_text("class Novo {}", encoding="utf-8")
        self.assertEqual(github.repo_status(self.p, env=self.env).changed, 1)
        self.assertTrue(github.commit_all(self.p, "Adiciona Novo", env=self.env).ok)
        self.assertEqual(github.repo_status(self.p, env=self.env).ahead, 1)
        self.assertTrue(github.push(self.p, env=self.env).ok)
        self.assertEqual(github.repo_status(self.p, env=self.env).ahead, 0)
        self.assertTrue(github.pull(self.p, env=self.env).ok)
        subprocess.run(["git", "-C", str(self.p), "checkout", "-q", "-b", "kaguya/missoes"], check=True)
        pr = github.create_pr(self.p, self.exe["gh"], env=self.env)
        self.assertTrue(pr.ok, pr.message)
        self.assertIn("/pull/", pr.url)

    def test_pull_refuses_with_uncommitted_changes(self):
        github.publish(self.p, self.exe["gh"], "Kodachi", env=self.env)
        (self.p / "x.txt").write_text("x", encoding="utf-8")
        r = github.pull(self.p, env=self.env)
        self.assertFalse(r.ok)
        self.assertIn("sem commit", r.message)


if __name__ == "__main__":
    unittest.main()
