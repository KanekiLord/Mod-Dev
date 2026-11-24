import tempfile
import unittest
from pathlib import Path
from diagnostico import vault_audit, build_report

class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.vault=self.root/'vault';self.vault.mkdir()
        self.project=self.root/'code';self.project.mkdir()

    def test_broken_links_and_duplicate_hashes(self):
        (self.vault/'a.md').write_text('[[existe]] [[ausente]]',encoding='utf-8')
        (self.vault/'existe.md').write_text('A nota 1',encoding='utf-8')
        (self.vault/'copia.md').write_text('A nota 1',encoding='utf-8')
        result=vault_audit(self.vault)
        self.assertEqual(result['markdown_notes'],3)
        self.assertIn('ausente',result['unresolved_examples'])
        self.assertEqual(result['duplicate_content_groups'],1)

    def test_diagnostic_does_not_modify_originals(self):
        (self.project/'CLAUDE.md').write_text('segredo interno aqui',encoding='utf-8')
        (self.vault/'tasks').mkdir()
        old=self.vault/'tasks'/'todo.md';old.write_text('- [ ] tarefa',encoding='utf-8')
        result=build_report(self.project,self.vault,self.root/'catalogo.json')
        self.assertTrue(result['project']['has_claude_md'])
        self.assertNotIn('segredo interno aqui',str(result))
        self.assertEqual(old.read_text(encoding='utf-8'),'- [ ] tarefa')

if __name__=='__main__': unittest.main()
