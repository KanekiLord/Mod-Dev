"""Choose where heavy downloads go (asked once, changeable in Configurações) and download the
transcription model with real progress — the voice features never download silently again."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QDialog, QHBoxLayout, QMessageBox, QProgressDialog, QRadioButton,
                               QVBoxLayout)

from .. import packs
from .common import _deliver, pick_folder, run_bg
from .widgets import button, label


class PacksDialog(QDialog):
    def __init__(self, parent, home: Path, need: int | None = None, current: Path | None = None):
        super().__init__(parent)
        self.setWindowTitle("Onde guardar os pacotes de voz e modelos")
        self.setMinimumWidth(560)
        self.need = need
        self.result_path: Path | None = None
        lay = QVBoxLayout(self)
        lay.addWidget(label("Os modelos de transcrição e as vozes podem ocupar de centenas de MB a alguns GB. "
                            "Escolha onde guardar (dá para mudar depois em Configurações › Voz; o que já estiver "
                            "instalado é movido, sem baixar de novo).", wrap=True))
        self.group = QButtonGroup(self)
        self.options: list[Path] = []
        found = packs.choices(home)
        # installed on another drive (e.g. D:) → that was a deliberate choice: suggest the same place
        default = next((i for i, ch in enumerate(found) if ch.key == "instalacao"
                        and Path(ch.path).anchor.lower() != Path(home).anchor.lower()), 0)
        for i, ch in enumerate(found):
            b = QRadioButton(f"{ch.label}\n{ch.path} — {packs.human(ch.free)} livres")
            b.setChecked((current is not None and ch.path == current) or (current is None and i == default))
            self.group.addButton(b, len(self.options))
            self.options.append(ch.path)
            lay.addWidget(b)
        self.other = QRadioButton("Outra pasta… (você escolhe o disco e a pasta)")
        self.group.addButton(self.other, len(self.options))
        lay.addWidget(self.other)
        if self.group.checkedId() < 0:
            self.group.buttons()[0].setChecked(True)
        self.warn = label("", "dim", wrap=True)
        lay.addWidget(self.warn)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = button("Cancelar", "x", "ghost")
        cancel.clicked.connect(self.reject)
        ok = button("Usar esta pasta", "check", "primary")
        ok.clicked.connect(self.confirm)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)

    def confirm(self):
        i = self.group.checkedId()
        if i < 0:
            return
        if i == len(self.options):
            chosen = pick_folder(self, "Pasta para os pacotes de voz e modelos")
            if not chosen:
                return
            path = Path(chosen) / "KaguyaStudio Pacotes" if Path(chosen).name != "KaguyaStudio Pacotes" else Path(chosen)
        else:
            path = self.options[i]
        if not packs.writable(path):
            self.warn.setText(f"Não consigo gravar em {path} (sem permissão). Escolha outra pasta.")
            return
        free = packs.free_bytes(path)
        if self.need and free is not None and free < self.need * 1.2:
            self.warn.setText(f"Espaço insuficiente em {path}: {packs.human(free)} livres, precisa de "
                              f"{packs.human(int(self.need * 1.2))}.")
            return
        self.result_path = path
        self.accept()


def ask_packs_dir(win, need: int | None = None) -> Path | None:
    """The packs folder, asking the first time. Old installs keep their folder without asking."""
    store, home = win.store, win.engine.home
    if packs.chosen(store):
        return win.engine.packs
    if packs.has_content(home):          # models/voices already downloaded there before this version
        packs.apply(store, home)
        return Path(home)
    chooser = getattr(win, "choose_packs_dir", None)   # tests replace the dialog
    path = chooser(home, need) if chooser else _dialog(win, home, need)
    if path is None:
        return None
    packs.apply(store, path)
    win.voice.relocate()
    return path


def _dialog(win, home, need, current=None) -> Path | None:
    dlg = PacksDialog(win, home, need, current)
    return dlg.result_path if dlg.exec() == QDialog.Accepted else None


def change_packs_dir(win, done=None) -> None:
    """Configurações › Voz › Mudar pasta: choose, then move what is installed (in the background)."""
    old = win.engine.packs
    if getattr(win, "live_window", None) is not None or win.wake.running or win.voice.downloading:
        QMessageBox.information(win, "Pasta dos pacotes", "Feche o Modo Live, desligue a escuta por nome e espere "
                                "downloads terminarem antes de mudar a pasta (os modelos estão em uso).")
        return
    chooser = getattr(win, "choose_packs_dir", None)
    new = chooser(win.engine.home, None) if chooser else _dialog(win, win.engine.home, None, old)
    if new is None or Path(new) == Path(old):
        return
    win.voice.close_engines()
    win.voice.transcriber = None          # loaded models keep files open on Windows
    import gc
    gc.collect()

    def work():
        return packs.move(old, new) if packs.has_content(old) else []

    def ok(moved):
        packs.apply(win.store, new)
        win.voice.relocate()
        win.toast(f"Pacotes agora em {new}" + (f" (movido: {', '.join(moved)})." if moved else "."))
        if done:
            done()

    def fail(exc, _tb):
        QMessageBox.warning(win, "Pasta dos pacotes", f"Não foi possível mover os pacotes: {exc}\n"
                            "Tudo continua na pasta anterior.")
        win.voice.relocate()
    run_bg(work, ok, fail)


def ensure_stt_model(win, model: str, then, on_cancel=None) -> None:
    """Run ``then()`` when the transcription model is on disk; otherwise ask, download with progress, then run it."""
    from ..voice import stt
    folder = win.engine.packs / "modelos"
    if stt.model_cached(folder, model):
        then()
        return
    size = stt.MODEL_BYTES.get(model, 0)
    root = ask_packs_dir(win, size)
    if root is None:
        if on_cancel:
            on_cancel()
        return
    folder = Path(root) / "modelos"
    if stt.model_cached(folder, model):
        then()
        return
    confirm = getattr(win, "confirm_download", None)   # tests answer without a dialog
    msg = (f"Para entender sua voz, o Studio precisa baixar uma vez o modelo de transcrição \"{model}\" "
           f"({packs.human(size)}, Systran/faster-whisper, licença MIT) do huggingface.co.\n\n"
           f"Destino: {folder}\n\nDepois disso tudo funciona sem internet. Baixar agora?")
    ok = confirm(msg) if confirm else QMessageBox.question(win, "Modelo de transcrição", msg) == QMessageBox.Yes
    if not ok:
        if on_cancel:
            on_cancel()
        return
    import threading
    cancel = threading.Event()
    dlg = None
    if not confirm:
        dlg = QProgressDialog(f"Baixando o modelo \"{model}\"…", "Cancelar", 0, 100, win)
        dlg.setWindowTitle("Modelo de transcrição")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.canceled.connect(cancel.set)
        dlg.show()

    def progress(done, total):
        if dlg is not None and total:
            pct = int(min(99, done * 100 / total))
            _deliver(lambda: (dlg.setValue(pct), dlg.setLabelText(
                f"Baixando o modelo \"{model}\"… {packs.human(done)} de {packs.human(total)}")))

    def finished(_r):
        if dlg is not None:
            dlg.canceled.disconnect()
            dlg.close()
        win.toast(f"Modelo de transcrição \"{model}\" pronto.")
        then()

    def failed(exc, _tb):
        by_user = cancel.is_set()          # read first: closing a QProgressDialog emits canceled
        if dlg is not None:
            dlg.canceled.disconnect()
            dlg.close()
        if not by_user:
            QMessageBox.warning(win, "Modelo de transcrição", str(exc))
        if on_cancel:
            on_cancel()
    win.voice.downloading = True
    run_bg(lambda: stt.download(folder, model, progress, cancel),
           lambda r: (setattr(win.voice, "downloading", False), finished(r)),
           lambda e, tb: (setattr(win.voice, "downloading", False), failed(e, tb)))
