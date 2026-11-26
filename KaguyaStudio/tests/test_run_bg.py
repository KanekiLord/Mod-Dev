"""run_bg must deliver errors to the handler on the GUI thread (the real setup: bridge made on the GUI thread).
Before 26/11/2026 every background error was lost (NameError in the handler): buttons stayed on
"Transcrevendo…", the Live on "Preparando…"."""
from pathlib import Path
import sys
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 necessário")
class RunBg(unittest.TestCase):
    def test_error_and_result_reach_the_gui_thread(self):
        app = QApplication.instance() or QApplication([])
        from kaguya.ui.common import bridge, run_bg
        bridge()                                    # created on the GUI thread, as the app does
        main = threading.current_thread()
        got = []

        def boom():
            raise RuntimeError("falhou de verdade")
        run_bg(boom, None, lambda e, tb: got.append(("erro", str(e), "RuntimeError" in tb,
                                                     threading.current_thread() is main)))
        run_bg(lambda: 42, lambda r: got.append(("ok", r, True, threading.current_thread() is main)))
        end = time.time() + 5
        while time.time() < end and len(got) < 2:
            app.processEvents()
            time.sleep(0.02)
        self.assertIn(("erro", "falhou de verdade", True, True), got)
        self.assertIn(("ok", 42, True, True), got)


if __name__ == "__main__":
    unittest.main()
