"""Computer use: MCP server safety rules with the fake backend, stdio protocol, engine wiring."""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kaguya.desktop import control  # noqa: E402
from kaguya.desktop.backend import FakeBackend, parse_keys  # noqa: E402
from kaguya.desktop.server import Desktop, Refused, handle  # noqa: E402


class DesktopRules(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name) / "desktop"
        self.log = Path(self.tmp.name) / "acoes.jsonl"
        self.fake = FakeBackend(str(self.log))

    def desk(self, window="Minecraft", **kw):
        return Desktop(self.fake, self.base, window=window, **kw)

    def actions(self):
        if not self.log.exists():
            return []
        return [json.loads(l) for l in self.log.read_text(encoding="utf-8").splitlines()]

    def test_window_restriction_maps_and_refuses_outside(self):
        d = self.desk()
        content = d.call("screenshot", {})
        self.assertEqual(content[0]["type"], "image")
        png = base64.b64decode(content[0]["data"])
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertIn("Minecraft", content[1]["text"])
        self.assertIn("800x600", content[1]["text"])  # only the window (fake rect 100,50 → 900,650)
        d.call("click", {"x": 10, "y": 20})
        clicks = [a for a in self.actions() if a["action"] == "click"]
        self.assertEqual((clicks[-1]["x"], clicks[-1]["y"]), (110, 70))  # mapped to the screen
        self.assertTrue(any(a["action"] == "focus" for a in self.actions()))  # brought to the front first
        with self.assertRaises(Refused):
            d.call("click", {"x": 850, "y": 10})  # outside the window
        with self.assertRaises(Refused):
            d.call("focus_window", {"title": "banco"})

    def test_missing_window_is_reported(self):
        d = self.desk(window="Photoshop")
        with self.assertRaises(Refused) as ctx:
            d.call("screenshot", {})
        self.assertIn("não está aberta", str(ctx.exception))

    def test_whole_screen_downscaled(self):
        d = self.desk(window="")
        text = d.call("screenshot", {})[1]["text"]
        self.assertIn("960x540", text)  # 1920 wide > 1280 → every 2nd pixel
        d.call("click", {"x": 100, "y": 100})
        click = [a for a in self.actions() if a["action"] == "click"][-1]
        self.assertEqual((click["x"], click["y"]), (200, 200))

    def test_stop_flag_failsafe_and_budget(self):
        d = self.desk()
        d.call("click", {"x": 1, "y": 1})
        control.request_stop(self.base, "botão Parar")
        with self.assertRaises(Refused) as ctx:
            d.call("type_text", {"text": "oi"})
        self.assertIn("parou", str(ctx.exception))
        control.reset(self.base)
        self.fake.pos = (0, 0)  # user pushed the mouse into the corner
        with self.assertRaises(Refused):
            d.call("press_keys", {"keys": "w"})
        self.assertIn("failsafe", control.stop_reason(self.base))
        control.reset(self.base)
        self.fake.pos = (400, 300)
        small = self.desk(max_actions=2)
        small.call("press_keys", {"keys": "e"})
        small.call("press_keys", {"keys": "e"})
        with self.assertRaises(Refused):
            small.call("press_keys", {"keys": "e"})

    def test_system_shortcuts_refused_and_keys_parsed(self):
        d = self.desk()
        with self.assertRaises(Refused):
            d.call("press_keys", {"keys": "ctrl+alt+delete"})
        self.assertEqual(parse_keys("Control + Return"), ["ctrl", "enter"])
        d.call("press_keys", {"keys": "w", "hold_seconds": 2})
        self.assertEqual(self.actions()[-1], {"action": "hold", "keys": ["w"], "seconds": 2.0})
        d.call("type_text", {"text": "/give @p diamond"})
        entries, _ = control.read_activity(self.base)
        self.assertEqual([e["action"] for e in entries][-2:], ["keys", "type"])

    def test_jsonrpc_handle(self):
        state = {}
        init = handle(lambda: self.desk(), {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                            "params": {"protocolVersion": "2025-03-26"}}, state)
        self.assertEqual(init["result"]["protocolVersion"], "2025-03-26")
        self.assertIsNone(handle(lambda: self.desk(), {"jsonrpc": "2.0", "method": "notifications/initialized"}, state))
        tools = handle(lambda: self.desk(), {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, state)["result"]["tools"]
        self.assertIn("screenshot", [t["name"] for t in tools])
        err = handle(lambda: self.desk(), {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                           "params": {"name": "click", "arguments": {"x": 5000, "y": 5}}}, state)
        self.assertTrue(err["result"]["isError"])


class DesktopStdio(unittest.TestCase):
    def test_server_over_stdio_like_the_clis(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, KAGUYA_DESKTOP_BACKEND="fake", KAGUYA_DESKTOP_DIR=tmp,
                       KAGUYA_DESKTOP_WINDOW="Minecraft", KAGUYA_DESKTOP_FAKE_LOG=str(Path(tmp) / "f.jsonl"))
            msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "press_keys", "arguments": {"keys": "f3"}}}]
            p = subprocess.run([sys.executable, str(ROOT / "run_kaguya.py"), "--mcp-desktop"],
                               input="\n".join(json.dumps(m) for m in msgs) + "\n", capture_output=True, text=True,
                               env=env, timeout=60, cwd=str(ROOT))
            replies = [json.loads(l) for l in p.stdout.splitlines()]
            self.assertEqual([r["id"] for r in replies], [1, 2], p.stderr)
            self.assertFalse(replies[1]["result"]["isError"], replies[1])
            self.assertIn("f3", (Path(tmp) / "f.jsonl").read_text(encoding="utf-8"))


