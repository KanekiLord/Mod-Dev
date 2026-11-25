from __future__ import annotations

from dataclasses import asdict, dataclass, field
import fnmatch
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import zipfile
from xml.etree import ElementTree as ET

MAX_FILE = 80 * 1024 * 1024          # bigger files: only archives are listed (central directory)
MAX_TEXT = 4 * 1024 * 1024           # bytes of a text file actually read
MAX_PIECES = 4000
MAX_ZIP_ENTRIES = 20000
ZIP_RATIO = 120                       # compression ratio above this smells like a zip bomb
ZIP_TOTAL = 2 * 1024 ** 3             # declared uncompressed size above this: refuse to look inside members

TEXT_EXT = {".txt", ".md", ".markdown", ".log", ".json", ".jsonc", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
            ".properties", ".csv", ".tsv", ".xml", ".html", ".htm", ".css", ".js", ".ts", ".tsx", ".jsx", ".py",
            ".java", ".kt", ".kts", ".gradle", ".groovy", ".c", ".h", ".cpp", ".hpp", ".cs", ".go", ".rs", ".rb",
            ".php", ".lua", ".sh", ".bat", ".cmd", ".ps1", ".sql", ".mcmeta", ".lang", ".snbt", ".mcfunction",
            ".glsl", ".vsh", ".fsh", ".srt", ".vtt", ".rst", ".tex", ".bbmodel"}
OFFICE = {".docx": "word", ".docm": "word", ".xlsx": "excel", ".xlsm": "excel", ".pptx": "powerpoint",
          ".pptm": "powerpoint"}
ARCHIVES = {".zip", ".jar", ".apk", ".mcpack", ".mcaddon", ".mrpack", ".war", ".aar"}
IMAGES = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".gif": "GIF", ".bmp": "BMP", ".webp": "WEBP"}
SUPPORTED = sorted(TEXT_EXT | set(OFFICE) | ARCHIVES | set(IMAGES) | {".pdf"})

SENSITIVE = ["*.env", ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa*", "id_ed25519*", "id_ecdsa*",
             ".git-credentials", ".netrc", ".npmrc", ".pypirc", "credentials.json", "credentials", "*.kdbx",
             "auth.json", ".credentials.json", "*.keystore", "*.jks", "secrets.*", "*.ovpn", "wallet.dat",
             "Login Data", "Cookies", "*.cookies"]
SENSITIVE_DIRS = {".ssh", ".aws", ".azure", ".gnupg", ".codex", ".claude"}


@dataclass
class Piece:
    where: str        # "linhas 120–140", "página 3", "Plan1!B4", "slide 2", "META-INF/mods.toml"…
    text: str
    score: float = 0.0


@dataclass
class ReadResult:
    path: str
    kind: str                      # texto | log | word | excel | powerpoint | pdf | arquivo | imagem | …
    title: str = ""
    size: int = 0
    pieces: list[Piece] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)       # short summary lines ("3 planilhas", "12 erros"…)
    warnings: list[str] = field(default_factory=list)    # what could not be read / risks found
    method: str = ""
    truncated: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ReadResult":
        d = dict(d)
        d["pieces"] = [Piece(**p) for p in d.get("pieces", [])]
        return cls(**d)

    def relevant(self, query: str = "", limit: int = 12000) -> list[Piece]:
        """Pieces to send: with a question, the ones that match it best (in file order); otherwise from the top."""
        pieces = self.pieces
        terms = [t for t in re.findall(r"\w{3,}", (query or "").lower()) if t not in _STOP]
        if terms:
            for p in pieces:
                low = p.text.lower()
                p.score = sum(low.count(t) for t in terms) + (2 if any(t in p.where.lower() for t in terms) else 0)
            ranked = sorted((p for p in pieces if p.score > 0), key=lambda p: -p.score)
            chosen, size = [], 0
            for p in ranked:
                if size + len(p.text) > limit:
                    break
                chosen.append(p)
                size += len(p.text)
            if chosen:
                order = {id(p): i for i, p in enumerate(pieces)}
                return sorted(chosen, key=lambda p: order[id(p)])
        out, size = [], 0
        for p in pieces:
            if size + len(p.text) > limit:
                break
            out.append(p)
            size += len(p.text)
        return out

    def render(self, query: str = "", limit: int = 12000) -> str:
        """Text block for the assistant (always with where each excerpt comes from)."""
        chosen = self.relevant(query, limit)
        head = [f"ARQUIVO: {self.path}", f"Tipo: {self.kind}" + (f" — {self.title}" if self.title else ""),
                f"Lido por: {self.method}"]
        head += [f"- {f}" for f in self.facts]
        if self.warnings:
            head.append("Avisos: " + "; ".join(self.warnings))
        partial = len(chosen) < len(self.pieces) or self.truncated
        if partial:
            head.append(f"(trechos selecionados: {len(chosen)} de {len(self.pieces)}"
                        + (f", pela pergunta “{query[:80]}”" if query else "") + ")")
        body = "\n\n".join(f"[{p.where}]\n{p.text}" for p in chosen)
        return "\n".join(head) + "\n\n" + body


