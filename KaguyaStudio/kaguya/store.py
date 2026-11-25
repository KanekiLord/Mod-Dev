"""Persistent local state (SQLite): settings, projects, global vault, tasks, events,
agent sessions and usage snapshots.

Changes from V3.4 (the cause of the "não consigo vincular" reports):
* the Obsidian vault is a **global setting**; a project may override it, but it is no
  longer mandatory to pick both folders in one go;
* projects can be edited (name, folder, vault), unlinked, and re-linking the same folder
  updates it instead of being silently ignored (``INSERT OR IGNORE``);
* the V3 database is imported without being modified.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import threading

from .paths import normalize_user_path

SCHEMA_VERSION = 4

TASK_KINDS = ("execute", "later", "idea")
TARGETS = ("codex", "claude", "equipe", "paralelo")
FINAL_STATES = ("approved", "rejected", "pending_review", "executed", "error", "cancelled",
                "interrupted", "blocked_limit", "done")


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Store:
    def __init__(self, database: Path):
        self.path = Path(database).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS projects(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    directory TEXT NOT NULL UNIQUE,
                    vault TEXT,
                    test_command TEXT,
                    removed INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    parent_id INTEGER,
                    target TEXT NOT NULL,
                    title TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    allow_write INTEGER NOT NULL DEFAULT 0,
                    allow_web INTEGER NOT NULL DEFAULT 1,
                    allow_commands INTEGER NOT NULL DEFAULT 0,
                    allow_mcp INTEGER NOT NULL DEFAULT 0,
                    run_tests INTEGER NOT NULL DEFAULT 0,
                    started_at TEXT, finished_at TEXT,
                    result TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(project_id) REFERENCES projects(id)
                );
                CREATE TABLE IF NOT EXISTS events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    moment TEXT NOT NULL,
                    agent TEXT NOT NULL DEFAULT '',
                    kind TEXT NOT NULL,
                    message TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions(
                    project_id INTEGER NOT NULL,
                    agent TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(project_id, agent)
                );
                CREATE TABLE IF NOT EXISTS usage(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent TEXT NOT NULL,
                    source TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS local_usage(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent TEXT NOT NULL,
                    task_id INTEGER,
                    moment TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    cached_tokens INTEGER NOT NULL DEFAULT 0,
                    duration_ms INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_queue ON tasks(project_id, kind, status, id);
                CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id, id);
            """)
            db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema',?)", (str(SCHEMA_VERSION),))

    @contextmanager
    def connection(self):
        with self._lock:
            db = sqlite3.connect(str(self.path), timeout=15)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            try:
                with db:
                    yield db
            finally:
                db.close()

    # ---------------------------------------------------------------- settings
    def get_setting(self, key: str, default=None):
        with self.connection() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except ValueError:
            return default

    def set_setting(self, key: str, value) -> None:
        with self.connection() as db:
            if value is None:
                db.execute("DELETE FROM settings WHERE key=?", (key,))
            else:
                db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
                           (key, json.dumps(value, ensure_ascii=False)))

    # ------------------------------------------------------------------- vault
    def global_vault(self) -> str | None:
        return self.get_setting("vault.global")

    def set_global_vault(self, path) -> str | None:
        if path in (None, ""):
            self.set_setting("vault.global", None)
            return None
        value = str(normalize_user_path(path))
        self.set_setting("vault.global", value)
        return value

    # ---------------------------------------------------------------- projects
    def add_project(self, name: str, directory, vault=None) -> int:
        """Link (or re-link) a project. The vault is optional; existence is checked by the UI
        through :mod:`kaguya.paths` so the user sees a specific diagnosis."""
        directory = str(normalize_user_path(directory))
        vault_value = str(normalize_user_path(vault)) if vault not in (None, "") else None
        label = (name or "").strip() or Path(directory).name or directory
        stamp = now()
        with self.connection() as db:
            row = db.execute("SELECT id FROM projects WHERE directory=?", (directory,)).fetchone()
            if row:
                db.execute("UPDATE projects SET name=?, vault=COALESCE(?, vault), removed=0, updated_at=? WHERE id=?",
                           (label, vault_value, stamp, row["id"]))
                return int(row["id"])
            cur = db.execute("INSERT INTO projects(name,directory,vault,created_at,updated_at) VALUES(?,?,?,?,?)",
                             (label, directory, vault_value, stamp, stamp))
            return int(cur.lastrowid)

    def update_project(self, pid: int, *, name: str | None = None, directory=None,
                       vault=..., test_command=...) -> None:
        sets, values = [], []
        if name is not None:
            sets.append("name=?"); values.append(name.strip() or "Projeto")
        if directory is not None:
            sets.append("directory=?"); values.append(str(normalize_user_path(directory)))
        if vault is not ...:
            sets.append("vault=?"); values.append(str(normalize_user_path(vault)) if vault else None)
        if test_command is not ...:
            sets.append("test_command=?"); values.append((test_command or "").strip() or None)
        if not sets:
            return
        sets.append("updated_at=?"); values.append(now())
        with self.connection() as db:
            try:
                db.execute(f"UPDATE projects SET {', '.join(sets)} WHERE id=?", (*values, pid))
            except sqlite3.IntegrityError as exc:
                raise ValueError("Essa pasta já está vinculada a outro projeto.") from exc

    def remove_project(self, pid: int) -> None:
        """Unlink only: tasks/history stay in the database, files are untouched."""
        with self.connection() as db:
            db.execute("UPDATE tasks SET status='cancelled', finished_at=? WHERE project_id=? AND status IN ('queued','running')",
                       (now(), pid))
            db.execute("DELETE FROM sessions WHERE project_id=?", (pid,))
            db.execute("UPDATE projects SET removed=1, updated_at=? WHERE id=?", (now(), pid))

    def projects(self, include_removed: bool = False) -> list[dict]:
        where = "" if include_removed else " WHERE removed=0"
        with self.connection() as db:
            return [dict(r) for r in db.execute(f"SELECT * FROM projects{where} ORDER BY name COLLATE NOCASE, id")]

    def project(self, pid: int) -> dict:
        with self.connection() as db:
            row = db.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if row is None:
            raise ValueError("Projeto não encontrado")
        return dict(row)

    def effective_vault(self, pid: int | None) -> str | None:
        if pid is not None:
            proj = self.project(pid)
            if proj.get("vault"):
                return proj["vault"]
        return self.global_vault()

    # ------------------------------------------------------------------- tasks
    def enqueue(self, pid: int, target: str, title: str, kind: str = "execute", *,
                allow_write: bool = False, allow_web: bool = True, allow_commands: bool = False,
                allow_mcp: bool = False, run_tests: bool = False, parent_id: int | None = None) -> int:
        if kind not in TASK_KINDS or target not in TARGETS:
            raise ValueError("Tipo ou destino não reconhecido")
        status = "queued" if kind == "execute" else "parked"
        with self.connection() as db:
            cur = db.execute(
                "INSERT INTO tasks(project_id,parent_id,target,title,kind,status,created_at,allow_write,allow_web,"
                "allow_commands,allow_mcp,run_tests) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (pid, parent_id, target, title, kind, status, now(), int(allow_write), int(allow_web),
                 int(allow_commands), int(allow_mcp), int(run_tests)))
            return int(cur.lastrowid)

    def claim(self, pid: int) -> dict | None:
        """Take the next queued task. One running task per project (parallel work happens
        inside a task, in isolated worktrees)."""
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM tasks WHERE project_id=? AND status='running' AND parent_id IS NULL",
                          (pid,)).fetchone():
                return None
            row = db.execute("SELECT * FROM tasks WHERE project_id=? AND kind='execute' AND status='queued' "
                             "AND parent_id IS NULL ORDER BY id LIMIT 1", (pid,)).fetchone()
            if row is None:
                return None
            started = now()
            db.execute("UPDATE tasks SET status='running', started_at=? WHERE id=?", (started, row["id"]))
            task = dict(row)
            task.update(status="running", started_at=started)
            return task

    def set_stage(self, tid: int, stage: str) -> None:
        with self.connection() as db:
            db.execute("UPDATE tasks SET stage=? WHERE id=?", (stage, tid))

    def complete(self, tid: int, status: str, result: str = "") -> None:
        if status not in FINAL_STATES:
            raise ValueError("Estado inválido")
        with self.connection() as db:
            db.execute("UPDATE tasks SET status=?, finished_at=?, result=? WHERE id=?",
                       (status, now(), result[:40000], tid))

    def get_task(self, tid: int) -> dict:
        with self.connection() as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
        if row is None:
            raise ValueError("Tarefa não encontrada")
        return dict(row)

    def tasks(self, pid: int, limit: int = 200) -> list[dict]:
        with self.connection() as db:
            return [dict(r) for r in db.execute(
                "SELECT * FROM tasks WHERE project_id=? ORDER BY id DESC LIMIT ?", (pid, limit))]

    def pending_count(self, pid: int) -> int:
        with self.connection() as db:
            return int(db.execute("SELECT COUNT(*) FROM tasks WHERE project_id=? AND status IN ('queued','running','parked')",
                                  (pid,)).fetchone()[0])

    def recover_interrupted(self) -> int:
        with self.connection() as db:
            cur = db.execute("UPDATE tasks SET status='interrupted', finished_at=? WHERE status='running'", (now(),))
            return cur.rowcount

    def activate_later(self, tid: int, **perms) -> bool:
        fields = {k: int(bool(v)) for k, v in perms.items()
                  if k in ("allow_write", "allow_web", "allow_commands", "allow_mcp", "run_tests")}
        sets = ", ".join(f"{k}=?" for k in fields)
        with self.connection() as db:
            cur = db.execute(
                "UPDATE tasks SET kind='execute', status='queued'" + (", " + sets if sets else "") +
                " WHERE id=? AND kind IN ('later','idea') AND status='parked'", (*fields.values(), tid))
            return cur.rowcount == 1

    def requeue(self, tid: int) -> bool:
        with self.connection() as db:
            cur = db.execute("UPDATE tasks SET status='queued', stage='', finished_at=NULL WHERE id=? AND "
                             "status IN ('interrupted','error','cancelled','blocked_limit')", (tid,))
            return cur.rowcount == 1

    def cancel_queued(self, tid: int) -> bool:
        with self.connection() as db:
            cur = db.execute("UPDATE tasks SET status='cancelled', finished_at=? WHERE id=? AND status IN ('queued','parked')",
                             (now(), tid))
            return cur.rowcount == 1

    # ------------------------------------------------------------------ events
    def append_event(self, tid: int, kind: str, message: str, agent: str = "") -> None:
        with self.connection() as db:
            db.execute("INSERT INTO events(task_id,moment,agent,kind,message) VALUES(?,?,?,?,?)",
                       (tid, now(), agent, kind, message[:16000]))

    def events(self, tid: int, limit: int = 500) -> list[dict]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM events WHERE task_id=? ORDER BY id DESC LIMIT ?", (tid, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]

    def project_history(self, pid: int, limit: int = 400) -> list[dict]:
        """Conversation-like history of a project (for the chat view after restart)."""
        with self.connection() as db:
            rows = db.execute(
                "SELECT e.*, t.title, t.target FROM events e JOIN tasks t ON t.id=e.task_id "
                "WHERE t.project_id=? AND e.kind IN ('user','message','verdict','system','error') "
                "ORDER BY e.id DESC LIMIT ?", (pid, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]

    # ---------------------------------------------------------------- sessions
    def session(self, pid: int, agent: str) -> str | None:
        with self.connection() as db:
            row = db.execute("SELECT session_id FROM sessions WHERE project_id=? AND agent=?", (pid, agent)).fetchone()
        return row["session_id"] if row else None

    def set_session(self, pid: int, agent: str, session_id: str | None) -> None:
        with self.connection() as db:
            if not session_id:
                db.execute("DELETE FROM sessions WHERE project_id=? AND agent=?", (pid, agent))
            else:
                db.execute("INSERT OR REPLACE INTO sessions(project_id,agent,session_id,updated_at) VALUES(?,?,?,?)",
                           (pid, agent, session_id, now()))

    # ------------------------------------------------------------------- usage
    def save_usage(self, agent: str, source: str, payload: dict) -> None:
        with self.connection() as db:
            db.execute("INSERT INTO usage(agent,source,captured_at,payload) VALUES(?,?,?,?)",
                       (agent, source, now(), json.dumps(payload, ensure_ascii=False)))
            db.execute("DELETE FROM usage WHERE agent=? AND id NOT IN (SELECT id FROM usage WHERE agent=? ORDER BY id DESC LIMIT 50)",
                       (agent, agent))

    def latest_usage(self, agent: str) -> dict | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM usage WHERE agent=? ORDER BY id DESC LIMIT 1", (agent,)).fetchone()
        if not row:
            return None
        data = dict(row)
        data["payload"] = json.loads(data["payload"])
        return data

    def add_local_usage(self, agent: str, task_id: int | None, input_tokens: int = 0, output_tokens: int = 0,
                        cached_tokens: int = 0, duration_ms: int = 0) -> None:
        with self.connection() as db:
            db.execute("INSERT INTO local_usage(agent,task_id,moment,input_tokens,output_tokens,cached_tokens,duration_ms)"
                       " VALUES(?,?,?,?,?,?,?)", (agent, task_id, now(), int(input_tokens or 0), int(output_tokens or 0),
                                                 int(cached_tokens or 0), int(duration_ms or 0)))

    def local_usage_since(self, agent: str, since_iso: str) -> dict:
        with self.connection() as db:
            row = db.execute("SELECT COUNT(*) runs, COALESCE(SUM(input_tokens),0) inp, COALESCE(SUM(output_tokens),0) outp,"
                             " COALESCE(SUM(cached_tokens),0) cached, COALESCE(SUM(duration_ms),0) dur FROM local_usage"
                             " WHERE agent=? AND moment>=?", (agent, since_iso)).fetchone()
        return {"runs": row["runs"], "input_tokens": row["inp"], "output_tokens": row["outp"],
                "cached_tokens": row["cached"], "duration_ms": row["dur"]}

    # --------------------------------------------------------------- migration
    def import_v3(self, legacy_db: Path) -> dict:
        """Copy projects/tasks from a V3.x database (opened read-only, never modified)."""
        report = {"projects": 0, "tasks": 0, "vault": None}
        if self.get_setting("migration.v3.done"):
            return report
        uri = Path(legacy_db).resolve().as_uri() + "?mode=ro"
        try:
            old = sqlite3.connect(uri, uri=True)
            old.row_factory = sqlite3.Row
        except sqlite3.Error:
            return report
        try:
            projects = [dict(r) for r in old.execute("SELECT * FROM projects ORDER BY id")]
            id_map = {}
            vaults = []
            for p in projects:
                id_map[p["id"]] = self.add_project(p.get("name") or "", p["directory"], None)
                if p.get("vault"):
                    vaults.append(p["vault"])
                    self.update_project(id_map[p["id"]], vault=p["vault"])
                report["projects"] += 1
            if vaults and not self.global_vault():
                # most used vault becomes the global one; project overrides are kept.
                existing = [v for v in vaults if Path(v).is_dir()]
                pool = existing or vaults
                best = max(sorted(set(pool)), key=pool.count)
                self.set_global_vault(best)
                report["vault"] = best
                for pid in id_map.values():
                    if self.project(pid).get("vault") == best:
                        self.update_project(pid, vault=None)
            cols = {r["name"] for r in old.execute("PRAGMA table_info(tasks)")}
            for t in old.execute("SELECT * FROM tasks ORDER BY id"):
                t = dict(t)
                if t["project_id"] not in id_map:
                    continue
                status = t["status"]
                if t["kind"] in ("later", "idea"):
                    status = "parked" if status == "parked" else status
                elif status in ("queued", "running"):
                    status = "interrupted"
                with self.connection() as db:
                    db.execute("INSERT INTO tasks(project_id,target,title,kind,status,created_at,allow_write,allow_web,"
                               "started_at,finished_at,result) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                               (id_map[t["project_id"]], t["target"] if t["target"] in TARGETS else "equipe",
                                t["title"], t["kind"], status, t["created_at"],
                                int(t.get("allow_write", 0)) if "allow_write" in cols else 0,
                                int(t.get("allow_web", 1)) if "allow_web" in cols else 1,
                                t.get("started_at"), t.get("finished_at"), t.get("result") or ""))
                report["tasks"] += 1
        except sqlite3.Error:
            pass
        finally:
            old.close()
        self.set_setting("migration.v3.done", True)
        return report
