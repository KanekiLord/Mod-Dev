"""Knowledge engine (spec 01/08): properties, update instead of duplicate, divergence, backups, stale proposals,
queue without vault, revalidation report, and retrieval by another assistant with link and version."""
from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kaguya.vault.index import VaultIndex  # noqa: E402
from kaguya.vault.knowledge import context_meta, parse_frontmatter, review, set_property  # noqa: E402
from kaguya.vault.outbox import Outbox  # noqa: E402

URL = "https://docs.minecraftforge.net/en/1.20.x/concepts/registries/"
NOTE = """---
tipo: pesquisa
fonte_url: https://docs.minecraftforge.net/en/1.20.x/concepts/registries/
coletado_em: 2026-10-01
status: validado
confianca: alta
versao_contexto: "Forge 1.20.1"
---

# Registro de entidades no Forge

Use DeferredRegister para registrar EntityType no construtor do mod e chame register no barramento do mod.
"""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.vault = self.root / "Segundo Cérebro"
        (self.vault / ".obsidian").mkdir(parents=True)
        (self.vault / "conhecimento").mkdir()
        self.note = self.vault / "conhecimento" / "registro-forge.md"
        self.note.write_text(NOTE, encoding="utf-8")
        (self.vault / "tasks").mkdir()
        (self.vault / "tasks" / "todo.md").write_text("- [ ] nada", encoding="utf-8")
        self.idx = VaultIndex(self.vault, self.root / "home")
        self.idx.update()
        self.ob = Outbox(self.vault, self.root / "home" / "outbox", self.idx, self.root / "home" / "backups")