_STOP = set("que para com uma por como dos das nos nas sem mais isso esse essa este esta onde qual quais "
            "the and for with this that from what which where".split())


# --------------------------------------------------------------------------- safety
def is_sensitive(path: Path) -> bool:
    p = Path(path)
    if any(part.lower() in SENSITIVE_DIRS for part in p.parts[:-1]):
        return True
    name = p.name
    return any(fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(name.lower(), pat.lower()) for pat in SENSITIVE)


def check_allowed(path, roots) -> Path:
    """Resolve symlinks and refuse anything outside the folders the user authorised."""
    p = Path(path).expanduser().resolve()
    for r in roots or []:
        try:
            if p.is_relative_to(Path(r).expanduser().resolve()):
                return p
        except (OSError, ValueError):
            continue
    raise PermissionError(f"Fora das pastas autorizadas: {p}")


# --------------------------------------------------------------------------- detection
def detect(path: Path, head: bytes) -> str:
    ext = path.suffix.lower()
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06"):
        return "office" if ext in OFFICE else "arquivo"
    if head.startswith(b"\x89PNG") or head[:3] == b"\xff\xd8\xff" or head[:4] == b"GIF8" or \
            head[:2] == b"BM" or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"):
        return "imagem"
    if head[:4] in (b"MZ\x90\x00",) or head[:2] == b"MZ" or head[:4] == b"\x7fELF":
        return "executavel"
    if b"\x00" in head[:4096] and not head.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "binario"
    return "texto"


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16") if data.startswith((b"\xff\xfe", b"\xfe\xff")) else ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


# --------------------------------------------------------------------------- text, code, logs
LOG_HINT = re.compile(r"(\bERROR\b|\bFATAL\b|Exception\b|Caused by:|\bSEVERE\b|Traceback \(most recent|"
                      r"\bfailed\b|\bfalhou\b|\berro\b|---- Minecraft Crash Report ----|Description:)", re.I)
WARN_HINT = re.compile(r"\bWARN(ING)?\b", re.I)


