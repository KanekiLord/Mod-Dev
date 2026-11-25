"""Knowledge engine helpers (spec 01/08): note properties, duplicate/update detection, revalidation report.

"Learning" here means: a candidate discovery is staged with its origin (who, how, where, when, project, version,
evidence), the user approves it, it is written to the EXISTING vault and later found again by any assistant.
Nothing is ever silently overwritten: updates to an existing note are appended after a backup, and contradictions
become a visible "divergência" with both sources.
"""
from __future__ import annotations

from datetime import date, datetime
import re

FM = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
WORD = re.compile(r"[a-zà-ÿ0-9][a-zà-ÿ0-9_.\-]{2,}", re.I)


VERSION = re.compile(r"\b(Minecraft|Forge|NeoForge|Fabric(?: API)?|Quilt|GeckoLib|Photon|LDLib|Blockbench|Blender|"
                     r"Java|Gradle|Kotlin|Python|Mixin|Architectury|Iris|Sodium|OptiFine)\s+v?(\d+(?:\.\d+)+[a-z0-9.-]*)",
                     re.I)


def detect_version(text: str) -> str:
    """'Forge 1.20.1', 'GeckoLib 4.4'… the first library + version mentioned (used to spot divergences)."""
    m = VERSION.search(text or "")
    return f"{m.group(1)} {m.group(2)}" if m else ""


def parse_frontmatter(text: str) -> dict:
    """Small, safe reader of the simple ``key: value`` properties Obsidian writes (no YAML objects built)."""
    m = FM.match(text or "")
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t", "-")):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def body_of(text: str) -> str:
    m = FM.match(text or "")
    return text[m.end():] if m else (text or "")


def set_property(text: str, key: str, value: str) -> str:
    """Change (or add) one property in the front matter, keeping everything else byte for byte."""
    m = FM.match(text or "")
    line = f"{key}: {value}"
    if not m:
        return f"---\n{line}\n---\n\n{text}"
    block = m.group(1)
    if re.search(rf"^{re.escape(key)}\s*:", block, re.M):
        block = re.sub(rf"^{re.escape(key)}\s*:.*$", line, block, count=1, flags=re.M)
    else:
        block = block + "\n" + line
    return f"---\n{block}\n---\n" + text[m.end():]


def words(text: str) -> set[str]:
    return {w.lower().strip(".-") for w in WORD.findall(body_of(text or "")) if len(w) > 2}


def overlap(a: str, b: str) -> float:
    """How much of the NEW text is already in the existing note (0..1)."""
    wa, wb = words(a), words(b)
    if not wa:
        return 0.0
    return len(wa & wb) / len(wa)


def norm_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _when(value: str) -> date | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime((value or "")[:10], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value).date()
    except (TypeError, ValueError):
        return None


def review(index, max_age_days: int = 180, today: date | None = None) -> dict:
    """What deserves attention in the vault. Reports only — changes go through proposals the user approves."""
    import os
    from pathlib import Path
    today = today or date.today()
    old, flagged, no_source, broken, by_title = [], [], [], [], {}
    titles, stems = set(), set()
    notes = list(index.bodies())
    for rel, title, _body in notes:
        titles.add(title.strip().lower())
        stems.add(Path(rel).stem.lower())
        stems.add(rel.lower().removesuffix(".md"))
    for rel, title, body in notes:
        fm = parse_frontmatter(body)
        key = re.sub(r"[^a-z0-9]+", "", title.lower())
        if key:
            by_title.setdefault(key, []).append(rel)
        status = fm.get("status", "")
        if status == "necessita_revalidacao":
            flagged.append(rel)
        stamp = fm.get("validado_em") or fm.get("coletado_em") or fm.get("criado") or ""
        d = _when(stamp)
        if d and (today - d).days > max_age_days and fm.get("tipo") in ("aprendizado", "pesquisa", "erro", "decisao"):
            old.append({"path": rel, "data": d.isoformat(), "versao": fm.get("versao_contexto", "")})
        if fm.get("tipo") in ("aprendizado", "pesquisa") and not (fm.get("fonte_url") or fm.get("fonte")):
            no_source.append(rel)
        for link in re.findall(r"\[\[([^\]|#]+)", body):
            target = link.strip().lower()
            if target and target not in stems and target not in titles and \
                    os.path.basename(target) not in stems:
                broken.append({"path": rel, "link": link.strip()})
    dups = [paths for paths in by_title.values() if len(paths) > 1]
    return {"antigas": old, "a_revalidar": flagged, "sem_fonte": no_source, "links_quebrados": broken[:300],
            "duplicadas": dups, "total": len(notes), "limite_dias": max_age_days}


def context_meta(text: str) -> str:
    """One line telling the assistant how much to trust a note (status, confidence, version, source)."""
    fm = parse_frontmatter(text)
    bits = []
    if fm.get("status"):
        bits.append("status " + fm["status"].replace("_", " "))
    if fm.get("confianca"):
        bits.append("confiança " + fm["confianca"].replace("_", " "))
    if fm.get("versao_contexto"):
        bits.append("versão " + fm["versao_contexto"])
    if fm.get("fonte_url"):
        bits.append("fonte " + fm["fonte_url"])
    if fm.get("coletado_em") or fm.get("validado_em"):
        bits.append("data " + (fm.get("validado_em") or fm.get("coletado_em")))
    warn = " ⚠ PRECISA SER REVALIDADA: confirme antes de usar" if fm.get("status") == "necessita_revalidacao" else ""
    return ("(" + "; ".join(bits) + ")" if bits else "") + warn
