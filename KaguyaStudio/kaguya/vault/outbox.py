"""Outbox: new notes are drafted outside the vault, reviewed, then created (never overwritten).

Drafts carry source/evidence front-matter; duplicates are detected by content hash and by
similar titles already present in the vault index.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re
import unicodedata

CATEGORIES = {
    "aprendizado": Path("memoria/agentes/kaguya-studio"),
    "erro": Path("memoria/agentes/kaguya-studio/erros"),
    "pesquisa": Path("conhecimento/kaguya-studio"),
    "ideia": Path("memoria/agentes/kaguya-studio/ideias"),
    "decisao": Path("projetos/kaguya-studio/decisoes"),
}


def slug(text: str) -> str:
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:70] or "nota"


class Outbox:
    def __init__(self, vault: Path, staging: Path, index=None):
        self.root = Path(vault).resolve()
        self.staging = Path(staging).resolve()
        self.staging.mkdir(parents=True, exist_ok=True)
        self.index = index

    def stage(self, kind: str, title: str, body: str, *, source: str = "kaguya-studio", project: str = "",
              evidence: str = "", links: list[str] | None = None) -> Path:
        if kind not in CATEGORIES:
            raise ValueError("Categoria não suportada")
        title = " ".join(title.split())[:140] or "Sem título"
        created = datetime.now().astimezone().isoformat(timespec="seconds")
        fm = ["---", f"tipo: {kind}", "origem: kaguya-studio", f"fonte: {json.dumps(source, ensure_ascii=False)}",
              f"criado: {created}", "status: revisao"]
        if project:
            fm.append(f"projeto: {json.dumps(project, ensure_ascii=False)}")
        fm.append("---")
        link_line = ("\n\nRelacionado: " + " ".join(f"[[{l}]]" for l in links)) if links else ""
        ev = f"\n\n## Evidência\n{evidence.strip()[:4000]}" if evidence.strip() else ""
        content = "\n".join(fm) + f"\n\n# {title}\n\n{body.strip()[:30000]}{ev}{link_line}\n"
        digest = sha256((kind + title + body.strip()).encode("utf-8")).hexdigest()[:12]
        name = f"{slug(title)}-{digest}.md"
        dest = self.staging / name
        if not dest.exists():
            dest.write_text(content, encoding="utf-8")
            meta = {"kind": kind, "title": title, "created": created, "target": CATEGORIES[kind].as_posix(),
                    "digest": digest, "project": project, "source": source}
            (self.staging / (name + ".json")).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return dest

    def drafts(self) -> list[dict]:
        out = []
        for meta in sorted(self.staging.glob("*.md.json")):
            try:
                spec = json.loads(meta.read_text(encoding="utf-8"))
                file = self.staging / meta.name[:-5]
                if not file.exists() or spec.get("kind") not in CATEGORIES:
                    continue
                dest = self.root / CATEGORIES[spec["kind"]] / file.name
                similar = self.index.find_similar_title(spec.get("title", "")) if self.index else []
                out.append({"filename": file.name, "title": spec.get("title", ""), "kind": spec["kind"],
                            "destination": str(dest), "relative": (CATEGORIES[spec["kind"]] / file.name).as_posix(),
                            "exists": dest.exists(), "similar": similar, "created": spec.get("created", ""),
                            "body": file.read_text(encoding="utf-8")})
            except (OSError, ValueError, KeyError):
                continue
        return out

    def discard(self, filename: str) -> bool:
        if filename != Path(filename).name or not filename.endswith(".md"):
            return False
        removed = False
        for p in (self.staging / filename, self.staging / (filename + ".json")):
            if p.is_file():
                p.unlink()
                removed = True
        return removed

    def approve(self, filenames: list[str]) -> list[Path]:
        done = []
        for name in filenames:
            if not isinstance(name, str) or name != Path(name).name or not name.endswith(".md"):
                continue
            src, meta = self.staging / name, self.staging / (name + ".json")
            if not src.is_file() or not meta.is_file() or src.is_symlink() or meta.is_symlink():
                continue
            try:
                spec = json.loads(meta.read_text(encoding="utf-8"))
                folder = (self.root / CATEGORIES[spec["kind"]]).resolve()
                if not folder.is_relative_to(self.root):
                    continue
                folder.mkdir(parents=True, exist_ok=True)
                dest = folder / name
                with dest.open("x", encoding="utf-8") as fh:  # create-only: never overwrite
                    fh.write(src.read_text(encoding="utf-8"))
                src.unlink()
                meta.unlink()
                done.append(dest)
            except (OSError, ValueError, KeyError):
                continue
        return done


_SECTION = re.compile(r"^\s*(?:#+\s*)?(APRENDIZADOS?|ERROS?(?: ENCONTRADOS)?|LIÇÕES|LICOES|REFER[ÊE]NCIAS)\s*:?\s*$",
                      re.I | re.M)


def extract_learnings(text: str) -> list[tuple[str, str]]:
    """Find 'APRENDIZADOS:' / 'ERROS:' / 'REFERÊNCIAS:' sections in an agent answer.

    Returns (category, bullet) pairs. The app turns them into outbox drafts automatically, so
    learning registration no longer depends on the agent remembering to write in the vault.
    """
    out = []
    matches = list(_SECTION.finditer(text or ""))
    for i, m in enumerate(matches):
        label = m.group(1).upper()
        kind = "erro" if label.startswith("ERRO") else "pesquisa" if label.startswith("REF") else "aprendizado"
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[m.end():end]
        for line in block.splitlines():
            s = line.strip()
            if not s:
                if out and out[-1][0] == kind:
                    continue
                continue
            if s.startswith(("-", "*", "•")) or re.match(r"^\d+[.)]\s", s):
                item = re.sub(r"^([-*•]|\d+[.)])\s*", "", s).strip()
                if len(item) >= 8:
                    out.append((kind, item[:600]))
            elif s.startswith("#") or s.endswith(":"):
                break
    return out[:12]
