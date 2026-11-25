"""Conversation page: streaming messages per agent, live activity and the composer."""
from __future__ import annotations

from datetime import datetime
import json
import re

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QTextOption
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QScrollArea, QSizePolicy, QVBoxLayout,
                               QWidget)

from . import theme
from .theme import AGENT, C
from .widgets import Card, Pill, Toggle, button, icon_label, label

STAGE_LABELS = {"implementacao": "Implementando", "verificacao": "Verificando", "revisao": "Revisando",
                "correcao": "Corrigindo", "execucao": "Executando", "final": "Veredito"}


class Avatar(QWidget):
    def __init__(self, agent: str, size: int = 34):
        super().__init__()
        self.agent = agent if agent in AGENT else "studio"
        self.setFixedSize(size, size)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        a = AGENT[self.agent]
        bg = QColor(a["color"])
        bg.setAlpha(40)
        p.setBrush(bg)
        border = QColor(a["color"])
        border.setAlpha(150)
        p.setPen(border)
        p.drawEllipse(self.rect().adjusted(1, 1, -1, -1))
        pm = theme.pixmap(a["icon"], a["color"], 18)
        p.drawPixmap((self.width() - 18) // 2, (self.height() - 18) // 2, pm)


class MessageCard(QFrame):
    def __init__(self, agent: str, body: str, stage: str = "", when: str | None = None, kind: str = "message"):
        super().__init__()
        self.agent, self.kind = agent, kind
        a = AGENT.get(agent, AGENT["studio"])
        self.setObjectName("msg")
        accent = a["color"]
        bg = "#1B1430" if agent != "user" else "#201938"
        border = C["border"]
        if kind == "verdict":
            border = C["gold"]
        elif kind == "error":
            border = C["danger"]
        self.setStyleSheet(f"QFrame#msg {{ background: {bg}; border: 1px solid {border}; border-radius: 14px; }}"
                           f"QFrame#msg[agent='codex'] {{ border-left: 3px solid {C['violet']}; }}"
                           f"QFrame#msg[agent='claude'] {{ border-left: 3px solid {C['amber']}; }}")
        self.setProperty("agent", agent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 16, 12)
        lay.setSpacing(12)
        lay.addWidget(Avatar(agent), 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(5)
        head = QHBoxLayout()
        head.setSpacing(8)
        name = label(a["name"] + (f"  ·  {a['mascot']}" if a.get("mascot") and a["mascot"] != a["name"] else ""))
        name.setStyleSheet(f"color: {accent}; font-weight: 700; font-size: 10pt;")
        head.addWidget(name)
        if stage:
            head.addWidget(Pill(STAGE_LABELS.get(stage.split(":")[0], stage), accent))
        head.addStretch(1)
        t = label(when or datetime.now().strftime("%H:%M"), "dim")
        head.addWidget(t)
        col.addLayout(head)
        self.body = QLabel()
        self.body.setWordWrap(True)
        self.body.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        self.body.setOpenExternalLinks(True)
        self.body.setTextFormat(Qt.MarkdownText)
        self.body.setStyleSheet(f"color: {C['text']}; font-size: 9.6pt;")
        self.body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.set_body(body)
        col.addWidget(self.body)
        self.activity = QVBoxLayout()
        self.activity.setSpacing(3)
        col.addLayout(self.activity)
        lay.addLayout(col, 1)

    def set_body(self, text: str):
        self._text = text
        shown = re.sub(r"```(?:json)?\s*\{[^`]*?\"veredito\"[^`]*?\}\s*```", "*(veredito estruturado abaixo)*", text)
        self.body.setText(shown[:12000])
        self.body.setVisible(bool(text.strip()))

    def append(self, text: str):
        self.set_body((self._text + "\n\n" + text).strip())

    def add_activity(self, icon_name: str, text: str, color: str = C["muted"]):
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(icon_label(icon_name, color, 14))
        lb = label(text[:240], "code")
        lb.setStyleSheet(f"color: {color}; font-family: '{theme.FONT_MONO}'; font-size: 8.2pt;")
        lb.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row.addWidget(lb, 1)
        self.activity.addLayout(row)
        if self.activity.count() > 14:
            item = self.activity.takeAt(0)
            if item and item.layout():
                while item.layout().count():
                    w = item.layout().takeAt(0).widget()
                    if w:
                        w.deleteLater()


class ChatView(QScrollArea):
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.inner = QWidget()
        self.lay = QVBoxLayout(self.inner)
        self.lay.setContentsMargins(4, 4, 10, 4)
        self.lay.setSpacing(10)
        self.lay.addStretch(1)
        self.setWidget(self.inner)
        self.current: dict[tuple[int, str], MessageCard] = {}
        self.last_agent_text = ""
        self._stick = True
        self.verticalScrollBar().rangeChanged.connect(self._autoscroll)
        self.verticalScrollBar().valueChanged.connect(self._track)

    def _track(self, v):
        sb = self.verticalScrollBar()
        self._stick = v >= sb.maximum() - 40

    def _autoscroll(self, _min, maximum):
        if self._stick:
            self.verticalScrollBar().setValue(maximum)

    def clear(self):
        while self.lay.count() > 1:
            w = self.lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.current.clear()

    def add(self, card: MessageCard) -> MessageCard:
        self.lay.insertWidget(self.lay.count() - 1, card)
        while self.lay.count() > 260:
            w = self.lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        return card

    def message(self, agent: str, text: str, stage: str = "", kind: str = "message", when: str | None = None) -> MessageCard:
        if agent in ("codex", "claude") and text:
            self.last_agent_text = text
        return self.add(MessageCard(agent, text, stage, when, kind))

    def agent_card(self, task_id: int, agent: str, stage: str) -> MessageCard:
        key = (task_id, agent + stage)
        card = self.current.get(key)
        if card is None:
            card = self.message(agent, "", stage)
            self.current[key] = card
        return card


class Composer(Card):
    send = Signal(str, str, str)     # text, target, forced
    stop = Signal()
    speak = Signal()
    mic = Signal(bool)
    devices = Signal()
    live = Signal()
    autonomy = Signal(bool)
    desktop = Signal(bool)

    def __init__(self):
        super().__init__(padding=12, radius=16, accent=C["gold"])
        self.target = "equipe"
        self.edit = QPlainTextEdit()
        self.edit.setPlaceholderText("Escreva para o Codex, o Claude ou a Equipe…   (Ctrl+Enter envia)")
        self.edit.setFixedHeight(74)
        self.edit.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.edit.setStyleSheet(f"QPlainTextEdit {{ background: {C['night']}; border: 1px solid {C['border']}; border-radius: 12px;"
                                f" padding: 10px 12px; font-size: 10.5pt; }}")
        self.edit.installEventFilter(self)
        self.edit.setAccessibleName("Mensagem")
        self.lay.addWidget(self.edit)
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(label("Destino", "dim"))
        self.chips = {}
        for key, text in (("equipe", "Equipe"), ("codex", "Codex"), ("claude", "Claude")):
            b = button(text, AGENT[key]["icon"], "chip", checkable=True, color=AGENT[key]["color"],
                       tip={"equipe": "Codex implementa, Claude revisa, Codex corrige até o veredito",
                            "codex": "Somente o Codex", "claude": "Somente o Claude Code"}[key])
            b.setMinimumWidth(b.sizeHint().width())
            b.clicked.connect(lambda _=False, k=key: self.set_target(k))
            self.chips[key] = b
            row.addWidget(b)
        row.addStretch(1)
        self.mic_btn = button("Falar", "mic", "ghost", "Clique para gravar e clique de novo para transcrever (voz local, Ctrl+M)",
                              checkable=True)
        self.mic_btn.toggled.connect(self.mic.emit)
        self.speak_btn = button("Ouvir", "volume", "ghost", "Ler a última resposta (voz local do Windows)")
        self.speak_btn.clicked.connect(self.speak.emit)
        self.dev_btn = button("", "settings", "ghost", "Escolher microfone e fone")
        self.dev_btn.clicked.connect(self.devices.emit)
        self.live_btn = button("Live", "wave", tip="Conversa por voz contínua com a IA escolhida (Ctrl+Shift+L)")
        self.live_btn.setStyleSheet(f"QPushButton {{ background: {C['violet_bg']}; border: 1px solid {C['violet']}; "
                                    f"color: {C['text']}; }} QPushButton:hover {{ background: {C['hover']}; }}")
        self.live_btn.setIcon(theme.icon("wave", C["violet"]))
        self.live_btn.clicked.connect(self.live.emit)
        row.addWidget(self.live_btn)
        row.addWidget(self.mic_btn)
        row.addWidget(self.dev_btn)
        row.addWidget(self.speak_btn)
        self.lay.addLayout(row)
        perms = QHBoxLayout()
        perms.setSpacing(14)
        self.t_write = Toggle("Alterar arquivos", False, "Permite editar arquivos do projeto (exige repositório Git)")
        self.t_cmds = Toggle("Comandos", False, "Permite rodar testes/builds e comandos no terminal do agente")
        self.t_web = Toggle("Web", True, "Permite que as IAs pesquisem documentação atual por iniciativa própria")
        self.t_tests = Toggle("Testes", False, "O Studio executa os testes do projeto após a implementação")
        self.t_mcp = Toggle("MCPs", False, "Permite usar os servidores MCP já configurados")
        self.t_auto = Toggle("Autônomo", False, "As IAs editam, rodam comandos, builds e testes e terminam a tarefa sem "
                             "pedir confirmação. Antes de cada tarefa o Studio cria um ponto de restauração Git "
                             "(botão Desfazer na Fila). Push, instalações e arquivos fora do projeto continuam bloqueados.")
        self.t_auto.toggled.connect(self._auto_changed)
        self._manual = None
        perms.addWidget(label("Permissões", "dim"))
        perms.addWidget(self.t_auto)
        self.t_pc = Toggle("Usar o PC", False, "Deixa a IA ver a tela e usar mouse e teclado (ex.: abrir o Minecraft e testar "
                           "o mod). Por padrão só a janela do Minecraft; um aviso com botão Parar fica sempre visível.")
        self.t_pc.toggled.connect(self.desktop.emit)
        perms.addWidget(self.t_pc)
        for t in (self.t_write, self.t_cmds, self.t_web, self.t_tests, self.t_mcp):
            perms.addWidget(t)
        perms.addStretch(1)
        self.lay.addLayout(perms)
        row2 = QHBoxLayout()
        row2.setSpacing(6)
        later = button("Depois", "clock", "ghost", "Guarda na fila sem interromper o trabalho atual")
        later.clicked.connect(lambda: self._emit("DEPOIS"))
        idea = button("Ideia", "lightbulb", "ghost", "Registra uma ideia (fila + rascunho no Segundo Cérebro)")
        idea.clicked.connect(lambda: self._emit("IDEIA"))
        self.stop_btn = button("Parar", "stop", "danger", "Interrompe a tarefa em execução neste projeto")
        self.stop_btn.clicked.connect(self.stop.emit)
        self.send_btn = button("Enviar", "send", "primary")
        self.send_btn.setMinimumWidth(110)
        self.send_btn.clicked.connect(lambda: self._emit(""))
        self.hint = label("DEPOIS/IDEIA não interrompem · PARALELO usa worktrees", "dim")
        self.hint.setToolTip("DEPOIS: e IDEIA: vão para a fila sem interromper • AGORA: pede confirmação para interromper"
                             " • PARALELO: seguido de linhas '@codex: …' e '@claude: …' divide o trabalho em worktrees Git")
        self.hint.setMinimumWidth(10)
        self.hint.setStyleSheet(f"color: {C['dim']}; font-size: 8pt;")
        row2.addWidget(self.hint, 1)
        row2.addWidget(later)
        row2.addWidget(idea)
        row2.addWidget(self.stop_btn)
        row2.addWidget(self.send_btn)
        self.lay.addLayout(row2)
        self.set_target("equipe")

    def set_target(self, key: str):
        self.target = key
        for k, b in self.chips.items():
            b.setChecked(k == key)

    def eventFilter(self, obj, e):
        if obj is self.edit and e.type() == e.Type.KeyPress:
            if e.key() in (Qt.Key_Return, Qt.Key_Enter) and e.modifiers() & Qt.ControlModifier:
                self._emit("")
                return True
        return super().eventFilter(obj, e)

    def _emit(self, forced: str):
        text = self.edit.toPlainText().strip()
        if text:
            self.send.emit(text, self.target, forced)

    def permissions(self) -> dict:
        return {"write": self.t_write.isChecked(), "commands": self.t_cmds.isChecked(), "web": self.t_web.isChecked(),
                "run_tests": self.t_tests.isChecked(), "mcp": self.t_mcp.isChecked(),
                "autonomous": self.t_auto.isChecked(), "desktop": self.t_pc.isChecked()}

    def set_desktop(self, on: bool):
        self.t_pc.blockSignals(True)
        self.t_pc.setChecked(on)
        self.t_pc.blockSignals(False)
        self.t_pc.set_knob(1.0 if on else 0.0)

    def set_autonomous(self, on: bool, notify: bool = False):
        """Reflect the project's autonomous mode: edit/commands/tests are implied and locked on."""
        self.t_auto.blockSignals(True)
        self.t_auto.setChecked(on)
        self.t_auto.blockSignals(False)
        self.t_auto.set_knob(1.0 if on else 0.0)
        self._apply_auto(on)
        if notify:
            self.autonomy.emit(on)

    def _auto_changed(self, on: bool):
        self._apply_auto(on)
        self.autonomy.emit(on)

    def _apply_auto(self, on: bool):
        locked = (self.t_write, self.t_cmds, self.t_tests)
        if on:
            if self._manual is None:
                self._manual = [t.isChecked() for t in locked]
            for t in locked:
                t.setChecked(True)
                t.setEnabled(False)
        else:
            for t, was in zip(locked, self._manual or [t.isChecked() for t in locked]):
                t.setEnabled(True)
                t.setChecked(was)
            self._manual = None


class ChatPage(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.view = ChatView()
        lay.addWidget(self.view, 1)
        self.composer = Composer()
        lay.addWidget(self.composer)

    # ---------------------------------------------------------- history
    def load_history(self, rows: list[dict]):
        self.view.clear()
        last_tid = None
        for r in rows[-160:]:
            when = r["moment"][11:16] if r.get("moment") else None
            if r["kind"] == "user":
                if r["task_id"] != last_tid:
                    self.view.message("user", f"**#{r['task_id']} · @{r['target']}**  \n{r['message']}", when=when)
                last_tid = r["task_id"]
            elif r["kind"] == "message":
                self.view.message(r["agent"] or "studio", r["message"], when=when)
            elif r["kind"] == "verdict":
                self.view.message(r["agent"] or "claude", verdict_md(r["message"]), "final", "verdict", when)
            elif r["kind"] == "error":
                self.view.message("studio", "⚠ " + r["message"][:1500], kind="error", when=when)
            elif r["kind"] == "system":
                self.view.message("studio", r["message"], when=when)

    # ---------------------------------------------------------- live events
    def on_event(self, ev: dict):
        t = ev["type"]
        if t == "agent_event":
            agent, kind, text, stage = ev["agent"], ev["kind"], ev.get("text") or "", ev.get("stage", "")
            card = self.view.agent_card(ev["task_id"], agent, stage)
            if kind == "text":
                card.append(text)
                self.view.last_agent_text = text
            elif kind == "command":
                card.add_activity("terminal", text, C["muted"])
            elif kind == "file_change":
                card.add_activity("edit", "Arquivos: " + text, C["gold"])
            elif kind == "web":
                card.add_activity("globe", text, C["info"])
            elif kind == "tool":
                card.add_activity("sparkle", text, C["dim"])
            elif kind == "todo":
                card.add_activity("queue", text.replace("\n", "  "), C["muted"])
            elif kind == "warning":
                card.add_activity("alert", text, C["warning"])
            elif kind == "error":
                card.add_activity("alert", text, C["danger"])
            elif kind == "log" and ev.get("data", {}).get("model"):
                card.add_activity("info", text, C["dim"])
        elif t == "verdict":
            self.view.message("claude", verdict_md(json.dumps(ev["verdict"], ensure_ascii=False)), "final", "verdict")
        elif t == "quality":
            lines = "\n".join(f"- {c['name']}: **{c['status']}**" for c in ev["checks"])
            self.view.message("studio", "Verificações do Studio:\n" + lines)
        elif t == "task_done":
            status = ev["status"]
            label_ = {"approved": "✅ Aprovada", "rejected": "❌ Reprovada", "pending_review": "⏳ Precisa de revisão humana",
                      "executed": "✔ Turno concluído (valide os resultados)", "error": "⚠ Falhou",
                      "cancelled": "■ Interrompida", "blocked_limit": "⛔ Limite de uso atingido"}.get(status, status)
            kind = "error" if status in ("error", "blocked_limit") else "message"
            self.view.message("studio", f"**Tarefa #{ev['task_id']}: {label_}**\n\n{ev.get('summary', '')[:1500]}", kind=kind)
        elif t == "learning":
            self.view.message("studio", f"📝 {ev['count']} aprendizado(s)/erro(s) aguardando sua revisão em *Segundo Cérebro › Rascunhos*.")


def verdict_md(raw: str) -> str:
    try:
        v = json.loads(raw)
    except ValueError:
        return raw
    icon = {"aprovado": "✅", "reprovado": "❌", "pendente": "⏳"}.get(v.get("veredito"), "•")
    lines = [f"**Veredito da revisão: {icon} {str(v.get('veredito', '?')).upper()}**"]
    for pr in v.get("problemas", [])[:12]:
        lines.append(f"- {pr}")
    if v.get("testes_sugeridos"):
        lines.append("\n*Testes sugeridos:* " + "; ".join(v["testes_sugeridos"][:5]))
    if not v.get("parsed", True):
        lines.append("\n*(o revisor não devolveu um veredito estruturado — tratado como pendente)*")
    return "\n".join(lines)
