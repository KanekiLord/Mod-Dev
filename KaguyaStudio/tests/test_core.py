import json
import tempfile
import unittest
from pathlib import Path

from core import Store, classify_message, Vault, inventory, minimal_context, safe_env, plan_command


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo'; self.repo.mkdir()
        self.vault_path = self.root / 'vault'; self.vault_path.mkdir()
        self.store = Store(self.root/'tasks.sqlite')
        self.pid = self.store.add_project('Naruto', self.repo, self.vault_path)

    def test_classify_future_does_not_execute(self):
        k, t, d = classify_message('DEPOIS: criar HUD', 'equipe')
        self.assertEqual((k,t,d),('later','equipe','criar HUD'))
        self.assertEqual(classify_message('IDEIA: novo jutsu', 'codex')[0],'idea')
        self.assertEqual(classify_message('@Claude: revisar API', 'equipe')[1],'claude')

    def test_queue_is_persistent_and_single_active(self):
        first = self.store.enqueue(self.pid, 'codex', 'fazer 1')
        second = self.store.enqueue(self.pid, 'claude', 'fazer 2')
        a = self.store.claim(self.pid)
        self.assertEqual(a['id'],first)
        self.assertIsNone(self.store.claim(self.pid))
        self.store.complete(first,'done','ok')
        self.assertEqual(self.store.claim(self.pid)['id'],second)
        store2 = Store(self.root/'tasks.sqlite')
        self.assertEqual(store2.get_task(second)['status'],'running')
        store2.recover_interrupted()
        self.assertEqual(store2.get_task(second)['status'],'interrupted')

    def test_later_idea_never_claimed(self):
        self.store.enqueue(self.pid,'codex','IDEIA qualquer','idea')
        self.store.enqueue(self.pid,'codex','DEPOIS qualquer','later')
        self.assertIsNone(self.store.claim(self.pid))

    def test_search_respects_existing_structure_and_source(self):
        d = self.vault_path/'conhecimento';d.mkdir()
        (d/'photon.md').write_text('# Photon\nEfeitos especiais no Minecraft. Versao 1.20.1',encoding='utf-8')
        (d/'outro.md').write_text('anotacao qualquer',encoding='utf-8')
        vault=Vault(self.vault_path,self.root/'staging')
        hits=vault.search('photon efeitos',limit=3)
        self.assertEqual(len(hits),1)
        self.assertEqual(hits[0]['path'],'conhecimento/photon.md')
        self.assertIn('Photon',minimal_context(hits,1200))

    def test_note_staging_and_sync_is_opt_in_new_file_only(self):
        vault=Vault(self.vault_path,self.root/'staging')
        fn=vault.stage('aprendizado','Correção Photon','testado localmente')
        self.assertTrue(fn.is_file())
        self.assertFalse((self.vault_path/'memoria'/'agentes').exists())
        preview=vault.sync_preview()
        self.assertEqual(len(preview),1)
        self.assertFalse((self.vault_path/'memoria'/'agentes').exists())
        synced=vault.sync_approved([fn.name])
        self.assertEqual(len(synced),1)
        self.assertIn('memoria',str(synced[0]))
        self.assertEqual(vault.sync_approved([fn.name]),[])

    def test_staging_blocks_path_traversal(self):
        vault=Vault(self.vault_path,self.root/'staging')
        vault.stage('pesquisa','../foo','teste')
        self.assertEqual(len(vault.sync_preview()),1)
        self.assertEqual(vault.sync_approved(['../../unsafe.md']),[])

    def test_inventory_preserves_existing_agents(self):
        d=self.repo/'.claude'/'agents';d.mkdir(parents=True)
        (d/'especialista.md').write_text('---\nname: especialista\nmodel: sonnet\n---\nTarefa',encoding='utf-8')
        (self.repo/'CLAUDE.md').write_text('Instrucoes existentes',encoding='utf-8')
        res=inventory(self.repo, self.root/'catalogo-inexistente.json')
        self.assertEqual(res['agents_local'],['especialista.md'])
        self.assertEqual((self.repo/'CLAUDE.md').read_text(), 'Instrucoes existentes')

    def test_catalog_contains_72_names(self):
        catalog=Path(__file__).resolve().parent.parent/'catalogo'/'agentes.json'
        entries=json.loads(catalog.read_text(encoding='utf-8'))
        self.assertEqual(len(entries),72)
        self.assertEqual(len({e['nome'] for e in entries}),72)

    def test_api_keys_are_removed_and_paid_provider_blocked(self):
        env=safe_env({'PATH':'abc','OPENAI_API_KEY':'danger','ANTHROPIC_API_KEY':'secret'})
        self.assertNotIn('OPENAI_API_KEY',env)
        self.assertNotIn('ANTHROPIC_API_KEY',env)
        with self.assertRaises(ValueError):safe_env({'CLAUDE_CODE_USE_BEDROCK':'1'})

    def test_plan_commands_do_not_use_paid_api_or_bypass(self):
        c=plan_command('codex',False,True)
        a=plan_command('claude',False,False)
        self.assertIn('exec',c)
        self.assertIn('--sandbox',c)
        self.assertIn('read-only',c)
        self.assertIn('--search',c)
        self.assertIn('-p',a)
        self.assertNotIn('dangerously-skip-permissions',str(a))
        self.assertNotIn('bypassPermissions',str(a))

    def test_staging_duplicate_prevented(self):
        vault=Vault(self.vault_path,self.root/'staging')
        a=vault.stage('pesquisa','Referencia','Fonte: URL')
        b=vault.stage('pesquisa','Referencia','Fonte: URL')
        self.assertEqual(a,b)
        self.assertEqual(len(vault.sync_preview()),1)


if __name__ == '__main__':unittest.main()