def _read_text(path: Path, res: ReadResult):
    size = path.stat().st_size
    with open(path, "rb") as fh:
        data = fh.read(MAX_TEXT + 1)
    if len(data) > MAX_TEXT:
        data, res.truncated = data[:MAX_TEXT], True
        res.warnings.append(f"arquivo grande: lidos os primeiros {MAX_TEXT // (1024 * 1024)} MB de "
                            f"{size / 1024 / 1024:.0f} MB")
    text = _decode(data).replace("\r\n", "\n")
    lines = text.rstrip("\n").split("\n") if text.strip() else []
    ext = path.suffix.lower()
    is_log = ext == ".log" or "crash-report" in path.name.lower() or path.name.lower() in ("latest.log", "debug.log")
    errors = [i for i, l in enumerate(lines) if LOG_HINT.search(l)]
    if is_log or (len(errors) >= 3 and len(lines) > 200):
        res.kind = "log"
        warns = sum(1 for l in lines if WARN_HINT.search(l))
        res.facts.append(f"{len(lines)} linhas; {len(errors)} com erro/exceção; {warns} avisos")
        # error lines with context first; then the end of the log (where crashes usually are)
        spans = []
        for i in errors:
            a, b = max(0, i - 3), min(len(lines), i + 6)
            if spans and a <= spans[-1][1]:
                spans[-1][1] = b
            else:
                spans.append([a, b])
        for a, b in spans[:400]:
            res.pieces.append(Piece(f"linhas {a + 1}–{b}", "\n".join(lines[a:b])))
        tail = max(0, len(lines) - 40)
        if not spans or spans[-1][1] < tail:
            res.pieces.append(Piece(f"linhas {tail + 1}–{len(lines)} (fim do log)", "\n".join(lines[tail:])))
        if not errors:
            res.facts.append("nenhuma linha de erro encontrada")
        res.method = "leitor de logs (linhas de erro com contexto + fim do arquivo)"
        return
    res.kind = "texto" if ext not in (".py", ".java", ".kt", ".js", ".ts", ".gradle", ".cs", ".cpp", ".c") else "código"
    res.method = "texto (UTF-8/Windows-1252)"
    if ext in (".json", ".jsonc", ".mcmeta", ".bbmodel"):
        try:
            obj = json.loads(text)
            res.facts.append("JSON válido" + (f"; chaves: {', '.join(list(obj)[:15])}" if isinstance(obj, dict) else
                                               f"; lista com {len(obj)} itens" if isinstance(obj, list) else ""))
        except ValueError as exc:
            res.warnings.append(f"JSON inválido: {exc}")
    elif ext in (".yaml", ".yml"):
        try:
            import yaml
            yaml.safe_load(text)       # safe_load: never builds arbitrary objects
            res.facts.append("YAML válido")
        except ImportError:
            pass
        except Exception as exc:
            res.warnings.append(f"YAML inválido: {str(exc)[:120]}")
    elif ext in (".csv", ".tsv"):
        res.kind = "tabela"
        res.facts.append(f"{max(0, len(lines) - 1)} linhas de dados; cabeçalho: {lines[0][:200] if lines else ''}")
    step = 40
    for a in range(0, len(lines), step):
        chunk = "\n".join(lines[a:a + step]).strip()
        if chunk:
            res.pieces.append(Piece(f"linhas {a + 1}–{min(len(lines), a + step)}", chunk))
        if len(res.pieces) >= MAX_PIECES:
            res.truncated = True
            break
    res.facts.insert(0, f"{len(lines)} linhas")


# --------------------------------------------------------------------------- Office (zip of XML; no macros run)
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _xml(z: zipfile.ZipFile, name: str):
    info = z.getinfo(name)
    if info.file_size > 60 * 1024 * 1024:
        raise ValueError(f"parte grande demais: {name}")
    data = z.read(name)
    if b"<!DOCTYPE" in data[:2048] or b"<!ENTITY" in data[:4096]:
        raise ValueError("documento com DTD/entidades (possível ataque XML) — não lido")
    return ET.fromstring(data)


def _office(path: Path, res: ReadResult):
    kind = OFFICE[path.suffix.lower()]
    res.kind = kind
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        if any(n.lower().endswith("vbaproject.bin") for n in names):
            res.warnings.append("contém macros (VBA): NÃO foram executadas nem lidas")
        if kind == "word":
            _word(z, names, res)
        elif kind == "excel":
            _excel(z, names, res)
        else:
            _pptx(z, names, res)
    res.method = f"leitor próprio de {kind} (XML do arquivo, modo seguro)"


def _word(z, names, res):
    root = _xml(z, "word/document.xml")
    body = root.find(f"{W}body")
    para_buf, n_par, n_tab, heading = [], 0, 0, ""

    def flush():
        nonlocal para_buf
        if para_buf:
            res.pieces.append(Piece(heading or f"parágrafos {n_par - len(para_buf) + 1}–{n_par}", "\n".join(para_buf)))
            para_buf = []
    for el in list(body) if body is not None else []:
        if el.tag == f"{W}p":
            text = "".join(t.text or "" for t in el.iter(f"{W}t")).strip()
            style = el.find(f"{W}pPr/{W}pStyle")
            sval = (style.get(f"{W}val") if style is not None else "") or ""
            if not text:
                continue
            n_par += 1
            if sval.lower().startswith(("heading", "titulo", "título", "title")):
                flush()
                heading = f"seção “{text[:60]}”"
                para_buf.append("# " + text)
            else:
                para_buf.append(text)
            if sum(len(p) for p in para_buf) > 1500:
                flush()
        elif el.tag == f"{W}tbl":
            flush()
            n_tab += 1
            rows = []
            for tr in el.iter(f"{W}tr"):
                cells = ["".join(t.text or "" for t in tc.iter(f"{W}t")).strip() for tc in tr.iter(f"{W}tc")]
                rows.append(" | ".join(cells))
            res.pieces.append(Piece(f"tabela {n_tab}", "\n".join(rows[:300])))
    flush()
    res.facts.append(f"{n_par} parágrafos, {n_tab} tabela(s)")
    core = "docProps/core.xml"
    if core in names:
        try:
            title = _xml(z, core).find("{http://purl.org/dc/elements/1.1/}title")
            res.title = (title.text or "") if title is not None else ""
        except (ValueError, ET.ParseError):
            pass


