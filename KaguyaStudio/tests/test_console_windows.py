"""Visible-console command line for executables under paths with spaces (regression of the
GitHub login failure: '"\\"C:\\Program Files\\GitHub CLI\\gh.EXE\\""' não é reconhecido)."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kaguya.cli.discovery import console_command_line  # noqa: E402


class ConsoleLine(unittest.TestCase):
    def test_no_backslash_escaped_quotes(self):
        line = console_command_line([r"C:\Program Files\GitHub CLI\gh.exe", "auth", "login", "--web"])
        self.assertEqual(line, r'cmd.exe /k ""C:\Program Files\GitHub CLI\gh.exe" auth login --web"')
        self.assertNotIn('\\"', line)

    @unittest.skipUnless(os.name == "nt", "execução real só no Windows")
    def test_runs_executable_with_spaces_on_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "Program Files" / "GitHub CLI"
            d.mkdir(parents=True)
            exe = d / "gh.cmd"
            exe.write_text("@echo FUNCIONOU %*\r\n", encoding="utf-8")
            out = subprocess.run(console_command_line([str(exe), "auth", "login"], keep_open=False),
                                 capture_output=True, text=True, timeout=30)
            self.assertIn("FUNCIONOU auth login", out.stdout, out.stderr)


if __name__ == "__main__":
    unittest.main()
