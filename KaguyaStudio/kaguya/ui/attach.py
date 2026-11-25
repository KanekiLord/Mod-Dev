"""Attach files to a message: read by the Leitor Universal, previewed and edited by the user, then sent as data."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout

from ..env import redact
from ..reader import ReadResult
from .theme import C
from .widgets import label


class AttachDialog(QDialog):
    """Shows what was read and exactly what will be sent. The user can delete anything before approving."""

    def __init__(self, parent, res: ReadResult, query: str = ""):
        super().__init__(parent)
        self.res, self.query = res, query
        self.setWindowTitle(f"Anexar {Path(res.path).name}")
        self.resize(760, 620)
        lay = QVBoxLayout(self)
        lay.addWidget(label(f"{Path(res.path).name} — {res.kind}", "h2"))
        facts = label(" · ".join(res.facts) or "", "muted", wrap=True)
        lay.addWidget(facts)
        if res.warnings:
            w = label("⚠ " + "  ⚠ ".join(res.warnings), wrap=True)
            w.setStyleSheet(f"color: {C['warning']};")
            lay.addWidget(w)
        lay.addWidget(label("O que vai para a IA (pode apagar o que quiser; é enviado como dado, não como ordem):",
                            "dim", wrap=True))
        self.edit = QPlainTextEdit()
        lay.addWidget(self.edit, 1)
        row = QHBoxLayout()
        self.only_relevant = QCheckBox("Só os trechos relevantes" + (f" para “{query[:40]}”" if query else ""))
        self.only_relevant.setChecked(bool(query))
        self.only_relevant.setEnabled(bool(query))
        self.hide_secrets = QCheckBox("Ocultar o que parece senha/token")
        self.hide_secrets.setChecked(True)
        for cb in (self.only_relevant, self.hide_secrets):
            cb.toggled.connect(self._fill)
            row.addWidget(cb)
        row.addStretch(1)
        self.size_lbl = QLabel()
        row.addWidget(self.size_lbl)
        lay.addLayout(row)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Anexar")
        self.buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)
        self.edit.textChanged.connect(lambda: self.size_lbl.setText(f"{len(self.edit.toPlainText()):,} caracteres"
                                                                    .replace(",", ".")))
        nothing = res.kind in ("bloqueado", "programa", "erro") or (not res.pieces and res.kind != "imagem")
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(not nothing)
        self._fill()

    def _fill(self, *_):
        text = self.res.render(self.query if self.only_relevant.isChecked() else "", limit=12000 if
                               self.only_relevant.isChecked() else 40000)
        if self.hide_secrets.isChecked():
            text = redact(text)
        self.edit.setPlainText(text)

    def item(self) -> dict:
        is_image = self.res.kind == "imagem"
        return {"name": Path(self.res.path).name, "text": self.edit.toPlainText().strip(),
                "image": self.res.path if is_image else ""}