def _col(ref: str) -> str:
    return re.match(r"[A-Z]+", ref).group(0) if ref and re.match(r"[A-Z]+", ref) else ""


def _excel(z, names, res):
    shared = []
    if "xl/sharedStrings.xml" in names:
        for si in _xml(z, "xl/sharedStrings.xml").iter(f"{S}si"):
            shared.append("".join(t.text or "" for t in si.iter(f"{S}t")))
    wb = _xml(z, "xl/workbook.xml")
    rels = {}
    if "xl/_rels/workbook.xml.rels" in names:
        for r in _xml(z, "xl/_rels/workbook.xml.rels").iter(f"{REL}Relationship"):
            rels[r.get("Id")] = r.get("Target")
    sheets = wb.find(f"{S}sheets")
    n_formulas = 0
    count = 0
    for sh in list(sheets) if sheets is not None else []:
        name = sh.get("name")
        target = rels.get(sh.get(f"{R}id"), "")
        part = ("xl/" + target.lstrip("/").removeprefix("xl/")) if target else ""
        if part not in names:
            continue
        count += 1
        rows_out, cells_seen = [], 0
        for row in _xml(z, part).iter(f"{S}row"):
            vals = []
            for c in row.iter(f"{S}c"):
                ref, t = c.get("r", ""), c.get("t")
                f, v = c.find(f"{S}f"), c.find(f"{S}v")
                val = v.text if v is not None else ""
                if t == "s" and val and val.isdigit() and int(val) < len(shared):
                    val = shared[int(val)]
                elif t == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter(f"{S}t"))
                if f is not None and f.text:
                    n_formulas += 1
                    val = f"={f.text}  → {val}"     # formula shown as text with the saved result; never evaluated
                if val != "":
                    vals.append(f"{ref}: {val}")
                    cells_seen += 1
            if vals:
                rows_out.append("  ".join(vals))
            if cells_seen > 3000:
                res.warnings.append(f"planilha “{name}” grande: lidas as primeiras ~3000 células")
                break
        for a in range(0, len(rows_out), 30):
            res.pieces.append(Piece(f"planilha “{name}” linhas {a + 1}–{min(len(rows_out), a + 30)}",
                                    "\n".join(rows_out[a:a + 30])))
    res.facts.append(f"{count} planilha(s); {n_formulas} fórmula(s) (mostradas como texto, não executadas)")


def _pptx(z, names, res):
    slides = sorted((n for n in names if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                    key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)))
    for n in slides:
        num = re.search(r"(\d+)\.xml$", n).group(1)
        texts = [t.text for t in _xml(z, n).iter(f"{A}t") if t.text and t.text.strip()]
        note = f"ppt/notesSlides/notesSlide{num}.xml"
        notes = [t.text for t in _xml(z, note).iter(f"{A}t") if t.text and t.text.strip()] if note in names else []
        body = "\n".join(texts) + ("\n(notas) " + " ".join(notes) if notes else "")
        if body.strip():
            res.pieces.append(Piece(f"slide {num}", body))
    res.facts.append(f"{len(slides)} slide(s)")


# --------------------------------------------------------------------------- PDF (text layer)
def _pdf(path: Path, res: ReadResult):
    res.kind = "pdf"
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            res.warnings.append("PDF protegido por senha: não lido")
            return
        n = len(reader.pages)
        for i, page in enumerate(reader.pages[:400], 1):
            text = (page.extract_text() or "").strip()
            if text:
                res.pieces.append(Piece(f"página {i}", text))
        res.method = "pypdf (camada de texto)"
        res.facts.append(f"{n} página(s)")
    except ImportError:
        _pdf_builtin(path, res)
    chars = sum(len(p.text) for p in res.pieces)
    if chars < 40:
        res.warnings.append("quase nenhum texto: o PDF parece escaneado (imagem). OCR não disponível — mande a página "
                            "como imagem para a IA, se quiser")


