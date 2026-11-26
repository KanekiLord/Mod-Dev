"""Outbox: knowledge is proposed outside the vault, reviewed, then written — never silently overwritten.

* A NEW note is created with the properties of spec 08 (tipo, projeto, fonte_url, coletado_em, status, confiança,
  versão, encontrado_por) and only if the file does not exist (create-only).
* When the vault already has the same source, or a note that already says most of it, the proposal becomes an
  UPDATE of that note: approving appends a dated section, after a backup, and only if the note did not change since
  the proposal was made. If the versions differ, it is a DIVERGÊNCIA (both stay visible, nothing is replaced).
* The exact same content again is not staged at all ("já registrado").
* Without a connected vault, proposals still queue up; they can be approved once the vault is linked.
"""
from __future__ import annotations

from datetime import datetime
import difflib
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import unicodedata

from .knowledge import norm_text, overlap, parse_frontmatter, set_property

CATEGORIES = {
    "aprendizado": Path("memoria/agentes/kaguya-studio"),
    "erro": Path("memoria/agentes/kaguya-studio/erros"),
    "pesquisa": Path("conhecimento/kaguya-studio"),
    "ideia": Path("memoria/agentes/kaguya-studio/ideias"),
    "decisao": Path("projetos/kaguya-studio/decisoes"),
}
PROPOSALS = {"atualizacao": "Atualizar nota existente", "divergencia": "Divergência com nota existente",
             "revalidar": "Marcar para revalidar"}
LABELS = {**{k: "Nova nota" for k in CATEGORIES}, **PROPOSALS}
SAME_CONTENT = 0.6      # share of the new text already present in an existing note → update, not a new note


def slug(text: str) -> str:
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:70] or "nota"


def _hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


BOM = b"\xef\xbb\xbf"


def _file_hash(path: Path) -> str:
    """Hash of the note exactly as it is on disk (same at proposal and at approval, BOM or not)."""
    return "b:" + sha256(Path(path).read_bytes()).hexdigest()


def _unchanged(path: Path, base_hash: str | None) -> bool:
    if not base_hash:
        return False
    if base_hash.startswith("b:"):
        return _file_hash(path) == base_hash
    try:                                   # proposals made before 5.9.2 hashed the decoded text
        return _hash(Path(path).read_text(encoding="utf-8")) == base_hash
    except (OSError, ValueError):
        return False


def _read_note(path: Path) -> tuple[str, bool]:
    """(text, had_bom). Invalid bytes raise: the note is never rewritten with replaced characters."""
    raw = Path(path).read_bytes()
    bom = raw.startswith(BOM)
    return raw[len(BOM):].decode("utf-8") if bom else raw.decode("utf-8"), bom


def _q(v: str) -> str:
    return json.dumps(v, ensure_ascii=False)


