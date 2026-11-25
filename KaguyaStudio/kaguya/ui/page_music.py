"""Kaguya Music page: local library, search, favourites, playlists, queue and dock options."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QInputDialog, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QSlider, QSplitter, QVBoxLayout, QWidget)

from .common import pick_folder, run_bg
from .music_dock import fmt
from .page_work import item, page_title, table
from .theme import C
from .widgets import Card, Toggle, button, label


class MusicPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.player = win.music
        self.lib = win.music.lib
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(page_title("music", "Kaguya Music", "Suas músicas locais tocadas pelo Studio, playlists e a bandeja "
                                 "lateral. Peça também por texto ou voz: \"toca a playlist Foco\", \"volume 30%\"."))
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar por música, artista ou pasta…")
        self.search.textChanged.connect(self.refresh_tracks)
        add = button("Adicionar pasta", "folder-plus", "primary", "Escolha uma pasta com músicas (MP3, FLAC, WAV, OGG, M4A…)")
        add.clicked.connect(self.add_folder)
        self.only_fav = Toggle("Só favoritas", False)
        self.only_fav.toggled.connect(self.refresh_tracks)
        bar.addWidget(self.search, 1)
        bar.addWidget(self.only_fav)
        bar.addWidget(add)
        lay.addLayout(bar)
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.table = table(["", "Título", "Artista", "Duração", "Tocadas"], stretch=1)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.doubleClicked.connect(lambda *_: self.play_selected())
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.track_menu)
        ll.addWidget(self.table, 1)
        trow = QHBoxLayout()
        for text, icon, fn in (("Tocar", "play", self.play_selected), ("Pôr na fila", "list", self.queue_selected),
                               ("Favoritar", "sparkle", self.fav_selected), ("Na playlist…", "plus", self.add_to_playlist)):
            b = button(text, icon, "ghost")
            b.clicked.connect(fn)
            trow.addWidget(b)
        trow.addStretch(1)
        self.count = label("", "dim")
        trow.addWidget(self.count)
        ll.addLayout(trow)
        split.addWidget(left)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        pc = Card()
        pc.lay.addWidget(label("PLAYLISTS", "section"))
        self.playlists = QListWidget()
        self.playlists.itemDoubleClicked.connect(lambda it: self.play_playlist(it.data(Qt.UserRole)))
        pc.lay.addWidget(self.playlists)
        prow = QHBoxLayout()
        newp = button("Nova", "plus", "ghost")
        newp.clicked.connect(self.new_playlist)
        playp = button("Tocar", "play", "ghost")
        playp.clicked.connect(lambda: self.play_playlist(self._sel_playlist()))
        delp = button("Apagar", "trash", "ghost")
        delp.clicked.connect(self.delete_playlist)
        for b in (newp, playp, delp):
            prow.addWidget(b)
        pc.lay.addLayout(prow)
        rl.addWidget(pc)
        qc = Card()
        qc.lay.addWidget(label("FILA", "section"))
        self.queue_list = QListWidget()
        self.queue_list.itemDoubleClicked.connect(lambda it: self.player._play_index(it.data(Qt.UserRole)))
        qc.lay.addWidget(self.queue_list)
        rl.addWidget(qc)
        oc = Card()
        oc.lay.addWidget(label("BANDEJA LATERAL E VOZ", "section"))
        self.t_dock = Toggle("Mostrar a bandeja (lingueta na borda da tela)", True)
        self.t_dock.toggled.connect(lambda on: win.set_music_dock_visible(on))
        oc.lay.addWidget(self.t_dock)
        erow = QHBoxLayout()
        erow.addWidget(label("Borda", "muted"))
        self.edge = QComboBox()
        self.edge.addItem("Direita", "right")
        self.edge.addItem("Esquerda", "left")
        self.edge.currentIndexChanged.connect(lambda: win.music_dock.set_edge(self.edge.currentData()))
        erow.addWidget(self.edge)
        erow.addStretch(1)
        oc.lay.addLayout(erow)
        drow = QHBoxLayout()
        drow.addWidget(label("Música enquanto a IA fala", "muted"))
        self.duck = QSlider(Qt.Horizontal)
        self.duck.setRange(0, 100)
        self.duck.valueChanged.connect(self._duck_changed)
        self.duck_lbl = label("", "dim")
        drow.addWidget(self.duck, 1)
        drow.addWidget(self.duck_lbl)
        oc.lay.addLayout(drow)
        oc.lay.addWidget(label("YouTube, Spotify e Amazon Music: o Studio abre a busca e, na bandeja, as teclas de mídia do "
                               "Windows controlam o app que estiver tocando. Ele não toca vídeos escondidos nem lê esses "
                               "apps; Spotify não recebe comandos de voz (regra da Spotify).", "dim", wrap=True))
        rl.addWidget(oc)
        split.addWidget(right)
        split.setSizes([700, 360])
        lay.addWidget(split, 1)
        self.player.changed.connect(self.refresh_queue)

    # ------------------------------------------------------------------ data
    def refresh(self):
        st = self.win.store
        lib = self.win.music.lib
        if lib.recovered and getattr(self, "_warned", 0) < len(lib.recovered):
            self._warned = len(lib.recovered)
            self.win.toast("A biblioteca de músicas estava danificada e foi refeita a partir das suas pastas. "
                           f"O arquivo antigo ficou guardado: {Path(lib.recovered[-1]).name}")
        self.t_dock.blockSignals(True)
        self.t_dock.setChecked(bool(st.get_setting("music.dock.visible", True)))
        self.t_dock.set_knob(1.0 if self.t_dock.isChecked() else 0.0)
        self.t_dock.blockSignals(False)
        self.edge.blockSignals(True)
        self.edge.setCurrentIndex(0 if self.win.music_dock.edge == "right" else 1)
        self.edge.blockSignals(False)
        self.duck.blockSignals(True)
        self.duck.setValue(self.player.duck_level)
        self.duck.blockSignals(False)
        self.duck_lbl.setText(f"{self.player.duck_level}%")
        self.refresh_tracks()
        self.refresh_playlists()
        self.refresh_queue()

    def refresh_tracks(self, *_):
        tracks = self.lib.tracks(self.search.text(), favorites=self.only_fav.isChecked())
        self.table.setRowCount(0)
        for t in tracks:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, item("★" if t.favorite else "", C["gold"], t.id))
            self.table.setItem(r, 1, item(t.title))
            self.table.setItem(r, 2, item(t.artist, C["muted"]))
            self.table.setItem(r, 3, item(fmt(t.duration_ms) if t.duration_ms else "—", C["dim"]))
            self.table.setItem(r, 4, item(str(t.plays), C["dim"]))
        folders = self.lib.folders()
        self.count.setText(f"{len(tracks)} de {self.lib.count()} músicas • {len(folders)} pasta(s)")

    def refresh_playlists(self):
        self.playlists.clear()
        for p in self.lib.playlists():
            it = QListWidgetItem(f"{p['name']}  ({p['n']})")
            it.setData(Qt.UserRole, p["id"])
            self.playlists.addItem(it)

    def refresh_queue(self):
        self.queue_list.clear()
        for i, tid in enumerate(self.player.queue[:200]):
            t = self.lib.get(tid)
            if t:
                it = QListWidgetItem(("▶ " if i == self.player.index else "") + t.label)
                it.setData(Qt.UserRole, i)
                self.queue_list.addItem(it)

    # --------------------------------------------------------------- actions
    def _selected_ids(self) -> list[int]:
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        return [self.table.item(r, 0).data(Qt.UserRole) for r in rows]

    def _all_ids(self) -> list[int]:
        return [self.table.item(r, 0).data(Qt.UserRole) for r in range(self.table.rowCount())]

    def play_selected(self):
        sel = self._selected_ids()
        ids = self._all_ids()
        if not ids:
            return
        start = ids.index(sel[0]) if sel else 0
        self.player.play_tracks(ids if len(sel) <= 1 else sel, start if len(sel) <= 1 else 0)

    def queue_selected(self):
        self.player.queue_add(self._selected_ids())
        self.win.toast("Adicionado à fila.")

    def fav_selected(self):
        for tid in self._selected_ids():
            t = self.lib.get(tid)
            self.lib.set_favorite(tid, not t.favorite)
        self.refresh_tracks()

    def track_menu(self, pos):
        menu = QMenu(self)
        menu.addAction("Tocar", self.play_selected)
        menu.addAction("Pôr na fila", self.queue_selected)
        menu.addAction("Favoritar / desfavoritar", self.fav_selected)
        sub = menu.addMenu("Adicionar à playlist")
        for p in self.lib.playlists():
            sub.addAction(p["name"], lambda pid=p["id"]: (self.lib.add_to_playlist(pid, self._selected_ids()),
                                                           self.refresh_playlists()))
        sub.addAction("Nova playlist…", self.add_to_playlist)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def add_folder(self):
        folder = pick_folder(self, "Pasta de músicas")
        if not folder:
            return
        self.win.toast("Lendo a pasta de músicas…")
        run_bg(lambda: self.lib.add_folder(folder), lambda n: (self.win.toast(f"{n} música(s) adicionada(s)."),
                                                               self.refresh()),
               lambda exc, tb: self.win.toast(f"Não foi possível ler a pasta: {exc}"))

    def new_playlist(self) -> int | None:
        name, ok = QInputDialog.getText(self, "Nova playlist", "Nome:")
        if ok and name.strip():
            pid = self.lib.create_playlist(name)
            self.refresh_playlists()
            return pid
        return None

    def add_to_playlist(self):
        ids = self._selected_ids()
        if not ids:
            self.win.toast("Selecione músicas na lista.")
            return
        names = [p["name"] for p in self.lib.playlists()] + ["Nova playlist…"]
        name, ok = QInputDialog.getItem(self, "Adicionar à playlist", "Playlist:", names, 0, False)
        if not ok:
            return
        pid = self.new_playlist() if name == "Nova playlist…" else self.lib.find_playlist(name)["id"]
        if pid:
            self.lib.add_to_playlist(pid, ids)
            self.refresh_playlists()

    def _sel_playlist(self):
        it = self.playlists.currentItem()
        return it.data(Qt.UserRole) if it else None

    def play_playlist(self, pid):
        if pid is None:
            return
        ids = [t.id for t in self.lib.playlist_tracks(pid)]
        if not self.player.play_tracks(ids):
            self.win.toast("Playlist vazia.")

    def delete_playlist(self):
        pid = self._sel_playlist()
        if pid is not None:
            self.lib.delete_playlist(pid)
            self.refresh_playlists()

    def _duck_changed(self, v):
        self.player.duck_level = int(v)
        self.win.store.set_setting("music.duck_level", int(v))
        self.duck_lbl.setText(f"{v}%")
        self.player._apply_volume()
