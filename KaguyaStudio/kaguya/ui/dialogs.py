"""Dialogs: link/edit project (with live folder verification), vault link, quick chat, details."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QButtonGroup, QDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QRadioButton,
                               QTextBrowser, QVBoxLayout, QWidget)

from ..paths import FolderCheck, check_project_folder, check_vault_folder
from ..store import Store
from . import theme
from .common import pick_folder
from .theme import C
from .widgets import Card, Pill, button, label


def check_html(check: FolderCheck | None) -> str:
    if check is None:
        return ""
    rows = []
    if check.problems:
        rows += [f"<span style='color:{C['danger']}'>✕ {p}</span>" for p in check.problems]
    else:
        rows.append(f"<span style='color:{C['success']}'>✓ {check.summary()}</span>")
    rows += [f"<span style='color:{C['warning']}'>⚠ {w}</span>" for w in check.warnings]
    rows += [f"<span style='color:{C['muted']}'>→ {h}</span>" for h in check.hints]
    return "<br>".join(rows)


class PathField(QWidget):
    """Editable path + browse button + live verification (typing or pasting works)."""
    checked = Signal(object)

    def __init__(self, kind: str, title: str, value: str = ""):
        super().__init__()
        self.kind, self.title = kind, title
        self.result: FolderCheck | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        row = QHBoxLayout()
        self.edit = QLineEdit(value)
        self.edit.setPlaceholderText("Cole ou digite o caminho, ex.: D:\\Projetos\\NarutoCD")
        self.edit.setAccessibleName(title)
        browse = button("Procurar…", "folder-open")
        browse.clicked.connect(self.browse)
        row.addWidget(self.edit, 1)
        row.addWidget(browse)
        lay.addLayout(row)
        self.status = label("", wrap=True)
        self.status.setTextFormat(Qt.RichText)
        lay.addWidget(self.status)
        self._timer = QTimer(self, singleShot=True, interval=350)
        self._timer.timeout.connect(self.verify)
        self.edit.textChanged.connect(lambda _: self._timer.start())
        if value:
            self.verify()

    def browse(self):
        path = pick_folder(self.window(), self.title, self.edit.text())
        if path:
            self.edit.setText(str(Path(path)))
            self.verify()

    def verify(self):
        text = self.edit.text().strip()
        if not text:
            self.result = None
            self.status.setText("")
            self.edit.setProperty("state", "")
        else:
            try:
                self.result = check_project_folder(text) if self.kind == "projeto" else check_vault_folder(text)
            except ValueError as exc:
                self.result = None
                self.status.setText(f"<span style='color:{C['danger']}'>✕ {exc}</span>")
                return
            self.status.setText(check_html(self.result))
            self.edit.setProperty("state", "ok" if self.result.ok else "error")
        self.edit.style().unpolish(self.edit)
        self.edit.style().polish(self.edit)
        self.checked.emit(self.result)

    def value(self) -> str:
        return self.result.path if self.result else self.edit.text().strip()


class ProjectDialog(QDialog):
    def __init__(self, store: Store, parent=None, project: dict | None = None):
        super().__init__(parent)
        self.store, self.project = store, project
        self.setWindowTitle("Editar projeto" if project else "Vincular projeto")
        self.setMinimumWidth(640)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(12)
        lay.addWidget(label("Editar projeto" if project else "Vincular projeto", "h1"))
        lay.addWidget(label("Cada pasta é verificada separadamente. Nada é alterado nos seus arquivos.", "muted", wrap=True))
        lay.addWidget(label("PASTA DO PROJETO", "section"))
        self.folder = PathField("projeto", "Escolha a pasta do projeto", project["directory"] if project else "")
        lay.addWidget(self.folder)
        lay.addWidget(label("NOME", "section"))
        self.name = QLineEdit(project["name"] if project else "")
        self.name.setPlaceholderText("Nome exibido (opcional)")
        lay.addWidget(self.name)
        lay.addWidget(label("SEGUNDO CÉREBRO (OBSIDIAN)", "section"))
        gv = store.global_vault()
        self.r_global = QRadioButton(f"Usar o vault global ({gv})" if gv else "Usar o vault global (ainda não definido)")
        self.r_own = QRadioButton("Vault próprio para este projeto")
        group = QButtonGroup(self)
        group.addButton(self.r_global)
        group.addButton(self.r_own)
        own = bool(project and project.get("vault"))
        (self.r_own if own else self.r_global).setChecked(True)
        lay.addWidget(self.r_global)
        lay.addWidget(self.r_own)
        self.vault = PathField("vault", "Escolha a pasta raiz do vault do Obsidian", project.get("vault") or "" if project else "")
        self.vault.setEnabled(own)
        self.r_own.toggled.connect(self.vault.setEnabled)
        lay.addWidget(self.vault)
        lay.addWidget(label("COMANDO DE TESTES (OPCIONAL)", "section"))
        self.tests = QLineEdit(project.get("test_command") or "" if project else "")
        self.tests.setPlaceholderText("Detectado automaticamente (gradlew test, pytest, npm test…)")
        lay.addWidget(self.tests)
        self.error = label("", wrap=True)
        self.error.setStyleSheet(f"color:{C['danger']}")
        lay.addWidget(self.error)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = button("Cancelar", kind="ghost")
        cancel.clicked.connect(self.reject)
        self.save_btn = button("Salvar projeto", "check", "primary")
        self.save_btn.clicked.connect(self.save)
        row.addWidget(cancel)
        row.addWidget(self.save_btn)
        lay.addLayout(row)
        self.folder.checked.connect(self._update)
        self._update()

    def _update(self, *_):
        ok = bool(self.folder.result and self.folder.result.ok)
        self.save_btn.setEnabled(ok)
        if ok and not self.name.text().strip():
            self.name.setPlaceholderText(Path(self.folder.result.path).name)

    def save(self):
        try:
            vault = None
            if self.r_own.isChecked():
                if not (self.vault.result and self.vault.result.ok):
                    self.error.setText("Verifique a pasta do vault próprio (ou escolha o vault global).")
                    return
                vault = self.vault.value()
            if self.project:
                self.store.update_project(self.project["id"], name=self.name.text().strip() or Path(self.folder.value()).name,
                                          directory=self.folder.value(), vault=vault, test_command=self.tests.text())
                self.pid = self.project["id"]
            else:
                self.pid = self.store.add_project(self.name.text().strip(), self.folder.value(), vault)
                self.store.update_project(self.pid, vault=vault, test_command=self.tests.text())
        except ValueError as exc:
            self.error.setText(str(exc))
            return
        self.accept()


class QuickChat(QDialog):
    """Small always-on-top chat opened from a mascot. Always read-only and never interrupts."""
    submit = Signal(str, str, str)  # text, target, forced intent

    def __init__(self, agent: str, parent=None):
        super().__init__(parent, Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setWindowTitle("Chat rápido — Kaguya Studio")
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        top = QHBoxLayout()
        top.addWidget(label("Mensagem rápida", "h2"))
        top.addStretch(1)
        top.addWidget(Pill("somente leitura • não interrompe", C["muted"]))
        lay.addLayout(top)
        chips = QHBoxLayout()
        self.target = agent
        self._chips = {}
        for key, text in (("codex", "Codex"), ("claude", "Claude"), ("equipe", "Equipe")):
            b = button(text, theme.AGENT[key]["icon"], "chip", checkable=True, color=theme.AGENT[key]["color"])
            b.setChecked(key == agent)
            b.clicked.connect(lambda _=False, k=key: self._pick(k))
            chips.addWidget(b)
            self._chips[key] = b
        chips.addStretch(1)
        lay.addLayout(chips)
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("Pergunte algo ou anote uma ideia… (Ctrl+Enter envia)")
        self.text.setFixedHeight(96)
        lay.addWidget(self.text)
        row = QHBoxLayout()
        later = button("Depois", "clock", "ghost")
        later.clicked.connect(lambda: self._send("DEPOIS"))
        idea = button("Ideia", "lightbulb", "ghost")
        idea.clicked.connect(lambda: self._send("IDEIA"))
        send = button("Enviar", "send", "primary")
        send.clicked.connect(lambda: self._send(""))
        row.addWidget(later)
        row.addWidget(idea)
        row.addStretch(1)
        row.addWidget(send)
        lay.addLayout(row)

    def _pick(self, key):
        self.target = key
        for k, b in self._chips.items():
            b.setChecked(k == key)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and e.modifiers() & Qt.ControlModifier:
            self._send("")
            return
        super().keyPressEvent(e)

    def _send(self, forced: str):
        text = self.text.toPlainText().strip()
        if text:
            self.submit.emit(text, self.target, forced)
            self.text.clear()


class TextDialog(QDialog):
    def __init__(self, title: str, text: str, parent=None, markdown: bool = False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(820, 600)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.addWidget(label(title, "h2"))
        view = QTextBrowser()
        view.setOpenExternalLinks(True)
        if markdown:
            view.setMarkdown(text)
        else:
            view.setPlainText(text)
            view.setStyleSheet(f"font-family: '{theme.FONT_MONO}'; font-size: 8.5pt;")
        lay.addWidget(view, 1)
        close = button("Fechar", kind="ghost")
        close.clicked.connect(self.accept)
        lay.addWidget(close, 0, Qt.AlignRight)