def _pdf_builtin(path: Path, res: ReadResult):
    """Minimal text-layer extraction (Flate streams, Tj/TJ). Good for simple PDFs; marks itself as approximate."""
    import zlib
    data = path.read_bytes()[:MAX_FILE]
    texts = []
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        raw = m.group(1)
        try:
            raw = zlib.decompress(raw)
        except zlib.error:
            pass
        if b"Tj" not in raw and b"TJ" not in raw:
            continue
        parts = []
        for t in re.finditer(rb"\((.*?)(?<!\\)\)\s*Tj|\[(.*?)\]\s*TJ", raw, re.S):
            seg = t.group(1) if t.group(1) is not None else b"".join(re.findall(rb"\((.*?)(?<!\\)\)", t.group(2), re.S))
            parts.append(seg.replace(rb"\(", b"(").replace(rb"\)", b")").decode("latin-1", errors="replace"))
        if parts:
            texts.append(" ".join(parts))
    for i, t in enumerate(texts, 1):
        res.pieces.append(Piece(f"bloco de texto {i}", t))
    res.method = "leitor simples de PDF do Studio (aproximado: fontes especiais podem sair erradas)"
    res.facts.append(f"{len(texts)} bloco(s) de texto")


# --------------------------------------------------------------------------- archives (listed, never extracted)
MOD_FILES = ("META-INF/mods.toml", "META-INF/neoforge.mods.toml", "fabric.mod.json", "quilt.mod.json", "mcmod.info",
             "META-INF/MANIFEST.MF", "pack.mcmeta", "manifest.json", "modrinth.index.json", "AndroidManifest.xml")


def _archive(path: Path, res: ReadResult):
    res.kind = "arquivo compactado"
    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        if len(infos) > MAX_ZIP_ENTRIES:
            res.warnings.append(f"{len(infos)} itens: listados os primeiros {MAX_ZIP_ENTRIES}")
            infos = infos[:MAX_ZIP_ENTRIES]
        total = sum(i.file_size for i in infos)
        packed = sum(i.compress_size for i in infos) or 1
        unsafe = [i.filename for i in infos if i.filename.startswith(("/", "\\")) or ".." in PurePosixPath(
            i.filename.replace("\\", "/")).parts or re.match(r"^[A-Za-z]:", i.filename)]
        bombs = [i.filename for i in infos if i.compress_size and i.file_size / i.compress_size > ZIP_RATIO
                 and i.file_size > 10 * 1024 * 1024]
        execs = [i.filename for i in infos if i.filename.lower().endswith((".exe", ".dll", ".bat", ".cmd", ".ps1",
                                                                           ".vbs", ".scr", ".msi", ".sh", ".so"))]
        nested = [i.filename for i in infos if i.filename.lower().endswith(tuple(ARCHIVES))]
        classes = sum(1 for i in infos if i.filename.endswith(".class"))
        res.facts.append(f"{len(infos)} itens; {total / 1024 / 1024:.1f} MB descompactado ({packed / 1024 / 1024:.1f} MB "
                         "compactado); nada foi extraído nem executado")
        if classes:
            pkgs = sorted({"/".join(i.filename.split("/")[:-1]) for i in infos if i.filename.endswith(".class")})
            res.facts.append(f"{classes} classes Java em {len(pkgs)} pacote(s)")
        if unsafe:
            res.warnings.append(f"PERIGO: {len(unsafe)} caminho(s) que escapam da pasta ao extrair (zip slip): "
                                + ", ".join(unsafe[:5]))
        if bombs or total > ZIP_TOTAL or total / packed > ZIP_RATIO:
            res.warnings.append("PERIGO: compressão suspeita (possível “zip bomb”) — conteúdo não aberto")
        if execs:
            res.warnings.append(f"contém {len(execs)} programa(s)/script(s) (não executados): " + ", ".join(execs[:5]))
        if nested:
            res.facts.append(f"{len(nested)} arquivo(s) compactado(s) dentro (não abertos): " + ", ".join(nested[:5]))
        dangerous = bool(unsafe or bombs or total > ZIP_TOTAL)
        if not dangerous:
            for name in MOD_FILES:
                if name in z.namelist():
                    info = z.getinfo(name)
                    if info.file_size < 512 * 1024:
                        res.pieces.append(Piece(name, _decode(z.read(name))[:20000]))
            if any(p.where in MOD_FILES[:5] for p in res.pieces):
                res.kind = "mod de Minecraft (.jar)" if path.suffix.lower() == ".jar" else res.kind
        listing = [f"{i.filename}  ({i.file_size} B)" for i in infos if not i.filename.endswith(".class")][:600]
        for a in range(0, len(listing), 120):
            res.pieces.append(Piece(f"lista de arquivos {a + 1}–{a + len(listing[a:a + 120])}", "\n".join(listing[a:a + 120])))
    res.method = "leitor de ZIP do Studio (só índice e metadados)"


