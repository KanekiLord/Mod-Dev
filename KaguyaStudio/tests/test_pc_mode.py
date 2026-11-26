"""'Meu computador' (personal assistant): helpers, server tools, engine routing."""
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kaguya.desktop import assistant, control  # noqa: E402
from kaguya.desktop.backend import FakeBackend  # noqa: E402
from kaguya.desktop.server import Desktop, Refused, handle  # noqa: E402


class Helpers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name) / "desktop"
        self.log = Path(self.tmp.name) / "fake.jsonl"
        patch = mock.patch.dict(os.environ, {"KAGUYA_DESKTOP_BACKEND": "fake", "KAGUYA_DESKTOP_DIR": str(self.base),
                                             "KAGUYA_DESKTOP_FAKE_LOG": str(self.log), "KAGUYA_DESKTOP_PC": "1",
                                             "KAGUYA_DESKTOP_AGENT": "claude"})
        patch.start()
        self.addCleanup(patch.stop)

    def answer_next(self, yes: bool):
        def run():
            for _ in range(200):
                reqs = assistant.pending_requests(self.base)
                if reqs:
                    self.asked.append(reqs[0])
                    assistant.answer_request(self.base, reqs[0]["id"], yes)
                    return
                time.sleep(0.02)
        self.asked = []
        t = threading.Thread(target=run)
        t.start()
        return t

    def test_when_parsing_alarms_and_events(self):
        now = datetime(2026, 11, 25, 15, 0)
        self.assertEqual(assistant.parse_when("16:30", now), datetime(2026, 11, 25, 16, 30))
        self.assertEqual(assistant.parse_when("9h", now), datetime(2026, 11, 26, 9, 0))  # already passed → tomorrow
        self.assertEqual(assistant.parse_when("2026-12-01 08:15", now), datetime(2026, 12, 1, 8, 15))
        with self.assertRaises(ValueError):
            assistant.parse_when("depois do almoço")
        a = assistant.add_alarm(self.base, minutes=0.001, text="tirar o bolo do forno")
        b = assistant.add_alarm(self.base, when="2099-01-01 10:00", text="futuro")
        time.sleep(0.15)
        due = assistant.due_alarms(self.base)
        self.assertEqual([d["id"] for d in due], [a["id"]])
        self.assertEqual(due[0]["agent"], "claude")
        self.assertEqual([x["id"] for x in assistant.load_alarms(self.base)], [b["id"]])
        ics = assistant.create_event(self.base, "Buscar mamãe, trabalho", "2026-11-26 18:00").read_text(encoding="utf-8")
        self.assertIn("DTSTART:20261126T180000", ics)
        self.assertIn("DTEND:20261126T190000", ics)
        self.assertIn("SUMMARY:Buscar mamãe\\, trabalho", ics)

    def test_confirmation_roundtrip_and_programs_need_it(self):
        t = self.answer_next(True)
        self.assertTrue(assistant.ask_user(self.base, "Enviar para Mamãe: oi", timeout=5))
        t.join()
        self.assertEqual(self.asked[0]["action"], "Enviar para Mamãe: oi")
        self.assertEqual(assistant.pending_requests(self.base), [])  # cleaned up
        self.assertFalse(assistant.ask_user(self.base, "ninguém responde", timeout=0.3))  # no answer = no
        exe = Path(self.tmp.name) / "Batata Game 2.exe"
        exe.write_text("x", encoding="utf-8")
        t = self.answer_next(False)
        with self.assertRaises(ValueError):
            assistant.open_target(str(exe))
        t.join()
        self.assertIn("Executar o programa", self.asked[0]["action"])
        folder = Path(self.tmp.name)
        self.assertEqual(assistant.open_target(f'"{folder}"'), str(folder))
        self.assertIn("open", self.log.read_text(encoding="utf-8"))
        self.assertEqual(assistant.open_target("https://youtube.com"), "https://youtube.com")
        with self.assertRaises(ValueError):
            assistant.open_target(str(folder / "nao existe.txt"))

    def test_server_pc_tools(self):
        d = Desktop(FakeBackend(str(self.log)), self.base, window="")
        names = [t["name"] for t in handle(lambda: d, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, {})["result"]["tools"]]
        for n in ("open_path", "open_app", "set_timer", "set_reminder", "create_event", "confirm"):
            self.assertIn(n, names)
        d.call("open_app", {"name": "WhatsApp"})
        acts = [json.loads(l) for l in self.log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([x["action"] for x in acts[-3:]], ["keys", "type", "keys"])
        self.assertEqual(acts[-2]["text"], "WhatsApp")
        with self.assertRaises((Refused, ValueError)):
            d.call("open_app", {"name": "regedit"})
        self.assertIn("Timer criado", d.call("set_timer", {"minutes": 5, "label": "macarrão"})[0]["text"])
        t = self.answer_next(False)
        out = d.call("confirm", {"action": "Enviar no WhatsApp para Mamãe: \"que horas te busco?\""})[0]["text"]
        t.join()
        self.assertIn("NÃO confirmou", out)
        entries, _ = control.read_activity(self.base)
        self.assertIn("NÃO: Enviar no WhatsApp", entries[-1]["detail"])

    def test_pc_tools_hidden_outside_pc_mode(self):
        with mock.patch.dict(os.environ, {"KAGUYA_DESKTOP_PC": ""}):
            d = Desktop(FakeBackend(str(self.log)), self.base, window="Minecraft")
            names = [t["name"] for t in handle(lambda: d, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, {})["result"]["tools"]]
            self.assertNotIn("open_app", names)
            with self.assertRaises(Refused):
                d.call("open_path", {"target": "C:\\\\"})


@unittest.skipUnless(shutil.which("git"), "git necessário")
class PcEngine(unittest.TestCase):
    def setUp(self):
        from tests.helpers import fake_env, make_fake_clis
        from kaguya.store import Store
        from kaguya.orchestrator.engine import Engine
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.bin = root / "bin"
        make_fake_clis(self.bin)
        self.home = root / "Usuario"
        (self.home / "Downloads").mkdir(parents=True)
        self.store = Store(root / "dados" / "s.db")
        with mock.patch("pathlib.Path.home", return_value=self.home):
            self.pid = self.store.pc_project()
        self.engine = Engine(self.store, home=root / "dados", env=fake_env(self.bin, KAGUYA_DESKTOP_BACKEND="fake"))

    def test_pc_task_without_git_full_access_and_safety_rules(self):
        from kaguya.messages import classify_message
        from tests.helpers import calls
        self.assertTrue(self.store.is_pc(self.pid))
        self.assertEqual(self.store.pc_project(), self.pid)  # created once
        tid = self.engine.submit(self.pid, classify_message("Miwa, abra o arquivo Batata Game 2 nos Downloads e analise", "equipe"))
        self.engine.wait(self.pid, 60)
        t = self.store.get_task(tid)
        self.assertEqual(t["status"], "executed", t["result"])  # no "needs Git" block
        self.assertTrue(t["allow_write"] and t["allow_commands"] and t["desktop"])
        args = [c for c in calls(self.bin) if c["cli"] == "claude" and "-p" in c["args"]][-1]["args"]
        self.assertEqual(Path([c for c in calls(self.bin) if c["cli"] == "claude" and "-p" in c["args"]][-1]["cwd"]).resolve(),
                         self.home.resolve())
        denied = args[args.index("--disallowedTools") + 1]
        self.assertIn("Bash(rm -rf:*)", denied)
        self.assertIn("PowerShell(Remove-Item -Recurse:*)", denied)
        self.assertIn("Bash(git push:*)", denied)
        cfg = json.loads(Path(args[args.index("--mcp-config") + 1]).read_text(encoding="utf-8"))
        env = cfg["mcpServers"]["kaguya_desktop"]["env"]
        self.assertEqual((env["KAGUYA_DESKTOP_PC"], env["KAGUYA_DESKTOP_WINDOW"], env["KAGUYA_DESKTOP_AGENT"]),
                         ("1", "", "claude"))
        from kaguya.prompts import task_prompt
        prompt = task_prompt("x", project="Meu computador", write=True, pc=True, desktop="")
        self.assertIn("MODO MEU COMPUTADOR", prompt)
        self.assertIn("confirm antes de: enviar qualquer mensagem", prompt)
        self.assertNotIn("USO DO COMPUTADOR (", prompt)  # PC rules replace the project's screen rules


if __name__ == "__main__":
    unittest.main()


class Security(unittest.TestCase):
    """Second review (26/11/2026): the assistant must not be able to answer its own confirmation, open things that
    run code without asking, nor type into another window."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name) / "desktop"
        self.log = Path(self.tmp.name) / "fake.jsonl"

    def _studio(self, answer: str):
        """A stand-in for the Studio's confirmation bridge: checks the token, answers on the same connection."""
        import socket
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        seen = []

        def serve():
            conn, _ = srv.accept()
            with conn:
                data = b""
                while b"\n" not in data:
                    data += conn.recv(4096)
                req = json.loads(data.decode())
                seen.append(req)
                ok = req["token"] == "segredo-da-tarefa"
                conn.sendall((json.dumps({"ok": ok, "text": answer if ok else "encerrado"}) + "\n").encode())
            srv.close()
        threading.Thread(target=serve, daemon=True).start()
        return srv.getsockname()[1], seen

    def test_answer_only_comes_from_the_studio_connection(self):
        port, seen = self._studio("sim")
        env = {"KAGUYA_CONFIRM_PORT": str(port), "KAGUYA_CONFIRM_TOKEN": "segredo-da-tarefa",
               "KAGUYA_DESKTOP_DIR": str(self.base)}
        with mock.patch.dict(os.environ, env):
            self.assertTrue(assistant.ask_user(self.base, "Enviar para Mamãe: oi", timeout=5))
        self.assertEqual((seen[0]["tool"], seen[0]["args"]["action"]), ("confirmar", "Enviar para Mamãe: oi"))
        port, _ = self._studio("nao")
        with mock.patch.dict(os.environ, {**env, "KAGUYA_CONFIRM_PORT": str(port)}):
            self.assertFalse(assistant.ask_user(self.base, "Apagar Downloads", timeout=5))

    def test_assistant_writing_sim_to_a_file_gets_nothing(self):
        stop = threading.Event()

        def attacker():          # what an assistant with write access to the user's folder could do
            while not stop.is_set():
                folder = control.control_dir(self.base) / assistant.REQUESTS
                for req in folder.glob("*.json") if folder.exists() else []:
                    (folder / (req.stem + ".resposta")).write_text("sim", encoding="utf-8")
                time.sleep(0.01)
        t = threading.Thread(target=attacker, daemon=True)
        t.start()
        self.addCleanup(stop.set)
        with mock.patch.dict(os.environ, {"KAGUYA_DESKTOP_DIR": str(self.base)}):
            os.environ.pop("KAGUYA_DESKTOP_BACKEND", None)
            os.environ.pop("KAGUYA_CONFIRM_PORT", None)
            self.assertFalse(assistant.ask_user(self.base, "Enviar mensagem", timeout=1))   # no channel → no

    def test_open_path_asks_for_anything_that_can_run_code(self):
        env = {"KAGUYA_DESKTOP_BACKEND": "fake", "KAGUYA_DESKTOP_DIR": str(self.base),
               "KAGUYA_DESKTOP_FAKE_LOG": str(self.log)}
        asked = []
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(assistant, "ask_user", side_effect=lambda b, what, *a: asked.append(what) or False):
            folder = Path(self.tmp.name)
            for name in ("pagina.hta", "painel.cpl", "atalho.url", "script.wsf", "sem_extensao"):
                (folder / name).write_text("x")
                with self.assertRaises(ValueError):
                    assistant.open_target(str(folder / name))
            self.assertEqual(len(asked), 5)
            for uri in ("ms-msdt:/id PCWDiagnostic", "search-ms:query=x", "ms-appinstaller:?source=http://x",
                        "file:///C:/Windows/System32/calc.exe"):
                with self.assertRaises(ValueError):
                    assistant.open_target(uri)
            (folder / "relatorio.pdf").write_text("x")
            assistant.open_target(str(folder / "relatorio.pdf"))            # documents open without asking
            assistant.open_target("https://youtube.com")
            assistant.open_target("ms-settings:sound")
            self.assertEqual(len(asked), 5)

    def test_keys_are_refused_when_windows_keeps_another_window_in_front(self):
        class Stubborn(FakeBackend):
            def focus(self, w):
                return False                                  # Windows focus lock: nothing changes
        env = {"KAGUYA_DESKTOP_BACKEND": "fake", "KAGUYA_DESKTOP_DIR": str(self.base),
               "KAGUYA_DESKTOP_FAKE_LOG": str(self.log)}
        with mock.patch.dict(os.environ, env):
            d = Desktop(Stubborn(str(self.log)), self.base, window="Minecraft")
            with self.assertRaises(Refused):
                d.call("type_text", {"text": "oi"})
        acts = [json.loads(l)["action"] for l in self.log.read_text(encoding="utf-8").splitlines()] \
            if self.log.exists() else []
        self.assertNotIn("type", acts)

    def test_codex_resume_keeps_this_tasks_sandbox(self):
        from kaguya.cli.commands import RunOptions, build_command
        from kaguya.cli.discovery import Capabilities
        cmd = build_command("codex", "codex", Capabilities(), RunOptions(write=False, resume="thread-antiga",
                                                                         in_git=True))
        self.assertIn("sandbox_mode='read-only'", cmd)
        self.assertLess(cmd.index("sandbox_mode='read-only'"), cmd.index("exec"))      # global option


class Alarms(unittest.TestCase):
    def test_two_processes_never_lose_a_reminder(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            base = Path(d) / "desktop"
            root = str(Path(__file__).resolve().parents[1])
            code = ("import sys; sys.path.insert(0, sys.argv[1]); from pathlib import Path; "
                    "from kaguya.desktop import assistant\n"
                    "for i in range(40): assistant.add_alarm(Path(sys.argv[2]), when='2099-01-01 10:00', text=f'p{i}')")
            env = dict(os.environ, KAGUYA_DESKTOP_DIR=str(base))
            proc = subprocess.Popen([sys.executable, "-c", code, root, str(base)], env=env)
            with mock.patch.dict(os.environ, {"KAGUYA_DESKTOP_DIR": str(base)}):
                for i in range(40):                       # the Studio side, at the same time
                    assistant.add_alarm(base, minutes=0.0001, text=f"s{i}")
                    assistant.due_alarms(base)
                proc.wait(60)
                time.sleep(0.05)
                assistant.due_alarms(base)
                left = {a["text"] for a in assistant.load_alarms(base)}
            self.assertEqual(left, {f"p{i}" for i in range(40)})     # every reminder of the other process kept