@unittest.skipUnless(shutil.which("git"), "git necessário")
class DesktopEngine(unittest.TestCase):
    def setUp(self):
        from tests.helpers import fake_env, git_init, make_fake_clis
        from kaguya.store import Store
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.bin = root / "bin"
        make_fake_clis(self.bin)
        self.project = root / "Mod"
        git_init(self.project)
        self.store = Store(root / "home" / "s.db")
        self.pid = self.store.add_project("Mod", self.project)
        self.events = []
        from kaguya.orchestrator.engine import Engine
        self.engine = Engine(self.store, self.events.append, home=root / "home",
                             env=fake_env(self.bin, KAGUYA_DESKTOP_BACKEND="fake"))

    def run_task(self, text, **kw):
        from kaguya.messages import classify_message
        tid = self.engine.submit(self.pid, classify_message(text, "equipe"), **kw)
        self.engine.wait(self.pid, 60)
        return self.store.get_task(tid)

    def test_claude_gets_only_the_desktop_server(self):
        from tests.helpers import calls
        t = self.run_task("@claude: abra o mundo de teste e veja se o HUD aparece", desktop=True)
        self.assertTrue(t["desktop"])
        call = [c for c in calls(self.bin) if c["cli"] == "claude" and "-p" in c["args"]][-1]["args"]
        cfg = Path(call[call.index("--mcp-config") + 1])
        server = json.loads(cfg.read_text(encoding="utf-8"))["mcpServers"]["kaguya_desktop"]
        self.assertEqual(server["env"]["KAGUYA_DESKTOP_WINDOW"], "Minecraft")
        self.assertEqual(server["env"]["KAGUYA_DESKTOP_BACKEND"], "fake")
        self.assertIn("--strict-mcp-config", call)  # the user's own MCP servers are not loaded
        self.assertIn("mcp__kaguya_desktop", call[call.index("--allowedTools") + 1])
        self.assertNotIn("mcp__*", call[call.index("--disallowedTools") + 1])
        log = (self.engine.home / "logs" / f"projeto-{self.pid}" / f"tarefa-{t['id']}" / "claude.log").read_text(encoding="utf-8")
        self.assertIn("ferramentas ok=[True, True]", log)  # the server really ran from that config
        evs = "\n".join(e["message"] for e in self.store.events(t["id"]))
        self.assertIn("Uso do computador: 2 ação(ões)", evs)  # screenshot + click recorded for the user
        flags = [e for e in self.events if e["type"] == "desktop"]
        self.assertEqual([f["active"] for f in flags], [True, False])

    def test_codex_desktop_config_and_normal_tasks_untouched(self):
        from tests.helpers import calls
        self.run_task("@codex: teste o jogo", desktop=True)
        call = [c for c in calls(self.bin) if c["cli"] == "codex" and "exec" in c["args"] and "--help" not in c["args"]][-1]["args"]
        joined = " ".join(call)
        self.assertIn("mcp_servers.kaguya_desktop.command=", joined)
        self.assertIn("default_tools_approval_mode='approve'", joined)
        self.run_task("@claude: explique")
        last = [c for c in calls(self.bin) if c["cli"] == "claude" and "-p" in c["args"]][-1]["args"]
        self.assertNotIn("--mcp-config", last)
        self.assertIn("mcp__*", last[last.index("--disallowedTools") + 1])


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(sys.platform == "win32", "somente Windows")
class WindowsBackendReal(unittest.TestCase):
    """Runs on the Windows CI runner: the real Windows API, no mocks."""

    def test_capture_cursor_windows_and_keys(self):
        from kaguya.desktop.backend import Rect, WindowsBackend
        b = WindowsBackend()
        scr = b.screen()
        self.assertGreater(scr.width, 100)
        png, w, h, step = b.capture(Rect(scr.left, scr.top, scr.left + 300, scr.top + 200))
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertEqual((w, h, step), (300, 200, 1))
        b.move(scr.left + 123, scr.top + 77)
        self.assertEqual(b.cursor(), (scr.left + 123, scr.top + 77))
        self.assertIsInstance(b.windows(), list)
        b.keys(["shift"])  # harmless key through SendInput
        self.assertIsInstance(b.foreground(), int)
