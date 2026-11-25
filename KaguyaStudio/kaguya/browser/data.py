"""Favourites and history of the Kaguya Browser (local SQLite; nothing leaves the PC)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3
import threading
from urllib.parse import quote_plus, urlparse

SEARCH = {"duckduckgo": ("DuckDuckGo", "https://duckduckgo.com/?q={}"),
          "google": ("Google", "https://www.google.com/search?q={}"),
          "bing": ("Bing", "https://www.bing.com/search?q={}"),
          "youtube": ("YouTube", "https://www.youtube.com/results?search_query={}")}
HOME = "kaguya:inicio"


def to_url(text: str, engine: str = "duckduckgo") -> str:
    """What the user typed in the address bar → URL (an address, a local file, or a search)."""
    t = (text or "").strip()
    if not t:
        return HOME
    if t.startswith(("http://", "https://", "file:///", "about:", "kaguya:")):
        return t
    if " " not in t and ("." in t or t.startswith("localhost")) and not t.endswith("."):
        host = t.split("/")[0]
        if host.startswith("localhost") or "." in host:
            return ("http://" if host.startswith(("localhost", "127.")) else "https://") + t
    return SEARCH.get(engine, SEARCH["duckduckgo"])[1].format(quote_plus(t))


def host_of(url: str) -> str:
    try:
        return urlparse(url).hostname or ""
    except ValueError:
        return ""


class BrowserData:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS favorites(url TEXT PRIMARY KEY, title TEXT NOT NULL, folder TEXT NOT NULL
                    DEFAULT '', added_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT NOT NULL,
                    title TEXT NOT NULL, visited_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_history_time ON history(visited_at);
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

    # ------------------------------------------------------------- favourites
    def add_favorite(self, url: str, title: str, folder: str = "") -> None:
        with self._db() as db:
            db.execute("INSERT OR REPLACE INTO favorites(url,title,folder,added_at) VALUES(?,?,?,?)",
                       (url, (title or url)[:200], folder, datetime.now().isoformat(timespec="seconds")))

    def remove_favorite(self, url: str) -> None:
        with self._db() as db:
            db.execute("DELETE FROM favorites WHERE url=?", (url,))

    def is_favorite(self, url: str) -> bool:
        with self._db() as db:
            return db.execute("SELECT 1 FROM favorites WHERE url=?", (url,)).fetchone() is not None

    def favorites(self) -> list[dict]:
        with self._db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM favorites ORDER BY folder, title")]

    # ---------------------------------------------------------------- history
    def visit(self, url: str, title: str, private: bool = False) -> None:
        if private or not url or url.startswith(("about:", "kaguya:", "data:")):
            return
        with self._db() as db:
            last = db.execute("SELECT id, url FROM history ORDER BY id DESC LIMIT 1").fetchone()
            if last and last["url"] == url:   # same page reloaded / title arrived late: update, don't duplicate
                db.execute("UPDATE history SET title=?, visited_at=? WHERE id=?",
                           ((title or url)[:200], datetime.now().isoformat(timespec="seconds"), last["id"]))
                return
            db.execute("INSERT INTO history(url,title,visited_at) VALUES(?,?,?)",
                       (url, (title or url)[:200], datetime.now().isoformat(timespec="seconds")))

    def history(self, query: str = "", limit: int = 300) -> list[dict]:
        sql, args = "SELECT * FROM history", []
        if query.strip():
            sql += " WHERE url LIKE ? OR title LIKE ?"
            args += [f"%{query.strip()}%"] * 2
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        with self._db() as db:
            return [dict(r) for r in db.execute(sql, args)]

    def clear_history(self) -> None:
        with self._db() as db:
            db.execute("DELETE FROM history")

    def suggestions(self, prefix: str, limit: int = 8) -> list[str]:
        p = prefix.strip()
        if not p:
            return []
        with self._db() as db:
            rows = db.execute("SELECT url FROM favorites WHERE url LIKE ? OR title LIKE ? UNION "
                              "SELECT url FROM (SELECT url, MAX(id) m FROM history WHERE url LIKE ? OR title LIKE ? "
                              "GROUP BY url ORDER BY m DESC) LIMIT ?", (f"%{p}%",) * 4 + (limit,)).fetchall()
        return [r[0] for r in rows]