class Proposals(Base):
    def test_note_saved_with_bom_can_be_updated_and_keeps_its_format(self):
        self.note.write_bytes(b"\xef\xbb\xbf" + NOTE.encode("utf-8"))     # as some Windows editors save
        self.idx.update()
        p = self.ob.stage("pesquisa", "Registro de entidades", "Em 1.20.1 o RegisterEvent também funciona.",
                          source_url=URL, version="Forge 1.20.1", found_by="Kaguya (Codex)")
        self.assertFalse(self.ob.drafts()[0]["stale"])
        done = self.ob.approve([p.name])
        self.assertEqual(len(done), 1, self.ob.last_error)                   # used to say "mudou" forever
        raw = self.note.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))                  # BOM kept
        self.assertIn("RegisterEvent também funciona", raw.decode("utf-8-sig"))

    def test_windows_line_breaks_are_kept_never_doubled(self):
        self.note.write_bytes(NOTE.replace("\n", "\r\n").encode("utf-8"))   # a note saved on Windows
        self.idx.update()
        p = self.ob.stage("pesquisa", "Registro de entidades", "Em 1.20.1 o RegisterEvent também funciona.",
                          source_url=URL, version="Forge 1.20.1", found_by="Kaguya (Codex)")
        self.assertEqual(len(self.ob.approve([p.name])), 1, self.ob.last_error)
        raw = self.note.read_bytes()
        self.assertNotIn(b"\r\r\n", raw)                                  # it used to double every line
        self.assertNotIn(b"\n\n\n", raw)
        self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"))              # every break stays \r\n
        self.assertTrue(raw.startswith(NOTE.replace("\n", "\r\n").encode("utf-8").rstrip(b"\r\n")))

    def test_invalid_bytes_are_never_rewritten_and_the_reason_is_shown(self):
        p = self.ob.stage("pesquisa", "Registro de entidades", "Outra informação.", source_url=URL,
                          version="Forge 1.20.1", found_by="Kaguya (Codex)")
        self.note.write_bytes(NOTE.encode("utf-8") + b"\xff\xfe lixo")      # changed + not UTF-8
        before = self.note.read_bytes()
        self.assertEqual(self.ob.approve([p.name]), [])
        self.assertIn("mudou", self.ob.last_error)
        self.assertEqual(self.note.read_bytes(), before)

    def test_new_note_has_the_spec_properties(self):
        p = self.ob.stage("aprendizado", "Clones usam EntityJoinLevelEvent", "Para spawnar clones, escute "
                          "EntityJoinLevelEvent e cancele duplicatas.", project="NarutoCD", source_url="https://x.org/a",
                          version="Forge 1.20.1", found_by="Miwa (Claude Code)", theme="entidades")
        self.assertEqual(self.ob.last_status, "novo")
        fm = parse_frontmatter(p.read_text(encoding="utf-8"))
        for k, v in {"tipo": "aprendizado", "projeto": "NarutoCD", "fonte_url": "https://x.org/a",
                     "status": "em_revisao", "confianca": "a_verificar", "versao_contexto": "Forge 1.20.1",
                     "encontrado_por": "Miwa (Claude Code)", "tema": "entidades"}.items():
            self.assertEqual(fm[k], v, k)
        self.assertEqual(fm["coletado_em"], date.today().isoformat())
        done = self.ob.approve([p.name])
        self.assertTrue(done[0].is_file())

    def test_same_source_becomes_an_update_with_backup_never_a_duplicate(self):
        before = self.note.read_text(encoding="utf-8")
        p = self.ob.stage("pesquisa", "Registro de entidades", "Em 1.20.1 o RegisterEvent também funciona para "
                          "registros dinâmicos.", source_url=URL, version="Forge 1.20.1", found_by="Kaguya (Codex)")
        self.assertEqual(self.ob.last_status, "atualizacao")
        d = self.ob.drafts()[0]
        self.assertEqual((d["kind"], d["relative"], d["stale"]), ("atualizacao", "conhecimento/registro-forge.md", False))
        self.assertIn("+Em 1.20.1 o RegisterEvent", d["diff"])
        done = self.ob.approve([p.name])
        self.assertEqual([d.resolve() for d in done], [self.note.resolve()])   # Windows: RUNNER~1 vs runneradmin
        after = self.note.read_text(encoding="utf-8")
        self.assertTrue(after.startswith(before.rstrip("\n")))                  # nothing removed or rewritten
        self.assertIn("## Atualização", after)
        self.assertIn("Kaguya (Codex)", after)
        backups = list((self.root / "home" / "backups").rglob("registro-forge.md.*.md"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), before)
        self.assertEqual(len(list((self.vault / "conhecimento").glob("*.md"))), 1)   # no duplicate note

    def test_exact_repeat_is_not_staged(self):
        self.ob.stage("pesquisa", "Registro", "Use DeferredRegister para registrar EntityType no construtor do mod e "
                      "chame register no barramento do mod.", source_url=URL)
        self.assertEqual(self.ob.last_status, "duplicado")
        self.assertEqual(self.ob.drafts(), [])

    def test_mostly_known_content_without_source_is_an_update(self):
        self.ob.stage("aprendizado", "Registrar entidades", "Use DeferredRegister para registrar EntityType no "
                      "construtor do mod; chame register no barramento do mod (eventBus).")
        self.assertEqual(self.ob.last_status, "atualizacao")

    def test_different_version_is_a_divergence_not_a_replacement(self):
        p = self.ob.stage("pesquisa", "Registro de entidades", "Em 1.7.10 se usa EntityRegistry.registerModEntity "
                          "no init.", source_url=URL, version="Forge 1.7.10")
        self.assertEqual(self.ob.last_status, "divergencia")
        self.ob.approve([p.name])
        after = self.note.read_text(encoding="utf-8")
        self.assertIn("Divergência", after)
        self.assertIn("**Forge 1.20.1**", after)
        self.assertIn("**Forge 1.7.10**", after)
        self.assertIn("Use DeferredRegister", after)                             # the old knowledge stays

    def test_note_changed_after_the_proposal_is_never_overwritten(self):
        p = self.ob.stage("pesquisa", "x", "Dica nova sobre registros dinâmicos.", source_url=URL)
        self.note.write_text(NOTE + "\nNota editada pelo usuário no Obsidian.\n", encoding="utf-8")
        self.assertTrue(self.ob.drafts()[0]["stale"])
        self.assertEqual(self.ob.approve([p.name]), [])
        self.assertIn("mudou depois da proposta", self.ob.last_error)
        self.assertNotIn("Dica nova", self.note.read_text(encoding="utf-8"))

    def test_queue_works_without_vault_and_is_approved_later(self):
        staging = self.root / "home" / "outbox"
        offline = Outbox(None, staging, None)
        p = offline.stage("erro", "NPE no ClonePower", "NPE quando o dono do clone sai do mundo.")
        self.assertEqual(offline.approve([p.name]), [])
        self.assertIn("Conecte", offline.last_error)
        online = Outbox(self.vault, staging, self.idx)
        self.assertEqual([d["title"] for d in online.drafts()], ["NPE no ClonePower"])
        self.assertTrue(online.approve([p.name])[0].is_file())


