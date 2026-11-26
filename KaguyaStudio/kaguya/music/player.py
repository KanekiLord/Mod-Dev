"""The Studio's own music player (QtMultimedia): local files, queue, shuffle/repeat, volume and ducking."""
from __future__ import annotations

import random
from pathlib import Path
from urllib.parse import quote_plus

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QImage

from .commands import parse
from .library import MusicLibrary, Track

REPEAT = ("off", "all", "one")


class MusicPlayer(QObject):
    changed = Signal()                 # track, state, queue, volume
    position = Signal(int, int)        # ms, duration ms

    def __init__(self, library: MusicLibrary, store=None, parent=None):
        super().__init__(parent)
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        self.lib, self.store = library, store
        self.player = QMediaPlayer(self)
        self.out = QAudioOutput(self)
        self.player.setAudioOutput(self.out)
        self.queue: list[int] = []
        self._ordered: list[int] | None = None   # order before shuffling (restored when shuffle goes off)
        self.index = -1
        self.shuffle = bool(self._get("music.shuffle", False))
        self.repeat = self._get("music.repeat", "off") if self._get("music.repeat", "off") in REPEAT else "off"
        self.volume = int(self._get("music.volume", 70))
        self.duck_level = int(self._get("music.duck_level", 25))   # % of the current volume while an AI speaks
        self.ducked = False
        self.track: Track | None = None
        self.cover: QImage | None = None
        self.last_error = ""
        self._apply_volume()
        self.player.mediaStatusChanged.connect(self._status)
        self.player.playbackStateChanged.connect(lambda *_: self.changed.emit())
        self.player.positionChanged.connect(lambda ms: self.position.emit(ms, self.player.duration()))
        self.player.errorOccurred.connect(self._error)

    def _get(self, key, default):
        return self.store.get_setting(key, default) if self.store else default

    def _set(self, key, value):
        if self.store:
            self.store.set_setting(key, value)

    # ------------------------------------------------------------------ state
    @property
    def playing(self) -> bool:
        from PySide6.QtMultimedia import QMediaPlayer
        return self.player.playbackState() == QMediaPlayer.PlayingState

    def status(self) -> dict:
        t = self.track
        return {"source": "local", "state": "playing" if self.playing else ("paused" if t else "stopped"),
                "title": t.title if t else "", "artist": t.artist if t else "", "path": t.path if t else "",
                "position_ms": self.player.position(), "duration_ms": self.player.duration(),
                "volume": self.volume, "ducked": self.ducked, "queue": len(self.queue),
                "index": self.index, "shuffle": self.shuffle, "repeat": self.repeat}

    # --------------------------------------------------------------- playback
    def play_tracks(self, ids: list[int], start: int = 0) -> bool:
        ids = [i for i in ids if i]
        if not ids:
            return False
        self.queue = list(ids)
        self._ordered = list(ids)
        if self.shuffle:
            first = self.queue.pop(start)
            random.shuffle(self.queue)
            self.queue.insert(0, first)
            start = 0
        return self._play_index(start)

    def _play_index(self, i: int) -> bool:
        if not (0 <= i < len(self.queue)):
            return False
        t = self.lib.get(self.queue[i])
        if t is None or not Path(t.path).exists():
            self.last_error = "Arquivo não encontrado (foi movido ou apagado)."
            self.queue.pop(i)
            return self._play_index(i) if i < len(self.queue) else False
        self.index, self.track, self.cover = i, t, None
        self.player.setSource(QUrl.fromLocalFile(t.path))
        self.player.play()
        self.lib.played(t.id)
        self.changed.emit()
        return True

    def toggle(self):
        if self.playing:
            self.pause()
        else:
            self.resume()

    def pause(self):
        self.player.pause()

    def resume(self) -> bool:
        if self.track is None:
            return self.play_tracks([t.id for t in self.lib.tracks(limit=500)])
        self.player.play()
        return True

    def next(self) -> bool:
        if not self.queue:
            return False
        if self.index + 1 < len(self.queue):
            return self._play_index(self.index + 1)
        if self.repeat == "all":
            return self._play_index(0)
        self.player.stop()
        return False

    def previous(self) -> bool:
        if self.player.position() > 3000 or self.index <= 0:
            self.player.setPosition(0)
            return True
        return self._play_index(self.index - 1)

    def seek(self, ms: int):
        self.player.setPosition(max(0, int(ms)))

    def queue_add(self, ids: list[int]):
        self.queue.extend(i for i in ids if i)
        if self.track is None and self.queue:
            self._play_index(0)
        self.changed.emit()

    def set_shuffle(self, on: bool):
        """Takes effect now: the songs after the current one are shuffled (the current one keeps
        playing); turning it off restores the original order from the current song on."""
        on = bool(on)
        if on and not self.shuffle and self.queue:
            self._ordered = list(self.queue)
            cur = self.queue[self.index] if 0 <= self.index < len(self.queue) else None
            rest = [t for i, t in enumerate(self.queue) if i != self.index]
            random.shuffle(rest)
            self.queue = ([cur] if cur is not None else []) + rest
            self.index = 0 if cur is not None else -1
        elif not on and self.shuffle and getattr(self, "_ordered", None):
            cur = self.queue[self.index] if 0 <= self.index < len(self.queue) else None
            self.queue = list(self._ordered)
            self.index = self.queue.index(cur) if cur in self.queue else -1
            self._ordered = None
        self.shuffle = on
        self._set("music.shuffle", self.shuffle)
        self.changed.emit()

    def cycle_repeat(self) -> str:
        self.repeat = REPEAT[(REPEAT.index(self.repeat) + 1) % len(REPEAT)]
        self._set("music.repeat", self.repeat)
        self.changed.emit()
        return self.repeat

    # ---------------------------------------------------------------- volume
    def set_volume(self, v: int):
        self.volume = max(0, min(100, int(v)))
        self._set("music.volume", self.volume)
        self._apply_volume()
        self.changed.emit()

    def duck(self, on: bool):
        """Lower the music while an assistant speaks; always restorable (on=False)."""
        if self.ducked != bool(on):
            self.ducked = bool(on)
            self._apply_volume()
            self.changed.emit()

    def _apply_volume(self):
        level = self.volume * (self.duck_level / 100 if self.ducked else 1)
        self.out.setVolume(max(0.0, min(1.0, level / 100)))

    # ----------------------------------------------------------------- events
    def _status(self, status):
        from PySide6.QtMultimedia import QMediaMetaData, QMediaPlayer
        if status == QMediaPlayer.LoadedMedia and self.track:
            md = self.player.metaData()
            title = md.stringValue(QMediaMetaData.Title)
            artist = md.stringValue(QMediaMetaData.ContributingArtist) or md.stringValue(QMediaMetaData.AlbumArtist)
            album = md.stringValue(QMediaMetaData.AlbumTitle)
            for key in (QMediaMetaData.ThumbnailImage, QMediaMetaData.CoverArtImage):
                img = md.value(key)
                if isinstance(img, QImage) and not img.isNull():
                    self.cover = img
                    break
            self.lib.update_meta(self.track.id, title, artist, album, self.player.duration())
            self.track = self.lib.get(self.track.id)
            self.changed.emit()
        elif status == QMediaPlayer.EndOfMedia:
            if self.repeat == "one":
                self.player.setPosition(0)
                self.player.play()
            else:
                self.next()

    def _error(self, _err, text):
        self.last_error = text or "Não foi possível tocar este arquivo."
        self.changed.emit()

    # -------------------------------------------------------------- commands
    def execute(self, action: str, arg: str = "", open_url=None) -> str:
        """Run a parsed command and return a short reply (shown in chat / spoken)."""
        if action == "pause":
            self.pause()
            return "Música pausada."
        if action == "resume":
            return "Voltando a tocar." if self.resume() else "Não há músicas na biblioteca ainda (Kaguya Music › Adicionar pasta)."
        if action == "next":
            return "Próxima música." if self.next() else "Fim da fila."
        if action == "previous":
            self.previous()
            return "Voltando."
        if action == "volume":
            self.set_volume(int(arg))
            return f"Volume da música em {self.volume}%."
        if action in ("volume_down", "volume_up"):
            self.set_volume(self.volume + (-15 if action == "volume_down" else 15))
            return f"Volume da música em {self.volume}%."
        if action == "shuffle":
            self.set_shuffle(arg != "off")
            return "Modo aleatório ligado." if self.shuffle else "Modo aleatório desligado."
        if action == "status":
            s = self.status()
            return (f"Tocando {s['title']}" + (f", de {s['artist']}" if s["artist"] else "") + ".") if s["title"] else \
                "Nada tocando no Kaguya Music."
        if action == "playlist":
            p = self.lib.find_playlist(arg)
            if p:
                ids = [t.id for t in self.lib.playlist_tracks(p["id"])]
                if self.play_tracks(ids):
                    return f"Tocando a playlist {p['name']}."
                return f"A playlist {p['name']} está vazia."
            action = "play"  # no playlist with that name: search the tracks instead
        if action == "play":
            found = self.lib.search(arg) if arg else self.lib.tracks(limit=500)
            if not found:
                if self.lib.count() == 0:
                    return "Sua biblioteca está vazia: adicione uma pasta de músicas no Kaguya Music."
                return f"Não achei \"{arg}\" nas suas músicas locais."
            self.play_tracks([t.id for t in found])
            t = self.track
            return f"Tocando {t.label}." if t else "Tocando."
        if action == "queue":
            found = self.lib.search(arg)
            if not found:
                return f"Não achei \"{arg}\" nas suas músicas locais."
            self.queue_add([found[0].id])
            return f"{found[0].label} entrou na fila."
        if action == "external":
            site = "spotify" if "spotify" in arg else "amazon" if "amazon" in arg else "youtube"
            q = arg
            for w in ("no youtube", "no spotify", "no amazon music", "no amazon", "youtube", "spotify", "amazon"):
                q = q.replace(w, "")
            q = q.strip()
            url = {"youtube": f"https://www.youtube.com/results?search_query={quote_plus(q)}",
                   "spotify": f"https://open.spotify.com/search/{quote_plus(q)}",
                   "amazon": f"https://music.amazon.com/search/{quote_plus(q)}"}[site]
            if open_url:
                open_url(url)
            nice = {"youtube": "YouTube", "spotify": "Spotify", "amazon": "Amazon Music"}[site]
            return (f"Abri a busca \"{q}\" no {nice} — escolha e dê play por lá. O Studio só toca arquivos "
                    "locais e não toca vídeos escondidos.")
        return ""

    def handle_text(self, text: str, open_url=None) -> str | None:
        """Chat/voice entry point: returns a reply when the text was a music command."""
        cmd = parse(text)
        if not cmd:
            return None
        return self.execute(*cmd, open_url=open_url)
