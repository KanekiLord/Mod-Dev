"""Leitor Universal with real files (made by the same libraries people use) and hostile ones."""
from pathlib import Path
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kaguya.reader import check_allowed, read, read_isolated  # noqa: E402


def have(mod):
    try:
        __import__(mod)
        return True
    except ImportError:
        return False


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name)


class TextAndLogs(Base):
    def test_log_sends_only_the_relevant_lines(self):
        lines = [f"[12:00:{i % 60:02d}] [Server thread/INFO]: Carregando chunk {i}" for i in range(5000)]
        lines[3200] = "[12:53:20] [Server thread/ERROR]: Erro ao registrar a entidade naruto:clone"
        lines[3201] = "java.lang.NullPointerException: Cannot invoke \"EntityType.create\" because \"type\" is null"
        lines[3202] = "\tat com.narutocd.entity.ModEntities.register(ModEntities.java:42)"
        log = self.d / "latest.log"
        log.write_text("\n".join(lines), encoding="utf-8")
        res = read(log)
        self.assertEqual(res.kind, "log")
        self.assertIn("5000 linhas", res.facts[0])
        text = res.render("NullPointerException ModEntities")
        self.assertIn("ModEntities.java:42", text)
        self.assertIn("linhas 3198–", text)                         # where it is, with line numbers
        self.assertLess(len(text), len(log.read_text()) / 20)         # never the whole log

    def test_code_json_csv_and_encoding(self):
        (self.d / "a.json").write_text('{"modid": "narutocd", "version": "1.0"}', encoding="utf-8")
        self.assertIn("chaves: modid, version", read(self.d / "a.json").facts[1])
        (self.d / "b.json").write_text('{"x": ', encoding="utf-8")
        self.assertTrue(any("JSON inválido" in w for w in read(self.d / "b.json").warnings))
        (self.d / "c.csv").write_text("item,preco\nkunai,10\nshuriken,5\n", encoding="utf-8")
        r = read(self.d / "c.csv")
        self.assertEqual(r.kind, "tabela")
        self.assertIn("2 linhas de dados", " ".join(r.facts))
        (self.d / "d.txt").write_bytes("Ação técnica".encode("cp1252"))
        self.assertEqual(read(self.d / "d.txt").pieces[0].text, "Ação técnica")


class Safety(Base):
    def test_sensitive_and_programs_are_refused(self):
        for name in (".env", "id_rsa", "credentials.json", "chave.pem", "auth.json"):
            (self.d / name).write_text("SECRET=123", encoding="utf-8")
            r = read(self.d / name)
            self.assertEqual(r.kind, "bloqueado", name)
            self.assertEqual(r.pieces, [])
        (self.d / ".ssh").mkdir()
        (self.d / ".ssh" / "config").write_text("Host x", encoding="utf-8")
        self.assertEqual(read(self.d / ".ssh" / "config").kind, "bloqueado")
        (self.d / "setup.exe").write_bytes(b"MZ\x90\x00" + b"\x00" * 100)
        self.assertEqual(read(self.d / "setup.exe").kind, "programa")

    def test_only_authorised_folders(self):
        ok = self.d / "Projetos" / "NarutoCD"
        nb = self.d / "Projetos" / "NarutoCD2"
        for f in (ok, nb):
            f.mkdir(parents=True)
            (f / "x.txt").write_text("x", encoding="utf-8")
        self.assertEqual(check_allowed(ok / "x.txt", [ok]), (ok / "x.txt").resolve())
        with self.assertRaises(PermissionError):
            check_allowed(nb / "x.txt", [ok])                        # the neighbour folder is not "inside"
        with self.assertRaises(PermissionError):
            check_allowed(ok / ".." / "NarutoCD2" / "x.txt", [ok])
        if hasattr(os, "symlink"):
            try:
                os.symlink(nb / "x.txt", ok / "atalho.txt")
            except OSError:
                return
            with self.assertRaises(PermissionError):
                check_allowed(ok / "atalho.txt", [ok])               # a link pointing outside does not count

    def test_hostile_archives_are_reported_never_extracted(self):
        slip = self.d / "slip.zip"
        with zipfile.ZipFile(slip, "w") as z:
            z.writestr("../../Windows/evil.bat", "del *")
            z.writestr("ok.txt", "ok")
        r = read(slip)
        self.assertTrue(any("zip slip" in w for w in r.warnings))
        self.assertTrue(any("programa" in w for w in r.warnings))
        self.assertFalse((self.d.parent.parent / "Windows" / "evil.bat").exists())
        bomb = self.d / "bomba.zip"
        with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("zeros.bin", b"\x00" * (40 * 1024 * 1024))
        r = read(bomb)
        self.assertTrue(any("zip bomb" in w for w in r.warnings))
        evil = self.d / "ataque.docx"
        laughs = ('<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;">]>'
                  '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">&lol2;</w:document>')
        with zipfile.ZipFile(evil, "w") as z:
            z.writestr("word/document.xml", laughs)
        r = read(evil)
        self.assertTrue(any("DTD" in w for w in r.warnings))
        self.assertEqual(r.pieces, [])

    def test_minecraft_mod_jar(self):
        jar = self.d / "narutocd-1.0.jar"
        with zipfile.ZipFile(jar, "w") as z:
            z.writestr("META-INF/mods.toml", 'modLoader="javafml"\n[[mods]]\nmodId="narutocd"\nversion="1.0"\n'
                                             '[[dependencies.narutocd]]\nmodId="forge"\nversionRange="[47,)"\n')
            z.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")
            for i in range(30):
                z.writestr(f"com/narutocd/entity/E{i}.class", b"\xca\xfe\xba\xbe")
        r = read(jar)
        self.assertEqual(r.kind, "mod de Minecraft (.jar)")
        self.assertIn("30 classes Java", " ".join(r.facts))
        self.assertIn('modId="narutocd"', r.render("dependências forge versão"))


