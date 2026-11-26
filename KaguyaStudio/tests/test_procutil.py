"""The runner that replaced subprocess.run for every external CLI call: it must never hang."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kaguya import procutil  # noqa: E402

# a "launcher" whose child keeps stdout open long after the launcher itself is gone — what
# claude.cmd → node does on Windows, the reason subprocess.run(timeout=…) waited forever there
GRANDCHILD = ("import subprocess, sys, time;"
              "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']);"
              "print('ok', flush=True); time.sleep(60)")


class Runner(unittest.TestCase):
    def test_normal_output_input_and_returncode(self):
        p = procutil.run([sys.executable, "-c", "import sys; print(sys.stdin.read().upper()); sys.exit(3)"],
                         input="olá", capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertEqual((p.returncode, p.stdout.strip()), (3, "OLÁ"))

    def test_timeout_kills_the_tree_and_returns_quickly(self):
        t0 = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            procutil.run([sys.executable, "-c", GRANDCHILD], capture_output=True, text=True, timeout=1.5)
        self.assertLess(time.monotonic() - t0, 8)

    def test_background_child_holding_the_output_does_not_block(self):
        # like gradlew starting the Gradle daemon: the command ends, a child keeps the output handle
        t0 = time.monotonic()
        p = procutil.run([sys.executable, "-c", "import subprocess, sys; subprocess.Popen([sys.executable, '-c', "
                          "'import time; time.sleep(30)']); print('BUILD SUCCESSFUL')"],
                         capture_output=True, text=True, timeout=20)
        self.assertLess(time.monotonic() - t0, 8)
        self.assertEqual((p.returncode, p.stdout.strip()), (0, "BUILD SUCCESSFUL"))

    def test_cancel_stops_a_running_command(self):
        cancel = threading.Event()
        threading.Timer(0.5, cancel.set).start()
        t0 = time.monotonic()
        with self.assertRaises(InterruptedError):
            procutil.run([sys.executable, "-c", GRANDCHILD], capture_output=True, text=True, timeout=60, cancel=cancel)
        self.assertLess(time.monotonic() - t0, 8)

    def test_diagnosis_of_a_hanging_cli_ends_with_a_clear_message(self):
        from kaguya.cli import discovery
        with tempfile.TemporaryDirectory() as d:
            exe = Path(d) / ("claude.cmd" if os.name == "nt" else "claude")
            if os.name == "nt":
                exe.write_text(f'@"{sys.executable}" -c "{GRANDCHILD}"\r\n')
            else:
                exe.write_text(f"#!/bin/sh\nexec '{sys.executable}' -c \"{GRANDCHILD}\"\n")
                exe.chmod(0o755)
            t0 = time.monotonic()
            diag, _caps = discovery.diagnose("claude", d, str(exe), timeout=1.5)
            self.assertLess(time.monotonic() - t0, 10)
            self.assertIn("não respondeu", " ".join(diag.details))


if __name__ == "__main__":
    unittest.main()
