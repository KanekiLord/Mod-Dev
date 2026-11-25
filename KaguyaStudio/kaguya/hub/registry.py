"""Persistent catalogue (SQLite) with reconciliation and an audit trail. Never stores secrets."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time

from . import redact
from .model import FLAGS, STATES, Extension

PROBE_FLAGS = {"falha", "requer_login", "indisponivel", "requer_reinicio"}   # owned by checks, not by config files


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Registry:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.sessions: dict[str, float] = {}     # provider → start time of a persistent session (e.g. Live)
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS extensions(
                    id TEXT PRIMARY KEY, provider TEXT, kind TEXT, name TEXT, scope TEXT, project TEXT, parent TEXT,
                    data TEXT NOT NULL, fingerprint TEXT, state TEXT, flags TEXT, first_seen TEXT, last_seen TEXT,
                    last_change TEXT, removed_at TEXT);
                CREATE INDEX IF NOT EXISTS idx_ext_provider ON extensions(provider, kind);
                CREATE TABLE IF NOT EXISTS audit(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, provider TEXT, scope TEXT, extension_id TEXT,
                    event TEXT, old_status TEXT, new_status TEXT, actor TEXT, approval_id TEXT, evidence_hash TEXT,
                    summary TEXT);
                CREATE INDEX IF NOT EXISTS idx_audit_ext ON audit(extension_id, id);
            """)

    def _db(self):
        lock, path = self._lock, self.path

        class Ctx:
            def __enter__(s):
                lock.acquire()
                s.db = sqlite3.connect(str(path), timeout=15)
                s.db.row_factory = sqlite3.Row
                return s.db

            def __exit__(s, et, *_):
                try:
                    if et is None:
                        s.db.commit()
                    s.db.close()
                finally:
                    lock.release()
        return Ctx()

    # ------------------------------------------------------------------ audit
    def audit(self, db, ext_id: str, provider: str, scope: str, event: str, old: str = "", new: str = "",
              actor: str = "hub", approval: str = "", evidence: str = "", summary: str = ""):
        db.execute("INSERT INTO audit(ts,provider,scope,extension_id,event,old_status,new_status,actor,approval_id,"
                   "evidence_hash,summary) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (_now(), provider, scope, ext_id, event, old, new, actor, approval,
                    hashlib.sha256(evidence.encode("utf-8")).hexdigest()[:16] if evidence else "",
                    redact.value(summary)[:500]))

    def history(self, ext_id: str, limit: int = 100) -> list[dict]:
        with self._db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM audit WHERE extension_id=? ORDER BY id DESC LIMIT ?",
                                                (ext_id, limit))]

    def log(self, limit: int = 200) -> list[dict]:
        with self._db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))]

    # ------------------------------------------------------------------ store
    @staticmethod
    def _status(state: str, flags: list[str]) -> str:
        return state + ("+" + ",".join(sorted(flags)) if flags else "")

    def _save(self, db, ext: Extension, first: str | None = None, removed: str | None = None):
        data = redact.value(json.dumps(ext.to_dict(), ensure_ascii=False))   # belt and braces: no secret survives
        db.execute("INSERT OR REPLACE INTO extensions(id,provider,kind,name,scope,project,parent,data,fingerprint,state,"
                   "flags,first_seen,last_seen,last_change,removed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,"
                   "COALESCE(?,(SELECT first_seen FROM extensions WHERE id=?),?),?,?,?)",
                   (ext.id, ext.provider, ext.kind, ext.name, ext.scope, ext.project, ext.parent, data,
                    ext.fingerprint(), ext.state, json.dumps(sorted(set(ext.flags))), first, ext.id, _now(), _now(),
                    ext.details.get("_last_change", _now()), removed))

    def get(self, ext_id: str) -> Extension | None:
        with self._db() as db:
            r = db.execute("SELECT data, state, flags FROM extensions WHERE id=?", (ext_id,)).fetchone()
        if not r:
            return None
        ext = Extension.from_dict(json.loads(r["data"]))
        ext.state, ext.flags = r["state"], json.loads(r["flags"] or "[]")
        return ext

    def all(self, include_removed: bool = True) -> list[Extension]:
        with self._db() as db:
            rows = db.execute("SELECT data, state, flags FROM extensions ORDER BY provider, kind, name").fetchall()
        out = []
        for r in rows:
            ext = Extension.from_dict(json.loads(r["data"]))
            ext.state, ext.flags = r["state"], json.loads(r["flags"] or "[]")
            if include_removed or "removido" not in ext.flags:
                out.append(ext)
        return out

    def query(self, text: str = "", provider: str = "", kind: str = "", status: str = "", project: str = "",
              offset: int = 0, limit: int = 300, include_removed: bool = False) -> tuple[list[Extension], int]:
        items = self.all(include_removed=include_removed or status == "removido")
        t = text.strip().lower()
        res = [e for e in items
               if (not t or t in f"{e.name} {e.description} {e.parent} {' '.join(e.tools)}".lower())
               and (not provider or e.provider == provider) and (not kind or e.kind == kind)
               and (not project or e.project in ("", project))
               and (not status or e.state == status or status in e.flags)]
        return res[offset:offset + limit], len(res)

    def counts(self) -> dict[str, int]:
        c: dict[str, int] = {}
        for e in self.all(include_removed=True):
            if "removido" in e.flags:
                c["removido"] = c.get("removido", 0) + 1
                continue
            c[e.state] = c.get(e.state, 0) + 1
            for f in e.flags:
                c[f] = c.get(f, 0) + 1
        return c

    # ------------------------------------------------------------------ reconcile
    def reconcile(self, provider: str, found: list[Extension], bad_sources: set[str]) -> list[dict]:
        """Bring the catalogue in line with what the client has NOW (the external change always wins)."""
        events = []
        seen = set()
        with self._db() as db:
            stored = {r["id"]: r for r in db.execute("SELECT * FROM extensions WHERE provider=?", (provider,))}
            for ext in found:
                if ext.id in seen:
                    continue            # same item reported twice by overlapping sources: one entry
                seen.add(ext.id)
                old = stored.get(ext.id)
                if old is None:
                    self._save(db, ext, first=_now())
                    self.audit(db, ext.id, provider, ext.scope, "descoberto", "", self._status(ext.state, ext.flags),
                               summary=ext.evidence)
                    events.append({"event": "descoberto", "id": ext.id, "name": ext.name})
                    continue
                prev = Extension.from_dict(json.loads(old["data"]))
                prev_state, prev_flags = old["state"], json.loads(old["flags"] or "[]")
                was_removed = bool(old["removed_at"]) or "removido" in prev_flags
                changed = old["fingerprint"] != ext.fingerprint()
                if changed or was_removed:
                    if self.sessions.get(provider):
                        ext.flags.append("requer_reinicio")     # a running session still has the old config
                    ext.details["_last_change"] = _now()
                    self._save(db, ext)
                    ev = "reinstalado" if was_removed else "alterado"
                    self.audit(db, ext.id, provider, ext.scope, ev, self._status(prev_state, prev_flags),
                               self._status(ext.state, ext.flags),
                               summary=("voltou a aparecer" if was_removed else
                                        f"versão {prev.version or '?'} → {ext.version or '?'}"
                                        if prev.version != ext.version else "configuração mudou"))
                    events.append({"event": ev, "id": ext.id, "name": ext.name})
                    continue
                # unchanged config: keep evidence gathered by checks/sessions on top of what the file says
                if "desabilitado" not in ext.flags and "requer_aprovacao" not in ext.flags:
                    if STATES.index(prev_state) > STATES.index(ext.state):
                        ext.state = prev_state
                    ext.tools, ext.evidence, ext.last_verified = prev.tools, prev.evidence or ext.evidence, prev.last_verified
                    ext.flags = sorted(set(ext.flags) | (set(prev_flags) & PROBE_FLAGS))
                ext.details["_last_change"] = old["last_change"]
                if ext.state != prev_state or sorted(set(ext.flags)) != sorted(set(prev_flags)):
                    self.audit(db, ext.id, provider, ext.scope, "estado", self._status(prev_state, prev_flags),
                               self._status(ext.state, ext.flags))
                    events.append({"event": "estado", "id": ext.id, "name": ext.name})
                self._save(db, ext)
            for ext_id, row in stored.items():
                if ext_id in seen or row["removed_at"]:
                    continue
                prev = Extension.from_dict(json.loads(row["data"]))
                if prev.source in bad_sources or any(prev.source.startswith(b) for b in bad_sources if b):
                    continue            # its file could not be read right now: keep it, never "remove" by accident
                prev.state, prev.flags = row["state"], json.loads(row["flags"] or "[]")
                old_status = self._status(prev.state, prev.flags)
                prev.flags = sorted(set(prev.flags) | {"removido"})
                self._save(db, prev, removed=_now())
                self.audit(db, ext_id, provider, prev.scope, "removido", old_status, self._status(prev.state, prev.flags),
                           summary="não está mais na configuração do cliente")
                events.append({"event": "removido", "id": ext_id, "name": prev.name})
        return events

    # ------------------------------------------------------------------ evidence from checks and real sessions
    def update_checked(self, ext_id: str, state: str | None, add_flags=(), drop_flags=(), tools=None, evidence: str = "",
                       actor: str = "verificação") -> Extension | None:
        ext = self.get(ext_id)
        if ext is None:
            return None
        old = self._status(ext.state, ext.flags)
        if state:
            ext.state = state
        ext.flags = sorted((set(ext.flags) - set(drop_flags)) | set(add_flags))
        if tools is not None:
            ext.tools = list(tools)[:200]
        if evidence:
            ext.evidence = redact.value(evidence)[:600]
        ext.last_verified = _now()
        with self._db() as db:
            last = db.execute("SELECT last_change FROM extensions WHERE id=?", (ext_id,)).fetchone()
            ext.details["_last_change"] = last["last_change"] if last else _now()
            self._save(db, ext)
            new = self._status(ext.state, ext.flags)
            if new != old or evidence:
                self.audit(db, ext_id, ext.provider, ext.scope, "verificado", old, new, actor=actor, evidence=evidence,
                           summary=evidence)
        return ext

    def record_session(self, provider: str, init: dict, project: str = "") -> int:
        """A real CLI session reported what it loaded (Claude Code 'init' event): the strongest evidence there is."""
        tools = [str(t) for t in init.get("tools") or []]
        n = 0
        by_name = {}
        for e in self.all(include_removed=False):
            if e.provider == provider:
                by_name.setdefault((e.kind, e.name), []).append(e)
        for srv in init.get("mcp_servers") or []:
            name, status = str(srv.get("name", "")), str(srv.get("status", "")).lower()
            mine = [t.split("__", 2)[2] for t in tools if t.startswith(f"mcp__{name}__")]
            for e in by_name.get(("mcp", name), []):
                if e.project and project and e.project != project:
                    continue
                when = time.strftime("%d/%m %H:%M")
                if status == "connected":
                    self.update_checked(e.id, "capacidade_verificada" if mine else "conectado",
                                        drop_flags={"falha", "requer_login", "requer_reinicio", "indisponivel"},
                                        tools=mine or e.tools, actor="sessão real",
                                        evidence=f"sessão real do Claude Code ({when}): conectado, {len(mine)} ferramenta(s)")
                elif status in ("needs-auth", "needs_auth"):
                    self.update_checked(e.id, "carregado_na_sessao", add_flags={"requer_login"}, actor="sessão real",
                                        evidence=f"sessão real do Claude Code ({when}): precisa de login")
                elif status in ("pending",):
                    self.update_checked(e.id, None, add_flags={"requer_aprovacao"}, actor="sessão real",
                                        evidence=f"sessão real do Claude Code ({when}): aguardando aprovação")
                else:
                    self.update_checked(e.id, "carregado_na_sessao", add_flags={"falha"}, actor="sessão real",
                                        evidence=f"sessão real do Claude Code ({when}): {status or 'falhou'}")
                n += 1
        for kind, key in (("agent", "agents"), ("skill", "skills"), ("plugin", "plugins")):
            for item in init.get(key) or []:
                name = item.get("name") if isinstance(item, dict) else str(item)
                for e in by_name.get((kind, name), []):
                    if e.level() < STATES.index("carregado_na_sessao"):
                        self.update_checked(e.id, "carregado_na_sessao", drop_flags={"requer_reinicio"},
                                            actor="sessão real", evidence="aparece na sessão real do Claude Code")
                        n += 1
        return n

    def add_manual(self, ext: Extension, actor: str = "usuário") -> None:
        with self._db() as db:
            self._save(db, ext, first=_now())
            self.audit(db, ext.id, ext.provider, ext.scope, "registrado", "", self._status(ext.state, ext.flags),
                       actor=actor, summary=ext.evidence)

    def clear_history(self) -> None:
        with self._db() as db:
            db.execute("DELETE FROM audit")
            db.execute("DELETE FROM extensions WHERE removed_at IS NOT NULL")


def flag_label(f: str) -> str:
    from .model import LABELS
    return LABELS.get(f, f)


assert set(PROBE_FLAGS) <= set(FLAGS)