# --------------------------------------------------------------------------- images
def _image(path: Path, res: ReadResult):
    res.kind = "imagem"
    try:
        from PIL import Image
        with Image.open(path) as im:
            res.facts.append(f"{im.format} {im.width}×{im.height}, modo {im.mode}")
    except Exception:
        head = path.read_bytes()[:32]
        if head.startswith(b"\x89PNG"):
            import struct
            w, h = struct.unpack(">II", head[16:24])
            res.facts.append(f"PNG {w}×{h}")
    res.pieces.append(Piece("imagem", "A imagem em si vai anexada para a IA ver; o Studio não lê texto dentro dela."))
    res.method = "metadados da imagem"


# --------------------------------------------------------------------------- entry points
def read(path) -> ReadResult:
    p = Path(path)
    res = ReadResult(path=str(p), kind="?", title=p.name)
    if is_sensitive(p):
        res.kind = "bloqueado"
        res.warnings.append("arquivo sensível (senhas, chaves, credenciais): o Studio não lê nem envia")
        return res
    if not p.is_file():
        res.kind = "erro"
        res.warnings.append("arquivo não encontrado")
        return res
    res.size = p.stat().st_size
    with open(p, "rb") as fh:
        head = fh.read(8192)
    kind = detect(p, head)
    try:
        if kind == "executavel":
            res.kind = "programa"
            res.warnings.append("programa executável: o Studio não lê nem executa")
        elif res.size > MAX_FILE and kind != "arquivo":
            res.kind = kind
            res.warnings.append(f"arquivo grande demais ({res.size / 1024 / 1024:.0f} MB)")
        elif kind == "pdf":
            _pdf(p, res)
        elif kind == "office":
            _office(p, res)
        elif kind == "arquivo":
            _archive(p, res)
        elif kind == "imagem":
            _image(p, res)
        elif kind == "binario":
            res.kind = "binário"
            res.warnings.append("formato binário não suportado")
        else:
            _read_text(p, res)
    except (zipfile.BadZipFile, ET.ParseError, ValueError, KeyError) as exc:
        res.warnings.append(f"não foi possível ler: {str(exc)[:200]}")
    if len(res.pieces) > MAX_PIECES:
        res.pieces, res.truncated = res.pieces[:MAX_PIECES], True
    return res


def reader_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--ler-arquivo"]
    return [sys.executable, "-m", "kaguya.reader"]


def read_isolated(path, timeout: float = 25) -> ReadResult:
    """Parse in a separate process (a hostile or huge file cannot hang or crash the Studio)."""
    env = dict(os.environ)
    if not getattr(sys, "frozen", False):
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2]) + os.pathsep + env.get("PYTHONPATH", "")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        p = subprocess.run([*reader_command(), str(path)], capture_output=True, timeout=timeout, env=env,
                           creationflags=flags)
        out = p.stdout.decode("utf-8", errors="replace").strip().splitlines()
        if p.returncode != 0 or not out:
            raise RuntimeError((p.stderr.decode("utf-8", errors="replace") or "sem resposta")[-300:])
        return ReadResult.from_dict(json.loads(out[-1]))
    except subprocess.TimeoutExpired:
        res = ReadResult(path=str(path), kind="erro", title=Path(path).name)
        res.warnings.append(f"a leitura passou de {timeout:.0f} s e foi interrompida")
        return res
    except (RuntimeError, ValueError, OSError) as exc:
        res = ReadResult(path=str(path), kind="erro", title=Path(path).name)
        res.warnings.append(f"falha no leitor: {str(exc)[:200]}")
        return res
