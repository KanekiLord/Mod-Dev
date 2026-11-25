"""Local music library (SQLite): tracks found in folders the user chose, favourites, playlists and history.

Nothing is copied or modified: only paths and metadata are stored.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import re
import sqlite3
import threading
import unicodedata

AUDIO_EXT = {".mp3", ".flac", ".wav", ".ogg", ".oga", ".opus", ".m4a", ".aac", ".wma"}
MAX_TRACKS = 20000


def norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    return re.sub(r"\s+", " ", "".join(c for c in t if not unicodedata.combining(c)).lower()).strip()


def guess_meta(path: Path) -> tuple[str, str]:
    """'Artista - Título.mp3' → (título, artista); otherwise (nome do arquivo, pasta)."""
    stem = re.sub(r"^\d{1,3}[\s._-]+", "", path.stem).replace("_", " ").strip()
    if " - " in stem:
        artist, title = stem.split(" - ", 1)
        return title.strip(), artist.strip()
    return stem, path.parent.name


@dataclass
class Track:
    id: int
    path: str
    title: str
    artist: str
    album: str
    duration_ms: int
    favorite: bool
    plays: int

    @property
    def label(self) -> str:
        return f"{self.title} — {self.artist}" if self.artist else self.title


class MusicLibrary:
    def __init__(self, db_path: Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS folders(path TEXT PRIMARY KEY, added_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tracks(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
                    artist TEXT NOT NULL DEFAULT '', album TEXT NOT NULL DEFAULT '', duration_ms INTEGER NOT NULL DEFAULT 0,
                    folder TEXT NOT NULL DEFAULT '', search TEXT NOT NULL DEFAULT '', favorite INTEGER NOT NULL DEFAULT 0,
                    plays INTEGER NOT NULL DEFAULT 0, last_played TEXT, added_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS playlists(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS playlist_items(playlist_id INTEGER NOT NULL, track_id INTEGER NOT NULL,
                    pos INTEGER NOT NULL, PRIMARY KEY(playlist_id, track_id));
            """)

    def _db(self):
        lock = self._lock

        class Ctx:
            def __enter__(s):
                lock.acquire()
                s.db = sqlite3.connect(str(self.path), timeout=15)
                s.db.row_factory = sqlite3.Row
                return s.db

            def __exit__(s, et, ev, tb):
                try:
                    if et is None:
                        s.db.commit()
                    s.db.close()
                finally:
                    lock.release()
        return Ctx()

    # ------------------------------------------------------------------ folders
    def folders(self) -> list[str]:
        with self._db() as db:
            return [r["path"] for r in db.execute("SELECT path FROM folders ORDER BY path")]

    def add_folder(self, folder, progress=None) -> int:
        """Scan a folder (recursively). Returns how many tracks were added."""
        folder = str(Path(folder).expanduser().resolve())
        if not Path(folder).is_dir():
            raise ValueError(f"Pasta não encontrada: {folder}")
        now = datetime.now().isoformat(timespec="seconds")
        added = 0
        with self._db() as db:
            db.execute("INSERT OR IGNORE INTO folders(path, added_at) VALUES(?,?)", (folder, now))
            known = {r["path"] for r in db.execute("SELECT path FROM tracks")}
            for root, dirs, files in os.walk(folder):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for f in files:
                    p = Path(root) / f
                    if p.suffix.lower() not in AUDIO_EXT or str(p) in known:
                        continue
                    if len(known) + added >= MAX_TRACKS:
                        return added
                    title, artist = guess_meta(p)
                    db.execute("INSERT OR IGNORE INTO tracks(path,title,artist,folder,search,added_at) VALUES(?,?,?,?,?,?)",
                               (str(p), title, artist, folder, norm(f"{title} {artist} {p.parent.name}"), now))
                    added += 1
                    if progress and added % 50 == 0:
                        progress(added)
        return added

    def remove_folder(self, folder: str) -> None:
        with self._db() as db:
            db.execute("DELETE FROM folders WHERE path=?", (folder,))
            ids = [r["id"] for r in db.execute("SELECT id FROM tracks WHERE folder=?", (folder,))]
            db.executemany("DELETE FROM playlist_items WHERE track_id=?", [(i,) for i in ids])
            db.execute("DELETE FROM tracks WHERE folder=?", (folder,))

    def prune_missing(self) -> int:
        with self._db() as db:
            gone = [r["id"] for r in db.execute("SELECT id, path FROM tracks") if not Path(r["path"]).exists()]
            db.executemany("DELETE FROM tracks WHERE id=?", [(i,) for i in gone])
            db.executemany("DELETE FROM playlist_items WHERE track_id=?", [(i,) for i in gone])
        return len(gone)

    # ------------------------------------------------------------------- tracks
    @staticmethod
    def _track(r) -> Track:
        return Track(r["id"], r["path"], r["title"], r["artist"], r["album"], r["duration_ms"], bool(r["favorite"]),
                     r["plays"])

    def tracks(self, query: str = "", limit: int = 2000, favorites: bool = False) -> list[Track]:
        sql, args = "SELECT * FROM tracks", []
        where = []
        for word in norm(query).split()[:6]:
            where.append("search LIKE ?")
            args.append(f"%{word}%")
        if favorites:
            where.append("favorite=1")
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY artist, title LIMIT ?"
        args.append(limit)
        with self._db() as db:
            return [self._track(r) for r in db.execute(sql, args)]

    def get(self, tid: int) -> Track | None:
        with self._db() as db:
            r = db.execute("SELECT * FROM tracks WHERE id=?", (tid,)).fetchone()
        return self._track(r) if r else None

    def by_path(self, path: str) -> Track | None:
        with self._db() as db:
            r = db.execute("SELECT * FROM tracks WHERE path=?", (path,)).fetchone()
        return self._track(r) if r else None

    def count(self) -> int:
        with self._db() as db:
            return int(db.execute("SELECT COUNT(*) FROM tracks").fetchone()[0])

    def update_meta(self, tid: int, title: str = "", artist: str = "", album: str = "", duration_ms: int = 0) -> None:
        t = self.get(tid)
        if not t:
            return
        title, artist, album = title or t.title, artist or t.artist, album or t.album
        with self._db() as db:
            db.execute("UPDATE tracks SET title=?, artist=?, album=?, duration_ms=CASE WHEN ?>0 THEN ? ELSE duration_ms END,"
                       " search=? WHERE id=?", (title, artist, album, duration_ms, duration_ms,
                                                norm(f"{title} {artist} {album} {Path(t.path).parent.name}"), tid))

    def played(self, tid: int) -> None:
        with self._db() as db:
            db.execute("UPDATE tracks SET plays=plays+1, last_played=? WHERE id=?",
                       (datetime.now().isoformat(timespec="seconds"), tid))

    def set_favorite(self, tid: int, on: bool) -> None:
        with self._db() as db:
            db.execute("UPDATE tracks SET favorite=? WHERE id=?", (int(on), tid))

    def search(self, query: str, limit: int = 30) -> list[Track]:
        """Best matches for a spoken/typed query (all words, then any word)."""
        found = self.tracks(query, limit)
        if found or not query.strip():
            return found
        words = [w for w in norm(query).split() if len(w) > 2]
        seen, out = set(), []
        for w in words:
            for t in self.tracks(w, limit):
                if t.id not in seen:
                    seen.add(t.id)
                    out.append(t)
        return out[:limit]

    # ---------------------------------------------------------------- playlists
    def playlists(self) -> list[dict]:
        with self._db() as db:
            return [dict(r) for r in db.execute(
                "SELECT p.id, p.name, COUNT(i.track_id) AS n FROM playlists p LEFT JOIN playlist_items i "
                "ON i.playlist_id=p.id GROUP BY p.id ORDER BY p.name")]

    def create_playlist(self, name: str) -> int:
        name = name.strip()[:80]
        if not name:
            raise ValueError("Dê um nome à playlist.")
        with self._db() as db:
            db.execute("INSERT OR IGNORE INTO playlists(name, created_at) VALUES(?,?)",
                       (name, datetime.now().isoformat(timespec="seconds")))
            return int(db.execute("SELECT id FROM playlists WHERE name=?", (name,)).fetchone()[0])

    def delete_playlist(self, pid: int) -> None:
        with self._db() as db:
            db.execute("DELETE FROM playlist_items WHERE playlist_id=?", (pid,))
            db.execute("DELETE FROM playlists WHERE id=?", (pid,))

    def add_to_playlist(self, pid: int, track_ids: list[int]) -> None:
        with self._db() as db:
            pos = int(db.execute("SELECT COALESCE(MAX(pos), -1) FROM playlist_items WHERE playlist_id=?",
                                 (pid,)).fetchone()[0])
            for tid in track_ids:
                pos += 1
                db.execute("INSERT OR IGNORE INTO playlist_items(playlist_id, track_id, pos) VALUES(?,?,?)",
                           (pid, tid, pos))

    def playlist_tracks(self, pid: int) -> list[Track]:
        with self._db() as db:
            return [self._track(r) for r in db.execute(
                "SELECT t.* FROM playlist_items i JOIN tracks t ON t.id=i.track_id WHERE i.playlist_id=? ORDER BY i.pos",
                (pid,))]

    def find_playlist(self, query: str) -> dict | None:
        q = norm(query)
        best = None
        for p in self.playlists():
            n = norm(p["name"])
            if n == q:
                return p
            if q and (q in n or n in q) and best is None:
                best = p
        return best
