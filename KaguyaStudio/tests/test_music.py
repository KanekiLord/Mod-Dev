"""Kaguya Music: library, playlists, local commands and the real QtMultimedia player."""
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest
import wave

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kaguya.music.commands import parse  # noqa: E402
from kaguya.music.library import MusicLibrary  # noqa: E402

try:
    from PySide6.QtMultimedia import QMediaPlayer  # noqa: F401
    HAVE_MM = True
except Exception:  # pragma: no cover
    HAVE_MM = False


def tone(path: Path, seconds: float = 0.6, hz: int = 440):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"".join(struct.pack("<h", int(6000 * math.sin(2 * math.pi * hz * i / 16000)))
                               for i in range(int(16000 * seconds))))


class LibraryAndCommands(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "Músicas"
        tone(self.root / "Ikimono-gakari - Blue Bird.wav")
        tone(self.root / "Animes" / "02 - Naruto Opening.wav")
        tone(self.root / ".oculto" / "secreta.wav")
        (self.root / "capa.jpg").write_bytes(b"x")
        self.lib = MusicLibrary(Path(self.tmp.name) / "m.db")

    def test_scan_search_playlists_favorites(self):
        self.assertEqual(self.lib.add_folder(self.root), 2)        # hidden folders and non-audio ignored
        self.assertEqual(self.lib.add_folder(self.root), 0)        # rescanning does not duplicate
        bb = self.lib.search("blue bird")[0]
        self.assertEqual((bb.title, bb.artist), ("Blue Bird", "Ikimono-gakari"))
        self.assertEqual(self.lib.search("naruto")[0].title, "Naruto Opening")
        self.assertEqual(self.lib.search("bird ikimono")[0].id, bb.id)
        pid = self.lib.create_playlist("Foco & Produção")
        self.lib.add_to_playlist(pid, [bb.id])
        self.assertEqual(self.lib.find_playlist("foco")["id"], pid)
        self.assertEqual([t.id for t in self.lib.playlist_tracks(pid)], [bb.id])
        self.lib.set_favorite(bb.id, True)
        self.assertEqual([t.id for t in self.lib.tracks(favorites=True)], [bb.id])
        (self.root / "Ikimono-gakari - Blue Bird.wav").unlink()
        self.assertEqual(self.lib.prune_missing(), 1)
        self.assertEqual(self.lib.playlist_tracks(pid), [])

    def test_commands_are_understood_locally(self):
        cases = {"Pausa a música": ("pause", ""), "próxima": ("next", ""), "Volume 30%": ("volume", "30"),
                 "Diminui a música para 30%": ("volume", "30"), "toca minhas trilhas locais": ("play", ""),
                 "Kaguya, toca a playlist Foco": ("playlist", "foco"), "toca Blue Bird": ("play", "blue bird"),
                 "coloca Blue Bird na fila para depois": ("queue", "blue bird"),
                 "pausa a música enquanto conversamos": ("pause", ""), "que música é essa": ("status", "")}
        for text, want in cases.items():
            self.assertEqual(parse(text), want, text)
        self.assertEqual(parse("Miwa, coloca uma abertura de Naruto no YouTube")[0], "external")
        for text in ("coloca o botão no menu", "implemente o HUD de chakra", "coloca a tarefa X na fila",
                     "para de usar print no código"):
            self.assertIsNone(parse(text), text)


@unittest.skipUnless(HAVE_MM, "QtMultimedia necessário")
class RealPlayer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name) / "Músicas"
        tone(root / "A - Primeira.wav", 0.5, 440)
        tone(root / "B - Segunda.wav", 0.5, 660)
        from kaguya.music.player import MusicPlayer
        self.lib = MusicLibrary(Path(self.tmp.name) / "m.db")
        self.lib.add_folder(root)
        from PySide6.QtCore import QCoreApplication, QEvent
        self.p = MusicPlayer(self.lib)
        # destroy the Qt objects here, on the main thread (never later by a garbage collection in another thread)
        self.addCleanup(lambda: QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete))
        self.addCleanup(self.p.deleteLater)
        self.addCleanup(self.p.player.stop)

    def pump(self, cond, timeout=8):
        end = time.time() + timeout
        while time.time() < end:
            self.app.processEvents()
            if cond():
                return True
            time.sleep(0.02)
        return False

    def test_plays_advances_queue_volume_and_ducking(self):
        reply = self.p.execute("play", "")
        self.assertIn("Tocando", reply)
        first = self.p.track.title
        self.assertTrue(self.pump(lambda: self.p.player.duration() > 0))
        self.assertAlmostEqual(self.p.player.duration(), 500, delta=60)      # real decoding by FFmpeg
        self.assertTrue(self.pump(lambda: self.p.track and self.p.track.title != first, 10))  # end → next track
        self.assertEqual(self.p.execute("volume", "30"), "Volume da música em 30%.")
        self.assertAlmostEqual(self.p.out.volume(), 0.30, places=2)
        self.p.duck_level = 25
        self.p.duck(True)
        self.assertAlmostEqual(self.p.out.volume(), 0.075, places=3)       # 25% of 30%
        self.p.duck(False)
        self.assertAlmostEqual(self.p.out.volume(), 0.30, places=2)       # always restored
        self.assertIn("Não achei", self.p.execute("play", "metallica"))
        opened = []
        self.assertIn("YouTube", self.p.execute("external", "abertura de naruto no youtube", open_url=opened.append))
        self.assertTrue(opened[0].startswith("https://www.youtube.com/results?search_query=abertura+de+naruto"))
        self.assertIsNone(self.p.handle_text("implemente o HUD"))


if __name__ == "__main__":
    unittest.main()
