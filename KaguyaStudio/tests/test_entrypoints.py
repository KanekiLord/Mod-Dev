"""Every flag the Studio uses to start a helper process must exist in BOTH entry points: the .exe uses
run_kaguya.py, ``python -m kaguya`` uses kaguya/__main__.py (a missing one opened the whole app instead)."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class EntryPoints(unittest.TestCase):
    def test_helper_flags_are_routed_in_both(self):
        used = set()
        for p in (ROOT / "kaguya").rglob("*.py"):
            used |= set(re.findall(r'sys\.executable, "(--[a-z-]+)"', p.read_text(encoding="utf-8")))
        self.assertIn("--baixar-modelo", used)
        for entry in (ROOT / "run_kaguya.py", ROOT / "kaguya" / "__main__.py"):
            text = entry.read_text(encoding="utf-8")
            for flag in used:
                self.assertIn(f'"{flag}"', text, f"{flag} não é tratado em {entry.name}")


if __name__ == "__main__":
    unittest.main()
