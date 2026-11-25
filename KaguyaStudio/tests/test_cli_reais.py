"""Integration with the REAL official CLIs, *without* any account (runs in CI on Windows).

Enabled only with KAGUYA_TEST_REAL_CLIS=1 and when ``codex``/``claude`` are installed. It
checks what can be verified honestly without a subscription: discovery of the npm launchers,
versions, capabilities, the 'not logged in' diagnosis, stdin/JSON streaming of a headless run
(which must fail with an authentication error — and be reported as failure, not success) and
the Codex app-server limits query. Runs with real accounts are a separate, manual step.
"""
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kaguya.cli.commands import RunOptions  # noqa: E402
from kaguya.cli.discovery import NOT_AUTHENTICATED, READY, diagnose  # noqa: E402
from kaguya.cli.runner import run_agent  # noqa: E402
from kaguya.usage import read_codex_limits  # noqa: E402

ENABLED = os.environ.get("KAGUYA_TEST_REAL_CLIS") == "1"
# A logged-in CLI would spend a (tiny) part of the subscription: only with explicit opt-in.
ALLOW_SPEND = os.environ.get("KAGUYA_TEST_REAL_RUN") == "1"


def clean_env():
    env = dict(os.environ)
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "CODEX_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"):
        env.pop(k, None)
    return env


@unittest.skipUnless(ENABLED and shutil.which("codex"), "Codex real não habilitado")
class RealCodex(unittest.TestCase):
    def test_discovery_and_not_logged_in(self):
        d, caps = diagnose("codex", env=clean_env())
        print("\n" + d.report())
        self.assertEqual(d.state, NOT_AUTHENTICATED)
        self.assertTrue(d.version.startswith("codex-cli"))
        for flag in ("--json", "--skip-git-repo-check", "--sandbox"):
            self.assertIn(flag, caps.flags)

    def test_headless_run_outside_git_reaches_auth_and_is_reported_as_failure(self):
        d, caps = diagnose("codex", env=clean_env())
        with tempfile.TemporaryDirectory() as tmp:
            events = []
            r = run_agent("codex", d.executable, caps, Path(tmp), "diga ok", RunOptions(in_git=False),
                          events.append, env=clean_env(), timeout_s=240)
        print(f"\nexit={r.exit_code} ok={r.ok} motivo={r.failure_reason()[:300]}")
        self.assertFalse(r.ok)
        self.assertNotIn("trusted directory", r.failure_reason())  # V3.4 defect is gone
        self.assertTrue(r.session_id, "thread.started deveria ter sido lido do JSONL")

    def test_limits_query_without_login_is_unavailable_not_invented(self):
        d, _ = diagnose("codex", env=clean_env())
        snap = read_codex_limits(d.executable, env=clean_env())
        print(f"\nlimites: available={snap.available} msg={snap.message}")
        self.assertFalse(snap.available)
        self.assertEqual(snap.windows, [])


@unittest.skipUnless(ENABLED and shutil.which("claude"), "Claude real não habilitado")
class RealClaude(unittest.TestCase):
    def test_discovery_reports_login_state(self):
        d, caps = diagnose("claude", env=clean_env())
        print("\n" + d.report())
        self.assertIn(d.state, (NOT_AUTHENTICATED, READY))
        for flag in ("--output-format", "--permission-mode", "--allowedTools", "--resume"):
            self.assertIn(flag, caps.flags)

    def test_headless_stream_json(self):
        d, caps = diagnose("claude", env=clean_env())
        if d.state == READY and not ALLOW_SPEND:
            self.skipTest("Claude logado: execução real só com KAGUYA_TEST_REAL_RUN=1 (consome cota mínima)")
        with tempfile.TemporaryDirectory() as tmp:
            r = run_agent("claude", d.executable, caps, Path(tmp), "Responda apenas: ok", RunOptions(in_git=False),
                          lambda e: None, env=clean_env(), timeout_s=240)
        print(f"\nexit={r.exit_code} ok={r.ok} sessão={r.session_id} resposta={r.final_text[:80]!r} "
              f"motivo={r.failure_reason()[:300]}")
        if d.state == READY:
            self.assertTrue(r.ok, r.failure_reason())
            self.assertTrue(r.session_id)
        else:
            self.assertFalse(r.ok)
            self.assertTrue(r.failure_reason())


if __name__ == "__main__":
    unittest.main()