class Versions(unittest.TestCase):
    def test_versions_are_detected_from_learnings(self):
        from kaguya.vault.knowledge import detect_version
        self.assertEqual(detect_version("No Forge 1.20.1 use DeferredRegister"), "Forge 1.20.1")
        self.assertEqual(detect_version("GeckoLib 4.4.2 mudou o renderer"), "GeckoLib 4.4.2")
        self.assertEqual(detect_version("sem versão aqui"), "")


class Review(Base):
    def test_report_and_revalidation_only_touch_the_status(self):
        old = self.vault / "conhecimento" / "velha.md"
        old.write_text("---\ntipo: pesquisa\ncoletado_em: 2025-01-10\nfonte_url: https://x\nversao_contexto: Forge 1.18\n"
                       "---\n# Shaders antigos\nVeja [[Nota Que Nao Existe]] e [[registro-forge]].\n", encoding="utf-8")
        (self.vault / "conhecimento" / "sem-fonte.md").write_text("---\ntipo: aprendizado\n---\n# Registro de entidades no Forge\n"
                                                                  "texto", encoding="utf-8")
        self.idx.update()
        rep = review(self.idx, max_age_days=180, today=date(2026, 11, 25))
        self.assertEqual([o["path"] for o in rep["antigas"]], ["conhecimento/velha.md"])
        self.assertEqual(rep["links_quebrados"], [{"path": "conhecimento/velha.md", "link": "Nota Que Nao Existe"}])
        self.assertIn("conhecimento/sem-fonte.md", rep["sem_fonte"])
        self.assertTrue(any(len(d) == 2 for d in rep["duplicadas"]))
        before = old.read_text(encoding="utf-8")
        p = self.ob.propose_revalidation("conhecimento/velha.md", "sem validação desde 2025-01-10")
        self.ob.approve([p.name])
        after = old.read_text(encoding="utf-8")
        self.assertEqual(after, set_property(before, "status", "necessita_revalidacao"))
        self.assertEqual(after.replace("status: necessita_revalidacao\n", ""), before)
        self.idx.update()
        self.assertIn("conhecimento/velha.md", review(self.idx, today=date(2026, 11, 25))["a_revalidar"])
        self.assertIn("PRECISA SER REVALIDADA", context_meta(after))


class AcrossAssistants(Base):
    def test_kaguya_records_and_miwa_retrieves_with_link_and_version_in_another_session(self):
        from kaguya.messages import Intent
        from kaguya.orchestrator.engine import Engine
        from kaguya.store import Store
        from tests.helpers import fake_env, git_init, make_fake_clis
        p = self.ob.stage("pesquisa", "Animações GeckoLib 4.4", "GeckoLib 4.4 exige registrar o renderer em "
                          "EntityRenderersEvent.RegisterRenderers.", source_url="https://geckolib.com/docs/4.4",
                          version="GeckoLib 4.4", found_by="Kaguya (Codex)")
        self.ob.approve([p.name])                                               # user approved Kaguya's finding
        proj = self.root / "NarutoCD"
        git_init(proj)
        make_fake_clis(self.root / "bin")
        store = Store(self.root / "home2" / "studio.sqlite3")                    # a different session/database
        store.set_global_vault(self.vault) if hasattr(store, "set_global_vault") else None
        pid = store.add_project("NarutoCD", proj, self.vault)
        eng = Engine(store, home=self.root / "home2", env=fake_env(self.root / "bin"))
        mem = eng.memory_for(pid, "como registrar o renderer do GeckoLib")
        self.assertIn("conhecimento/kaguya-studio/", mem)                       # cites the note path
        self.assertIn("versão GeckoLib 4.4", mem)
        self.assertIn("fonte https://geckolib.com/docs/4.4", mem)
        self.assertIn("status em revisao", mem)
        self.assertIn("EntityRenderersEvent", mem)


if __name__ == "__main__":
    unittest.main()
