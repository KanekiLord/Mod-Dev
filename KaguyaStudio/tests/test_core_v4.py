import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kaguya.appdirs import CATALOG  # noqa: E402
from kaguya.cli.discovery import (diagnose, NOT_INSTALLED, NOT_AUTHENTICATED, NO_PERMISSION, find_cli,  # noqa: E402
                                  parse_capabilities)
from kaguya.cli.events import StreamParser  # noqa: E402
from kaguya.env import redact  # noqa: E402
from kaguya.inventory import scan, suggest_agents  # noqa: E402
from kaguya.messages import classify_message  # noqa: E402
from kaguya.paths import check_vault_folder, check_project_folder, normalize_user_path  # noqa: E402
from kaguya.prompts import parse_verdict  # noqa: E402
from kaguya.store import Store  # noqa: E402
from kaguya.usage import claude_snapshot, codex_snapshot_from_response  # noqa: E402
from kaguya.vault.index import VaultIndex  # noqa: E402
from kaguya.vault.outbox import Outbox, extract_learnings  # noqa: E402
from kaguya.vault.todo import parse_todo  # noqa: E402
from tests.helpers import make_fake_clis, fake_env  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)


class PathsAndStore(Base):
    def test_normalize_accepts_quotes_env_and_spaces(self):
        target = self.root / "Segundo Cérebro"
        target.mkdir()
        os.environ["KAGUYA_TEST_DIR"] = str(self.root)
        self.addCleanup(os.environ.pop, "KAGUYA_TEST_DIR")
        p = normalize_user_path(f'"{os.path.join("$KAGUYA_TEST_DIR" if os.name != "nt" else "%KAGUYA_TEST_DIR%", "Segundo Cérebro")}"')
        self.assertEqual(p, target.resolve())
        with self.assertRaises(ValueError):
            normalize_user_path("   ")

    def test_vault_check_specific_messages(self):
        missing = check_vault_folder(str(self.root / "nao existe"))
        self.assertFalse(missing.ok)
        self.assertIn("não existe", missing.problems[0])
        v = self.root / "vault"
        (v / ".obsidian").mkdir(parents=True)
        (v / "sub").mkdir()
        (v / "nota.md").write_text("x", encoding="utf-8")
        ok = check_vault_folder(str(v))
        self.assertTrue(ok.ok and ok.is_obsidian and ok.markdown_sample == 1)
        sub = check_vault_folder(str(v / "sub"))
        self.assertTrue(sub.ok)
        self.assertTrue(any(str(v.resolve()) in h for h in sub.hints))

    def test_project_without_git_is_linkable_read_only(self):
        c = check_project_folder(str(self.root))
        self.assertTrue(c.ok)
        self.assertIsNone(c.git_root)
        self.assertTrue(c.warnings)

    def test_store_edit_unlink_relink_and_persist(self):
        s = Store(self.root / "s.sqlite3")
        a = self.root / "a"; a.mkdir()
        b = self.root / "b"; b.mkdir()
        pid = s.add_project("Alpha", a)
        s.update_project(pid, name="Alpha 2", directory=b, test_command="gradlew test")
        self.assertEqual(s.project(pid)["directory"], str(b.resolve()))
        s.remove_project(pid)
        self.assertEqual(s.projects(), [])
        self.assertEqual(s.add_project("Alpha", b), pid)  # re-linking revives the same project
        s2 = Store(self.root / "s.sqlite3")
        self.assertEqual(s2.project(pid)["test_command"], "gradlew test")

    def test_import_v3_database_read_only(self):
        old = self.root / "v3.sqlite3"
        db = sqlite3.connect(old)
        db.executescript("""CREATE TABLE projects(id INTEGER PRIMARY KEY, name TEXT, directory TEXT, vault TEXT, created_at TEXT);
            CREATE TABLE tasks(id INTEGER PRIMARY KEY, project_id INT, target TEXT, title TEXT, kind TEXT, status TEXT,
            created_at TEXT, allow_write INT, allow_web INT, started_at TEXT, finished_at TEXT, result TEXT);""")
        db.execute("INSERT INTO projects VALUES(1,'Naruto','D:/Projetos/NarutoCD','D:/Segundo Cerebro','x')")
        db.execute("INSERT INTO tasks VALUES(1,1,'codex','HUD','later','parked','x',0,1,NULL,NULL,'')")
        db.execute("INSERT INTO tasks VALUES(2,1,'equipe','rodando','execute','running','x',0,1,NULL,NULL,'')")
        db.commit(); db.close()
        before = old.read_bytes()
        s = Store(self.root / "v4.sqlite3")
        rep = s.import_v3(old)
        self.assertEqual((rep["projects"], rep["tasks"]), (1, 2))
        self.assertTrue(s.global_vault())
        statuses = sorted(t["status"] for t in s.tasks(s.projects()[0]["id"]))
        self.assertEqual(statuses, ["interrupted", "parked"])
        self.assertEqual(old.read_bytes(), before)
        self.assertEqual(s.import_v3(old)["projects"], 0)  # only once


