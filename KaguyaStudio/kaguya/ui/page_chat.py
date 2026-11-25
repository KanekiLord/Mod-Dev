"""Conversation page: streaming messages per agent, live activity and the composer."""
from __future__ import annotations

from datetime import datetime
import json
import re

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QTextOption
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout,
                               QWidget)

from . import theme
from .theme import AGENT, C
from .widgets import Card, Pill, Toggle, button, icon_label, label

STAGE_LABELS = {"implementacao": "Implementando", "verificacao": "Verificando", "revisao": "Revisando",
                "correcao": "Corrigindo", "execucao": "Executando", "final": "Veredito"}


# Portrait source for chat avatars: set by the main window (agent -> QImage of the mascot).
_portrait_source = None
_portrait_cache: dict = {}


def set_portrait_source(fn) -> None:
    global _portrait_source
    _portrait_source = fn
    _portrait_cache.clear()


def portrait(agent: str, size: int):
    """Round crop of the mascot's face (top-centre of the sprite), cached per agent/size."""
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QImage, QPainterPath, QPixmap
    key = (agent, size)
    if key in _portrait_cache:
        return _portrait_cache[key]
    img = _portrait_source(agent) if _portrait_source else None
    if img is None or img.isNull():
        return None
    if img.format() != QImage.Format_ARGB32:
        img = img.convertToFormat(QImage.Format_ARGB32)
    # tight bounds of the visible pixels, then a square around the head
    w, h = img.width(), img.height()
    top = next((y for y in range(0, h, 2) if any(img.pixelColor(x, y).alpha() > 40 for x in range(0, w, 4))), 0)
    side = int(min(w, h) * 0.5)
    left = max(0, (w - side) // 2)
    crop = img.copy(QRect(left, max(0, top - side // 20), side, side))
    dpr = 2
    pm = QPixmap(size * dpr, size * dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform, False)
    path = QPainterPath()
    path.addEllipse(0, 0, size * dpr, size * dpr)
    p.setClipPath(path)
    p.fillRect(pm.rect(), QColor(AGENT[agent]["bg"]) if agent in AGENT else QColor(C["elevated"]))
    p.drawImage(pm.rect(), crop)
    p.end()
    pm.setDevicePixelRatio(dpr)
    _portrait_cache[key] = pm
    return pm


class Avatar(QWidget):
    def __init__(self, agent: str, size: int = 38):
        super().__init__()
        self.agent = agent if agent in AGENT else "studio"
        self.size_ = size
        self.setFixedSize(size, size)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        a = AGENT[self.agent]
        pm = portrait(self.agent, self.size_) if self.agent in ("codex", "claude") else None
        if pm is not None:
            p.drawPixmap(0, 0, pm)
        else:
            bg = QColor(a["color"])
            bg.setAlpha(40)
            p.setBrush(bg)
            p.setPen(Qt.NoPen)
            p.drawEllipse(self.rect().adjusted(1, 1, -1, -1))
            ic = theme.pixmap(a["icon"], a["color"], 18)
            p.drawPixmap((self.width() - 18) // 2, (self.height() - 18) // 2, ic)
        ring = QColor(a["color"])
        ring.setAlpha(190)
        p.setPen(ring)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(self.rect().adjusted(1, 1, -1, -1))


class Bubble(QFrame):
    """Chat bubble with a small tail (left for the assistants, right for the user)."""

    def __init__(self, side: str, fill: str, border: str):
        super().__init__()
        self.side, self.fill, self.border = side, QColor(fill), QColor(border)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

    def paintEvent(self, e):
        from PySide6.QtGui import QPainterPath, QPen
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)
        tail = 8
        body = r.adjusted(tail if self.side == "left" else 0, 0, -tail if self.side == "right" else 0, 0)
        path = QPainterPath()
        path.addRoundedRect(body, 14, 14)
        t = QPainterPath()
        if self.side == "left":
            t.moveTo(body.left() + 12, body.top())
            t.lineTo(r.left(), body.top())
            t.lineTo(body.left(), body.top() + 12)
        elif self.side == "right":
            t.moveTo(body.right() - 12, body.top())
            t.lineTo(r.right(), body.top())
            t.lineTo(body.right(), body.top() + 12)
        path = path.united(t)
        p.setPen(QPen(self.border, 1))
        p.setBrush(self.fill)
        p.drawPath(path)


class MessageCard(QFrame):
    """One message row: avatar + bubble (assistants, left), bubble (user, right), or a centred notice."""

    def __init__(self, agent: str, body: str, stage: str = "", when: str | None = None, kind: str = "message"):
        super().__init__()
        self.agent, self.kind = agent, kind
        a = AGENT.get(agent, AGENT["studio"])
        accent = a["color"]
        side = "right" if agent == "user" else "left" if agent in ("codex", "claude", "equipe", "paralelo") else "center"
        self.side = side
        fill = {"right": "#3A2A63", "left": "#1E1734", "center": "#1A1430"}[side]
        border = C["border"]
        if kind == "verdict":
            border = C["gold"]
        elif kind == "error":
            border = C["danger"]
        elif side == "left":
            border = QColor(accent).darker(160).name()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.bubble = Bubble(side if side != "center" else "none", fill, border)
        lay = QVBoxLayout(self.bubble)
        tail = 8 if side != "center" else 0
        lay.setContentsMargins(12 + (tail if side == "left" else 0), 8, 12 + (tail if side == "right" else 0), 6)
        lay.setSpacing(3)
        if side == "left":
            row.addWidget(Avatar(agent, 40), 0, Qt.AlignTop)
            mascot = a.get("mascot")
            head = QHBoxLayout()
            head.setSpacing(6)
            name = label(f"{mascot} · {a['name']}" if mascot and mascot != a["name"] else a["name"])
            name.setStyleSheet(f"color: {accent}; font-weight: 700; font-size: 9pt;")
            head.addWidget(name)
            if stage:
                head.addWidget(Pill(STAGE_LABELS.get(stage.split(":")[0], stage), accent))
            head.addStretch(1)
            lay.addLayout(head)
        self.body = QLabel()
        self.body.setWordWrap(True)
        self.body.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        self.body.setOpenExternalLinks(True)
        self.body.setTextFormat(Qt.MarkdownText)
        self.body.setStyleSheet(f"color: {C['text'] if side != 'center' else C['muted']}; "
                                f"font-size: {'9.6pt' if side != 'center' else '8.8pt'};")
        self.body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lay.addWidget(self.body)
        self.activity = QVBoxLayout()
        self.activity.setSpacing(3)
        lay.addLayout(self.activity)
        foot = QHBoxLayout()
        foot.addStretch(1)
        t = label(when or datetime.now().strftime("%H:%M"), "dim")
        t.setStyleSheet(f"color: {C['dim']}; font-size: 7.6pt;")
        foot.addWidget(t)
        if side == "right":
            tick = label("✓✓")
            tick.setStyleSheet(f"color: {C['violet']}; font-size: 7.6pt;")
            foot.addWidget(tick)
        lay.addLayout(foot)
        if side == "right":
            row.addStretch(1)
            row.addWidget(self.bubble, 0)
        elif side == "left":
            row.addWidget(self.bubble, 0)
            row.addStretch(1)
        else:
            row.addStretch(1)
            row.addWidget(self.bubble, 0)
            row.addStretch(1)
        self.set_body(body)
        self.fit(700)

    def fit(self, width: int | None = None):
        """Bubbles grow with the text up to ~78% of the conversation width (like messaging apps)."""
        if width is not None:
            self._avail = width
        width = getattr(self, "_avail", 700)
        frac = 0.78 if self.side != "center" else 0.7
        max_w = max(260, int(width * frac)) - (50 if self.side == "left" else 0)
        self.bubble.setMaximumWidth(max_w)
        pad = 34
        plain = re.sub(r"[*_`#>]|\[([^\]]*)\]\([^)]*\)", r"\1", getattr(self, "_text", ""))
        fm = self.body.fontMetrics()
        natural = max([fm.horizontalAdvance(line) for line in plain.splitlines()] or [0]) + 8
        if self.activity.count():
            natural = max(natural, 380)
        self.body.setMinimumWidth(max(60, min(natural, max_w - pad)))

    def set_body(self, text: str):
        self._text = text
        shown = re.sub(r"```(?:json)?\s*\{[^`]*?\"veredito\"[^`]*?\}\s*```", "*(veredito estruturado abaixo)*", text)
        self.body.setText(shown[:12000])
        self.body.setVisible(bool(text.strip()))
        if hasattr(self, "_avail"):
            self.fit()

    def append(self, text: str):
        self.set_body((self._text + "\n\n" + text).strip())

    def add_activity(self, icon_name: str, text: str, color: str = C["muted"]):
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(icon_label(icon_name, color, 14))
        lb = label(text[:240], "code")
        lb.setStyleSheet(f"color: {color}; font-family: '{theme.FONT_MONO}'; font-size: 8.2pt;")
        lb.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lb.setWordWrap(True)
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
        self.lay.setSpacing(8)
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

    def resizeEvent(self, e):
        super().resizeEvent(e)
        w = self.viewport().width()
        for i in range(self.lay.count()):
            card = self.lay.itemAt(i).widget()
            if isinstance(card, MessageCard):
                card.fit(w)

    def add(self, card: MessageCard) -> MessageCard:
        card.fit(self.viewport().width())
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
    attach = Signal()
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
        self.attachments: list[dict] = []          # {"name", "text", "image"} approved in the preview
        self.attach_row = QHBoxLayout()
        self.attach_row.setSpacing(6)
        self.lay.addLayout(self.attach_row)
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
        self.attach_btn = button("Anexar", "file", "ghost", "Anexar arquivos (log, código, Word, Excel, PowerPoint, PDF, "
                                 "ZIP/JAR, imagem): o Studio lê, mostra a prévia e só envia o que você aprovar")
        self.attach_btn.clicked.connect(self.attach.emit)
        row.addWidget(self.attach_btn)
        row.addWidget(self.mic_btn)
        row.addWidget(self.dev_btn)
        row.addWidget(self.speak_btn)
        self.lay.addLayout(row)
        perms = QHBoxLayout()
        perms.setSpacing(14)
        self.t_write = Toggle("Arquivos", False, "Permite editar arquivos do projeto (exige repositório Git)")
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


def _chip(text: str, on_remove) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(8, 2, 4, 2)
    lay.setSpacing(4)
    lab = QLabel("📎 " + text)
    lab.setStyleSheet(f"color: {C['text']};")
    x = QPushButton("×")
    x.setFixedSize(18, 18)
    x.setToolTip("Remover anexo")
    x.setStyleSheet(f"QPushButton {{ border: none; color: {C['muted']}; }} QPushButton:hover {{ color: {C['danger']}; }}")
    x.clicked.connect(on_remove)
    lay.addWidget(lab)
    lay.addWidget(x)
    w.setStyleSheet(f"background: {C['surface2']}; border-radius: 9px;")
    return w


def _composer_add_attachment(self, item: dict):
    self.attachments.append(item)
    self._render_attachments()


def _composer_remove_attachment(self, item: dict):
    if item in self.attachments:
        self.attachments.remove(item)
    self._render_attachments()


def _composer_render_attachments(self):
    while self.attach_row.count():
        it = self.attach_row.takeAt(0)
        if it.widget():
            it.widget().deleteLater()
    for item in self.attachments:
        self.attach_row.addWidget(_chip(item["name"], lambda _=False, i=item: self.remove_attachment(i)))
    if self.attachments:
        self.attach_row.addStretch(1)


def _composer_take_attachments(self) -> tuple[str, list[str], str]:
    """(context for the assistant, image files, short label) — and clears the list."""
    items, self.attachments = self.attachments, []
    self._render_attachments()
    context = "\n\n".join(i["text"] for i in items if i.get("text"))
    images = [i["image"] for i in items if i.get("image")]
    label = ", ".join(i["name"] for i in items)
    return context, images, label


Composer.add_attachment = _composer_add_attachment
Composer.remove_attachment = _composer_remove_attachment
Composer._render_attachments = _composer_render_attachments
Composer.take_attachments = _composer_take_attachments