class Office(Base):
    @unittest.skipUnless(have("docx"), "python-docx ausente (só para gerar o arquivo de teste)")
    def test_word_headings_tables_and_macros(self):
        import docx
        doc = docx.Document()
        doc.add_heading("Registro de entidades", level=1)
        doc.add_paragraph("Use DeferredRegister no construtor do mod.")
        t = doc.add_table(rows=2, cols=2)
        t.cell(0, 0).text, t.cell(0, 1).text = "Entidade", "Classe"
        t.cell(1, 0).text, t.cell(1, 1).text = "clone", "CloneEntity"
        path = self.d / "guia.docx"
        doc.save(path)
        r = read(path)
        self.assertEqual(r.kind, "word")
        text = r.render()
        self.assertIn("# Registro de entidades", text)
        self.assertIn("clone | CloneEntity", text)
        macro = self.d / "guia.docm"
        with zipfile.ZipFile(path) as src, zipfile.ZipFile(macro, "w") as dst:
            for item in src.infolist():
                dst.writestr(item, src.read(item))
            dst.writestr("word/vbaProject.bin", b"\xd0\xcf\x11\xe0 macro")
        r = read(macro)
        self.assertTrue(any("macros" in w and "NÃO" in w for w in r.warnings))

    @unittest.skipUnless(have("openpyxl"), "openpyxl ausente (só para gerar o arquivo de teste)")
    def test_excel_values_and_formulas_as_text(self):
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Itens"
        ws.append(["item", "dano"])
        ws.append(["kunai", 10])
        ws.append(["shuriken", 5])
        ws["B4"] = "=SUM(B2:B3)"
        wb.create_sheet("Notas")["A1"] = "balancear chakra"
        path = self.d / "itens.xlsx"
        wb.save(path)
        r = read(path)
        self.assertEqual(r.kind, "excel")
        text = r.render()
        self.assertIn("A2: kunai", text)
        self.assertIn("B4: =SUM(B2:B3)", text)                       # formula shown, never evaluated
        self.assertIn("balancear chakra", text)
        self.assertIn("2 planilha(s); 1 fórmula(s)", " ".join(r.facts))

    @unittest.skipUnless(have("pptx"), "python-pptx ausente (só para gerar o arquivo de teste)")
    def test_powerpoint_slides_and_notes(self):
        from pptx import Presentation
        pr = Presentation()
        s = pr.slides.add_slide(pr.slide_layouts[1])
        s.shapes.title.text = "Roadmap do NarutoCD"
        s.placeholders[1].text = "Fase 1: clones"
        s.notes_slide.notes_text_frame.text = "lembrar dos testes"
        path = self.d / "plano.pptx"
        pr.save(path)
        r = read(path)
        self.assertEqual(r.kind, "powerpoint")
        self.assertIn("Roadmap do NarutoCD", r.render())
        self.assertIn("(notas) lembrar dos testes", r.render())


class PdfAndImages(Base):
    def _pdf(self, text: str) -> Path:
        stream = f"BT /F1 18 Tf 50 700 Td ({text}) Tj ET".encode("latin-1")
        objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
                b"/Resources << /Font << /F1 5 0 R >> >> >>",
                b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
                b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
        out, offs = io.BytesIO(), []
        out.write(b"%PDF-1.4\n")
        for i, o in enumerate(objs, 1):
            offs.append(out.tell())
            out.write(f"{i} 0 obj\n".encode() + o + b"\nendobj\n")
        x = out.tell()
        out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
        for o in offs:
            out.write(f"{o:010d} 00000 n \n".encode())
        out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF".encode())
        p = self.d / "doc.pdf"
        p.write_bytes(out.getvalue())
        return p

    def test_pdf_text_with_and_without_pypdf(self):
        from unittest import mock
        p = self._pdf("Forge 1.20.1 usa DeferredRegister")
        r = read(p)
        self.assertEqual(r.kind, "pdf")
        self.assertIn("DeferredRegister", r.render())
        with mock.patch.dict(sys.modules, {"pypdf": None}):            # the Windows build has no pypdf
            r2 = read(p)
        self.assertIn("DeferredRegister", r2.render())
        self.assertIn("aproximado", r2.method)

    def test_image_metadata(self):
        from PIL import Image
        Image.new("RGBA", (64, 32)).save(self.d / "sprite.png")
        r = read(self.d / "sprite.png")
        self.assertEqual(r.kind, "imagem")
        self.assertIn("64×32", r.facts[0])


class Isolated(Base):
    def test_separate_process_gives_the_same_result(self):
        (self.d / "notas.md").write_text("# Clones\nUse o evento EntityJoinLevelEvent.", encoding="utf-8")
        r = read_isolated(self.d / "notas.md")
        self.assertEqual(r.kind, "texto")
        self.assertIn("EntityJoinLevelEvent", r.render())

    def test_timeout_is_reported(self):
        from unittest import mock
        from kaguya.reader import core
        slow = [sys.executable, "-c", "import time; time.sleep(30)"]
        with mock.patch.object(core, "reader_command", lambda: slow):
            r = core.read_isolated(self.d / "x.txt", timeout=1)
        self.assertEqual(r.kind, "erro")
        self.assertIn("interrompida", r.warnings[0])


if __name__ == "__main__":
    unittest.main()