class CliAndEvents(Base):
    def test_diagnosis_states(self):
        b = self.root / "bin"
        make_fake_clis(b)
        d, _ = diagnose("codex", env=fake_env(b, FAKE_CODEX_AUTH="none"))
        self.assertEqual(d.state, NOT_AUTHENTICATED)
        self.assertTrue(d.fixes)
        d, _ = diagnose("codex", env=fake_env(b, FAKE_CODEX_AUTH="apikey"))
        self.assertEqual(d.state, NO_PERMISSION)
        self.assertNotIn("ABCDE", d.report().replace("***ABCDE", ""))
        d, _ = diagnose("claude", env=fake_env(b, FAKE_CLAUDE_AUTH="api_key"))
        self.assertEqual(d.state, NO_PERMISSION)
        d, _ = diagnose("claude", env={"PATH": str(self.root / "vazio"), "HOME": str(self.root),
                                       "USERPROFILE": str(self.root)})
        self.assertEqual(d.state, NOT_INSTALLED)
        self.assertTrue(any("npm" in f for f in d.fixes))

    def test_manual_executable_override(self):
        b = self.root / "bin"
        paths = make_fake_clis(b)
        found, how = find_cli("claude", paths["claude"], env={"PATH": ""})
        self.assertEqual(how, "definido manualmente")
        self.assertIsNone(find_cli("claude", str(self.root / "x.ps1"), env={"PATH": ""})[0])

    def test_capabilities_from_help(self):
        caps = parse_capabilities("1.0", "--output-format <f> stream-json  --permission-mode (choices: dontAsk, plan)")
        self.assertTrue(caps.has("--output-format") and caps.mentions("dontAsk"))

    def test_claude_stream_parsing(self):
        p = StreamParser("claude")
        lines = [{"type": "system", "subtype": "init", "session_id": "s1", "model": "m"},
                 {"type": "assistant", "session_id": "s1", "message": {"content": [
                     {"type": "tool_use", "name": "Edit", "input": {"file_path": "a.java"}},
                     {"type": "text", "text": "feito"}]}},
                 {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed_warning"}},
                 {"type": "result", "subtype": "success", "is_error": False, "result": "feito", "usage": {"input_tokens": 5}}]
        for l in lines:
            p.feed(json.dumps(l))
        r = p.result
        self.assertTrue(r.ok)
        self.assertEqual(r.files_changed, ["a.java"])
        self.assertEqual(r.session_id, "s1")
        self.assertEqual(len(r.rate_limits), 1)

    def test_codex_without_turn_completed_is_not_success(self):
        p = StreamParser("codex")
        p.feed(json.dumps({"type": "thread.started", "thread_id": "t"}))
        p.result.exit_code = 0
        self.assertFalse(p.result.ok)
        self.assertIn("conclusão", p.result.failure_reason())

    def test_redact(self):
        self.assertNotIn("abcdefghijklmnop", redact("token=abcdefghijklmnop sk-ant-abcdefghijklmnopqrst"))


class VaultAndMemory(Base):
    def make_vault(self):
        v = self.root / "Segundo Cérebro"
        (v / ".obsidian").mkdir(parents=True)
        (v / "conhecimento" / "raw").mkdir(parents=True)
        (v / "conhecimento" / "photon.md").write_text("# Photon Shader\nEfeitos de luz. Ver [[Blockbench]] #shader", "utf-8")
        (v / "conhecimento" / "raw" / "blockbench.md").write_text("# Blockbench\nModelagem de roupas", "utf-8")
        (v / "memoria").mkdir()
        (v / "memoria" / "senhas.md").write_text("senha secreta 123", "utf-8")
        (v / ".obsidian" / "workspace.md").write_text("photon", "utf-8")
        return v

    def test_index_incremental_search_and_exclusions(self):
        v = self.make_vault()
        idx = VaultIndex(v, self.root / "home")
        st = idx.update()
        self.assertEqual(st["total"], 2)
        hits = idx.search("efeitos photon")
        self.assertEqual(hits[0].path, "conhecimento/photon.md")
        self.assertIn("Blockbench", hits[0].links)
        self.assertEqual(idx.search("senha secreta"), [])
        self.assertEqual(idx.update()["changed"], 0)  # incremental
        time.sleep(0.01)
        (v / "conhecimento" / "photon.md").write_text("# Photon\natualizado iris", "utf-8")
        os.utime(v / "conhecimento" / "photon.md", (time.time() + 5, time.time() + 5))
        self.assertEqual(idx.update()["changed"], 1)
        self.assertTrue(idx.search("iris"))

    def test_outbox_create_only_and_duplicates(self):
        v = self.make_vault()
        idx = VaultIndex(v, self.root / "home"); idx.update()
        ob = Outbox(v, self.root / "outbox", idx)
        n1 = ob.stage("pesquisa", "Photon Shader", "fonte: https://example.com", evidence="lido em 24/11")
        n2 = ob.stage("pesquisa", "Photon Shader", "fonte: https://example.com", evidence="lido em 24/11")
        self.assertEqual(n1, n2)
        d = ob.drafts()
        self.assertEqual(len(d), 1)
        self.assertIn("conhecimento/photon.md", d[0]["similar"])
        done = ob.approve([n1.name])
        self.assertEqual(len(done), 1)
        self.assertTrue(done[0].is_file())
        self.assertEqual(ob.approve([n1.name]), [])
        self.assertEqual(ob.approve(["../../x.md"]), [])

    def test_extract_learnings(self):
        text = "TRABALHO: x\nAPRENDIZADOS:\n- Forge 1.7.10 usa @EventHandler no mod principal\n- nenhum\nERROS:\n- NPE em Missao.java quando rank nulo\nREFERÊNCIAS:\n- https://docs.minecraftforge.net (24/11/2026)\n"
        items = extract_learnings(text)
        kinds = [k for k, _ in items]
        self.assertIn("aprendizado", kinds)
        self.assertIn("erro", kinds)
        self.assertIn("pesquisa", kinds)

    def test_todo_parser(self):
        items = parse_todo("# Foco\n- [ ] HUD de chakra\n- [x] Missões rank C\n  - [/] sub\n")
        self.assertEqual([i.state for i in items], ["aberto", "feito", "em andamento"])
        self.assertEqual(items[0].section, "Foco")


class InventoryUsageMessages(Base):
    def test_inventory_reconciles_with_catalog_without_secrets(self):
        proj = self.root / "proj"
        (proj / ".claude" / "agents").mkdir(parents=True)
        (proj / ".claude" / "agents" / "narutocd-revisor.md").write_text(
            "---\nname: narutocd-revisor\ndescription: Revisa\nmodel: sonnet\n---\nx", "utf-8")
        (proj / ".claude" / "agents" / "meu-agente.md").write_text("---\nname: meu-agente\n---\n", "utf-8")
        (proj / ".mcp.json").write_text(json.dumps({"mcpServers": {"obsidian": {"command": "x", "env": {"TOKEN": "segredo"}}}}), "utf-8")
        inv = scan(proj, None, CATALOG, home=self.root / "home")
        self.assertEqual(inv.catalog_total, 72)
        self.assertEqual(inv.catalog_found, ["narutocd-revisor"])
        self.assertIn("meu-agente", inv.not_in_catalog)
        self.assertEqual(len(inv.catalog_missing), 71)
        self.assertNotIn("segredo", json.dumps(inv.to_dict()))
        self.assertEqual(suggest_agents(inv, ["revisar"]), ["narutocd-revisor"])

    def test_codex_limits_parsing(self):
        snap = codex_snapshot_from_response({"rateLimits": {
            "primary": {"usedPercent": 42, "windowDurationMins": 300, "resetsAt": int(time.time()) + 3600},
            "secondary": {"usedPercent": 10, "windowDurationMins": 10080, "resetsAt": int(time.time()) + 86400},
            "planType": "plus"}})
        self.assertTrue(snap.available)
        self.assertEqual([w.name for w in snap.windows], ["Janela de 5 horas", "Semanal (7 dias)"])
        self.assertEqual(snap.windows[0].remaining_percent, 58)
        empty = codex_snapshot_from_response({})
        self.assertFalse(empty.available)

    def test_claude_unavailable_without_official_data(self):
        snap = claude_snapshot(None)
        self.assertFalse(snap.available)
        self.assertFalse(snap.windows)

    def test_verdict_parsing_never_auto_approves(self):
        self.assertEqual(parse_verdict("parece bom")["veredito"], "pendente")
        self.assertEqual(parse_verdict('```json\n{"veredito":"reprovado","problemas":["a"]}\n```')["problemas"], ["a"])
        self.assertEqual(parse_verdict("VEREDITO: APROVADO")["veredito"], "aprovado")

    def test_message_intents(self):
        self.assertEqual(classify_message("DEPOIS: hud").kind, "later")
        i = classify_message("@claude: AGORA: pare e revise")
        self.assertEqual((i.target, i.interrupt), ("claude", True))
        p = classify_message("PARALELO:\n@codex: a\n- @claude: b")
        self.assertEqual(p.subtasks, [("codex", "a"), ("claude", "b")])
        with self.assertRaises(ValueError):
            classify_message("PARALELO: só uma coisa")


if __name__ == "__main__":
    unittest.main()
