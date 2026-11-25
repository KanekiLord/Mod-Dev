"""Personalities page: Kaguya (Codex) and Miwa (Claude Code) side by side.

Everything here changes only how they talk, their names, voices and looks — never permissions, models or safety
rules (spec 04). Global profile or a per-project override; export/import JSON without secrets; reset.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QLineEdit, QMessageBox,
                               QPlainTextEdit, QSlider, QTextBrowser, QVBoxLayout, QWidget)

from .. import persona
from .page_work import page_title, scroll
from .theme import AGENT, C
from .widgets import Card, SpriteView, Toggle, button, label


class PersonaEditor(Card):
    def __init__(self, page, agent: str):
        super().__init__(accent=AGENT[agent]["color"])
        self.page, self.win, self.agent = page, page.win, agent
        self._loading = False
        head = QHBoxLayout()
        self.sprite = SpriteView(AGENT[agent]["color"], aura=False)
        self.sprite.setFixedSize(96, 96)
        head.addWidget(self.sprite)
        col = QVBoxLayout()
        self.title = label("", "h2")
        self.title.setStyleSheet(f"color: {AGENT[agent]['color']};")
        col.addWidget(self.title)
        col.addWidget(label(f"Provedor: {AGENT[agent]['name']} (não muda ao renomear)", "dim"))
        self.scope_note = label("", "dim", wrap=True)
        col.addWidget(self.scope_note)
        head.addLayout(col, 1)
        self.lay.addLayout(head)
        self.enabled = Toggle("Usar personalidade", True)
        self.lay.addWidget(self.enabled)
        form = QFormLayout()
        form.setVerticalSpacing(6)
        self.name = QLineEdit()
        self.name.setPlaceholderText(persona.DEFAULT_NAME[agent])
        self.name.setMaxLength(24)
        self.preset = QComboBox()
        for key, spec in persona.PRESETS.items():
            self.preset.addItem(spec["label"], key)
        self.nickname = QLineEdit()
        self.nickname.setPlaceholderText("como ela te chama (ex.: Meu Lorde, chefe, seu nome)")
        self.address = QComboBox()
        for key, text in (("voce", "Você"), ("tu", "Tu"), ("formal", "Formal")):
            self.address.addItem(text, key)
        self.greeting = QLineEdit()
        self.greeting.setPlaceholderText("ex.: \"Bom dia, Meu Lorde! Pronta para a missão de hoje.\"")
        self.proactive = QComboBox()
        for key, text in persona.PROACTIVE.items():
            self.proactive.addItem(text, key)
        form.addRow("Nome", self.name)
        form.addRow("Estilo", self.preset)
        form.addRow("Apelido", self.nickname)
        form.addRow("Tratamento", self.address)
        form.addRow("Saudação", self.greeting)
        form.addRow("Iniciativa própria", self.proactive)
        self.lay.addLayout(form)
        self.third = Toggle("Falar de si na terceira pessoa às vezes", False)
        self.emoji = Toggle("Emojis no texto (nunca na voz)", False)
        self.lay.addWidget(self.third)
        self.lay.addWidget(self.emoji)
        grid = QGridLayout()
        grid.setVerticalSpacing(4)
        self.sliders: dict[str, tuple[QSlider, object]] = {}
        for row, (key, text) in enumerate(persona.SLIDERS):
            sl = QSlider(Qt.Horizontal)
            sl.setRange(0, 100)
            sl.setSingleStep(5)
            sl.setPageStep(10)
            sl.setAccessibleName(text)
            val = label("", "dim")
            val.setFixedWidth(34)
            grid.addWidget(label(text, "muted"), row, 0)
            grid.addWidget(sl, row, 1)
            grid.addWidget(val, row, 2)
            self.sliders[key] = (sl, val)
        self.lay.addLayout(grid)
        self.extra = QPlainTextEdit()
        self.extra.setPlaceholderText("Do seu jeito: história, jeito de falar, manias… (ex.: \"chama os bugs de Akatsuki\")")
        self.extra.setFixedHeight(64)
        self.lay.addWidget(label("Texto livre", "dim"))
        self.lay.addWidget(self.extra)
        # voice and look live in their own settings; editable here too
        vrow = QFormLayout()
        self.voice = QComboBox()
        from ..voice.neural import PRESETS as VOICES
        for key, preset in VOICES.items():
            self.voice.addItem(preset.label, key)
        self.variant = QComboBox()
        for key, text in self.win.mascots[agent].variants():
            self.variant.addItem(text, key)
        vrow.addRow("Voz neural", self.voice)
        vrow.addRow("Visual", self.variant)
        self.lay.addLayout(vrow)
        brow = QHBoxLayout()
        self.listen = button("Ouvir apresentação", "volume", "ghost", "Fala a saudação com a voz escolhida (local, sem IA)")
        self.listen.clicked.connect(self.hear)
        self.reset_btn = button("Restaurar padrão", "refresh", "ghost")
        self.reset_btn.clicked.connect(self.reset)
        brow.addWidget(self.listen)
        brow.addWidget(self.reset_btn)
        brow.addStretch(1)
        self.lay.addLayout(brow)
        self.preview = QTextBrowser()
        self.preview.setFixedHeight(150)
        self.preview.setStyleSheet(f"font-size: 8.4pt; color: {C['muted']};")
        self.lay.addWidget(label("Texto que vai para a IA (depois das regras do Studio)", "dim"))
        self.lay.addWidget(self.preview)
        self._save_timer = QTimer(self, singleShot=True, interval=350)
        self._save_timer.timeout.connect(self.save)
        for w in (self.name, self.nickname, self.greeting):
            w.textChanged.connect(self._changed)
        for w in (self.preset, self.address, self.proactive):
            w.currentIndexChanged.connect(self._changed)
        self.preset.currentIndexChanged.connect(self._preset_changed)
        for w in (self.enabled, self.third, self.emoji):
            w.toggled.connect(self._changed)
        self.extra.textChanged.connect(self._changed)
        for sl, val in self.sliders.values():
            sl.valueChanged.connect(lambda v, lb=val: lb.setText(str(v)))
            sl.valueChanged.connect(self._changed)
        self.voice.currentIndexChanged.connect(self._voice_changed)
        self.variant.currentIndexChanged.connect(self._variant_changed)

    # ------------------------------------------------------------------ data
    def load(self):
        self._loading = True
        pid = self.page.scope_pid()
        p = persona.load(self.win.store, self.agent, pid)
        self.enabled.setChecked(p.enabled)
        self.enabled.set_knob(1.0 if p.enabled else 0.0)
        self.name.setText(p.name)
        self.preset.setCurrentIndex(max(0, self.preset.findData(p.preset)))
        self.nickname.setText(p.nickname)
        self.address.setCurrentIndex(max(0, self.address.findData(p.address)))
        self.greeting.setText(p.greeting)
        self.proactive.setCurrentIndex(max(0, self.proactive.findData(p.proactive)))
        for t, on in ((self.third, p.third_person), (self.emoji, p.emoji)):
            t.setChecked(on)
            t.set_knob(1.0 if on else 0.0)
        for key, (sl, val) in self.sliders.items():
            sl.setValue(p.value(key))
            val.setText(str(p.value(key)))
        self.extra.setPlainText(p.extra)
        from ..voice.neural import DEFAULT_PRESET
        from ..voice.engines import load_profile
        self.voice.setCurrentIndex(max(0, self.voice.findData(
            load_profile(self.win.store, self.agent).voice or DEFAULT_PRESET.get(self.agent, "dora"))))
        self.variant.setCurrentIndex(max(0, self.variant.findData(self.win.mascots[self.agent].prefs.variant)))
        override = persona.has_project_override(self.win.store, self.agent, pid)
        self.scope_note.setText("Ajuste só deste projeto." if override else
                                ("Usando o perfil global (edite para criar um ajuste deste projeto)." if pid is not None
                                 else "Perfil global (vale para todos os projetos sem ajuste próprio)."))
        self._loading = False
        self._refresh(p)

    def current(self) -> persona.Persona:
        p = persona.Persona(preset=self.preset.currentData(), name=self.name.text().strip(),
                            nickname=self.nickname.text().strip(), address=self.address.currentData(),
                            third_person=self.third.isChecked(), greeting=self.greeting.text().strip(),
                            proactive=self.proactive.currentData(), emoji=self.emoji.isChecked(),
                            extra=self.extra.toPlainText().strip()[:800], enabled=self.enabled.isChecked())
        for key, (sl, _val) in self.sliders.items():
            setattr(p, key, sl.value())
        return p

    def _changed(self, *_):
        if not self._loading:
            self._save_timer.start()
            self._refresh(self.current())

    def _preset_changed(self, *_):
        if self._loading:
            return
        values = persona.PRESETS.get(self.preset.currentData(), {}).get("values", {})
        self._loading = True
        for key, v in values.items():
            self.sliders[key][0].setValue(v)
        self._loading = False
        self._changed()

    def save(self):
        persona.save(self.win.store, self.agent, self.current(), self.page.scope_pid())
        if self.page.scope_pid() is None:
            self.win.apply_persona_names()
        self.load_note()

    def load_note(self):
        pid = self.page.scope_pid()
        if pid is not None:
            self.scope_note.setText("Ajuste só deste projeto.")

    def _refresh(self, p: persona.Persona):
        name = (p.name or persona.DEFAULT_NAME[self.agent])
        self.title.setText(f"{name}")
        self.sprite.set_image(self.win.mascots[self.agent].image())
        self.preview.setPlainText(persona.describe(p, self.agent) or "Personalidade desligada: só as regras do Studio.")

    def _voice_changed(self, *_):
        if not self._loading:
            from ..voice.engines import load_profile, save_profile
            p = load_profile(self.win.store, self.agent)
            p.voice = self.voice.currentData()
            save_profile(self.win.store, self.agent, p)

    def _variant_changed(self, *_):
        if not self._loading:
            self.win.mascots[self.agent].set_variant(self.variant.currentData())
            self._refresh(self.current())

    def reset(self):
        persona.reset(self.win.store, self.agent, self.page.scope_pid())
        if self.page.scope_pid() is None:
            self.win.apply_persona_names()
        self.load()

    def hear(self):
        p = self.current()
        name = p.name or persona.DEFAULT_NAME[self.agent]
        text = p.greeting or f"Oi{', ' + p.nickname if p.nickname else ''}! Eu sou a {name}. Pronta para trabalhar."
        if not self.win.voice.say(text, self.agent):
            self.win.voice.speak(text, self.agent)


class PersonaPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page_title("sparkle", "Personalidades", "Como a Kaguya e a Miwa falam, se chamam, soam e "
                                   "aparecem. Não muda permissões, modelos nem regras de segurança."))
        bar = QHBoxLayout()
        bar.addWidget(label("Aplicar a", "dim"))
        self.scope = QComboBox()
        self.scope.currentIndexChanged.connect(self.reload)
        bar.addWidget(self.scope)
        self.clear_btn = button("Remover ajustes deste projeto", "x", "ghost")
        self.clear_btn.clicked.connect(self.clear_project)
        bar.addWidget(self.clear_btn)
        bar.addStretch(1)
        exp = button("Exportar", "download", "ghost", "Salva os dois perfis em JSON (sem segredos)")
        exp.clicked.connect(self.export)
        imp = button("Importar", "folder-open", "ghost", "Carrega perfis de um JSON")
        imp.clicked.connect(self.import_)
        bar.addWidget(exp)
        bar.addWidget(imp)
        outer.addLayout(bar)
        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(0, 0, 8, 0)
        grid.setHorizontalSpacing(14)
        self.editors = {a: PersonaEditor(self, a) for a in ("codex", "claude")}
        grid.addWidget(self.editors["codex"], 0, 0, Qt.AlignTop)
        grid.addWidget(self.editors["claude"], 0, 1, Qt.AlignTop)
        outer.addWidget(scroll(content), 1)

    def scope_pid(self):
        return self.scope.currentData()

    def refresh(self):
        self.scope.blockSignals(True)
        self.scope.clear()
        self.scope.addItem("Todos os projetos (global)", None)
        if self.win.pid is not None:
            name = self.win.store.project(self.win.pid)["name"]
            self.scope.addItem(f"Só o projeto atual: {name}", self.win.pid)
        self.scope.blockSignals(False)
        self.reload()

    def reload(self, *_):
        self.clear_btn.setVisible(self.scope_pid() is not None)
        for e in self.editors.values():
            e.load()

    def clear_project(self):
        pid = self.scope_pid()
        if pid is None:
            return
        for a in ("codex", "claude"):
            persona.clear_project(self.win.store, a, pid)
        self.reload()
        self.win.toast("Este projeto volta a usar os perfis globais.")

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exportar personalidades", "personalidades-kaguya-studio.json",
                                              "JSON (*.json)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(persona.export_json(self.win.store))
            self.win.toast("Personalidades exportadas.")

    def import_(self):
        path, _ = QFileDialog.getOpenFileName(self, "Importar personalidades", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                done = persona.import_json(self.win.store, fh.read())
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Importar", f"Arquivo inválido: {exc}")
            return
        self.win.apply_persona_names()
        self.reload()
        self.win.toast(f"Importado: {', '.join(AGENT[a]['mascot'] for a in done) or 'nada'}.")