class Outbox:
    def __init__(self, vault: Path | None, staging: Path, index=None, backups: Path | None = None):
        self.root = Path(vault).resolve() if vault else None
        self.staging = Path(staging).resolve()
        self.staging.mkdir(parents=True, exist_ok=True)
        self.backups = Path(backups) if backups else self.staging.parent / "backups" / "notas"
        self.index = index
        self.last_status = ""      # "novo" | "atualizacao" | "divergencia" | "duplicado"
        self.last_error = ""

    # ------------------------------------------------------------------ staging
    def _existing(self, title: str, body: str, source_url: str) -> tuple[str, str] | None:
        """(path, text) of a vault note that already covers this, if any."""
        if self.index is None or self.root is None:
            return None
        best, best_score = None, 0.0
        similar = set(self.index.find_similar_title(title))
        for rel, _t, text in self.index.bodies():
            fm = parse_frontmatter(text)
            if source_url and fm.get("fonte_url") == source_url:
                return rel, text
            score = overlap(body, text)
            if rel in similar:
                score += 0.25
            if score > best_score:
                best, best_score = (rel, text), score
        return best if best_score >= SAME_CONTENT else None

    def stage(self, kind: str, title: str, body: str, *, source: str = "kaguya-studio", project: str = "",
              evidence: str = "", links: list[str] | None = None, source_url: str = "", source_type: str = "",
              version: str = "", found_by: str = "", theme: str = "", confidence: str = "a_verificar") -> Path:
        if kind not in CATEGORIES:
            raise ValueError("Categoria não suportada")
        title = " ".join(title.split())[:140] or "Sem título"
        now = datetime.now().astimezone()
        created = now.isoformat(timespec="seconds")
        body = body.strip()[:30000]
        if not source_url:
            m = re.search(r"https?://[^\s)>\]]+", body + " " + source)
            source_url = m.group(0).rstrip(".,;") if m else ""
        existing = self._existing(title, body, source_url)
        if existing and norm_text(body) and norm_text(body) in norm_text(existing[1]):
            self.last_status = "duplicado"            # already in the vault, word for word
            return self.root / existing[0]
        ev = f"\n\n## Evidência\n{evidence.strip()[:4000]}" if evidence.strip() else ""
        link_line = ("\n\nRelacionado: " + " ".join(f"[[{l}]]" for l in links)) if links else ""
        who = found_by or source
        if existing:
            rel, text = existing
            old_v = parse_frontmatter(text).get("versao_contexto", "")
            diverge = bool(version and old_v and version.strip() != old_v.strip())
            kind2 = "divergencia" if diverge else "atualizacao"
            head = (f"## ⚠ Divergência {now:%Y-%m-%d} — {who}\nEsta nota registrava **{old_v}**; a nova fonte fala de "
                    f"**{version}**. As duas ficam registradas até alguém verificar." if diverge else
                    f"## Atualização {now:%Y-%m-%d} — {who}")
            extra = "\n".join(x for x in (
                f"Fonte: {source_url}" if source_url else "", f"Versão: {version}" if version else "",
                f"Projeto: {project}" if project else "", f"Confiança: {confidence.replace('_', ' ')} · status: em revisão")
                if x)
            section = f"\n\n{head}\n\n{body}{ev}\n\n{extra}{link_line}\n"
            digest = _hash(rel + section)[:12]
            name = f"{kind2}-{slug(Path(rel).stem)}-{digest}.md"
            dest = self.staging / name
            if not dest.exists():
                dest.write_text(section, encoding="utf-8")
                meta = {"kind": kind2, "title": f"{Path(rel).stem} ← {title}", "created": created, "target": rel,
                        "base_hash": _file_hash(self.root / rel) if (self.root / rel).is_file() else _hash(text),
                        "digest": digest, "project": project, "source": source,
                        "source_url": source_url, "category": kind}
                (self.staging / (name + ".json")).write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                                            encoding="utf-8")
            self.last_status = kind2
            return dest
        fm = ["---", f"tipo: {kind}", "origem: kaguya-studio", f"fonte: {_q(source)}"]
        if project:
            fm.append(f"projeto: {_q(project)}")
        if theme:
            fm.append(f"tema: {_q(theme)}")
        if source_url:
            fm.append(f"fonte_url: {source_url}")
        if source_type:
            fm.append(f"fonte_tipo: {source_type}")
        fm += [f"coletado_em: {now:%Y-%m-%d}", f"criado: {created}", "status: em_revisao", f"confianca: {confidence}"]
        if version:
            fm.append(f"versao_contexto: {_q(version)}")
        if found_by:
            fm.append(f"encontrado_por: {_q(found_by)}")
        fm.append("---")
        content = "\n".join(fm) + f"\n\n# {title}\n\n{body}{ev}{link_line}\n"
        digest = _hash(kind + title + body)[:12]
        name = f"{slug(title)}-{digest}.md"
        dest = self.staging / name
        if not dest.exists():
            dest.write_text(content, encoding="utf-8")
            meta = {"kind": kind, "title": title, "created": created, "target": CATEGORIES[kind].as_posix(),
                    "digest": digest, "project": project, "source": source, "source_url": source_url}
            (self.staging / (name + ".json")).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        self.last_status = "novo"
        return dest

    def propose_revalidation(self, rel: str, reason: str) -> Path | None:
        """Ask to mark a note as needing revalidation (only its 'status' property changes, after approval)."""
        if self.root is None:
            return None
        path = (self.root / rel).resolve()
        if not path.is_file() or not path.is_relative_to(self.root):
            return None
        text = path.read_text(encoding="utf-8")
        digest = _hash(rel + reason)[:12]
        name = f"revalidar-{slug(Path(rel).stem)}-{digest}.md"
        (self.staging / name).write_text(f"Motivo: {reason}\n", encoding="utf-8")
        meta = {"kind": "revalidar", "title": f"Revalidar {Path(rel).stem}", "target": rel,
                "base_hash": _file_hash(path),
                "created": datetime.now().astimezone().isoformat(timespec="seconds"), "reason": reason}
        (self.staging / (name + ".json")).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.staging / name

    # ------------------------------------------------------------------ review
    def _result(self, spec: dict, rel: str, current: str, addition: str) -> str:
        if spec["kind"] == "revalidar":
            return set_property(current, "status", "necessita_revalidacao")
        return current.rstrip("\n") + "\n" + addition

    def drafts(self) -> list[dict]:
        out = []
        for meta in sorted(self.staging.glob("*.md.json")):
            try:
                spec = json.loads(meta.read_text(encoding="utf-8"))
                file = self.staging / meta.name[:-5]
                kind = spec.get("kind")
                if not file.exists() or kind not in LABELS:
                    continue
                body = file.read_text(encoding="utf-8")
                item = {"filename": file.name, "title": spec.get("title", ""), "kind": kind, "label": LABELS[kind],
                        "created": spec.get("created", ""), "body": body, "similar": [], "diff": "", "stale": False,
                        "source_url": spec.get("source_url", "")}
                if kind in PROPOSALS:
                    rel = spec["target"]
                    item.update(relative=rel, destination=str(self.root / rel) if self.root else "",
                                exists=True)
                    cur_path = (self.root / rel) if self.root else None
                    if cur_path is not None and cur_path.is_file():
                        cur = _read_note(cur_path)[0]
                        item["stale"] = not _unchanged(cur_path, spec.get("base_hash"))
                        new = self._result(spec, rel, cur, body)
                        item["diff"] = "".join(difflib.unified_diff(cur.splitlines(True), new.splitlines(True),
                                                                    f"{rel} (atual)", f"{rel} (proposta)", n=2))
                    else:
                        item["stale"] = True
                else:
                    rel = (CATEGORIES[kind] / file.name).as_posix()
                    dest = (self.root / rel) if self.root else None
                    item.update(relative=rel, destination=str(dest) if dest else "",
                                exists=bool(dest and dest.exists()),
                                similar=self.index.find_similar_title(spec.get("title", "")) if self.index else [])
                out.append(item)
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

    def _backup(self, path: Path, rel: str) -> Path:
        dest = self.backups / f"{rel}.{datetime.now():%Y%m%d-%H%M%S}.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        return dest

    def approve(self, filenames: list[str]) -> list[Path]:
        self.last_error = ""
        if self.root is None:
            self.last_error = "Conecte o Segundo Cérebro (vault) para aprovar: as propostas continuam guardadas."
            return []
        done = []
        for name in filenames:
            if not isinstance(name, str) or name != Path(name).name or not name.endswith(".md"):
                continue
            src, meta = self.staging / name, self.staging / (name + ".json")
            if not src.is_file() or not meta.is_file() or src.is_symlink() or meta.is_symlink():
                continue
            try:
                spec = json.loads(meta.read_text(encoding="utf-8"))
                if spec["kind"] in PROPOSALS:
                    target = (self.root / spec["target"]).resolve()
                    if not target.is_relative_to(self.root) or not target.is_file():
                        continue
                    if not _unchanged(target, spec.get("base_hash")):
                        self.last_error = (f"“{spec['target']}” mudou depois da proposta: nada foi alterado. "
                                           "Descarte e gere a proposta de novo.")
                        continue
                    try:
                        cur, bom = _read_note(target)
                    except UnicodeDecodeError:
                        self.last_error = (f"“{spec['target']}” tem caracteres inválidos (não é UTF-8): nada foi "
                                           "alterado para não estragar a nota. Abra e salve no Obsidian, depois aprove.")
                        continue
                    self._backup(target, spec["target"])
                    new = self._result(spec, spec["target"], cur, src.read_text(encoding="utf-8"))
                    tmp = target.with_name(target.name + ".kaguya-tmp")
                    tmp.write_text(new, encoding="utf-8-sig" if bom else "utf-8")   # keeps the note's own format
                    os.replace(tmp, target)            # atomic: a crash never leaves half a note
                    dest = target
                else:
                    folder = (self.root / CATEGORIES[spec["kind"]]).resolve()
                    if not folder.is_relative_to(self.root):
                        continue
                    folder.mkdir(parents=True, exist_ok=True)
                    dest = folder / name
                    try:
                        with dest.open("x", encoding="utf-8") as fh:  # create-only: never overwrite
                            fh.write(src.read_text(encoding="utf-8"))
                    except FileExistsError:
                        self.last_error = (f"Já existe uma nota “{CATEGORIES[spec['kind']]}/{name}”: nada foi "
                                           "sobrescrito. Renomeie ou apague a existente e aprove de novo.")
                        continue
                src.unlink()
                meta.unlink()
                done.append(dest)
            except (OSError, ValueError, KeyError) as exc:
                self.last_error = f"Não foi possível aprovar “{name}”: {exc}"      # never silent
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
