"""Main window: sidebar navigation, project bar, pages, and the right status panel."""
from __future__ import annotations

from pathlib import Path
import time

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QFont, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QSizePolicy, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QScrollArea,
                               QStackedWidget, QVBoxLayout, QWidget)

from .. import VERSION
from ..messages import classify_message
from ..orchestrator.engine import Engine
from ..paths import check_project_folder
from ..store import Store
from ..usage import claude_snapshot
from ..vault.todo import read_todo
from . import theme
from .common import Bridge, bridge, open_path, run_bg
from .dialogs import ProjectDialog, QuickChat
from .mascot import Mascot
from .page_chat import ChatPage
from .page_system import DiagnosticsPage, SettingsPage, UsagePage, STATE_COLORS
from .page_work import AgentsPage, MemoryPage, QueuePage
from .theme import AGENT, C
from .voice_ui import VoiceController
from .widgets import Card, Dot, Header, Meter, Pill, SpriteView, Stepper, button, icon_label, label

NAV = [("chat", "chat", "Conversa"), ("queue", "queue", "Fila de tarefas"), ("memory", "brain", "Segundo Cérebro"),
       ("agents", "agents", "Agentes e skills"), ("usage", "gauge", "Uso e limites"), ("diag", "pulse", "Diagnóstico"),
       ("settings", "settings", "Configurações")]


class MascotCard(QFrame):
    def __init__(self, mascot: Mascot, on_chat):
        super().__init__()
        self.m = mascot
        agent = mascot.agent
        a = AGENT[agent]
        self.setObjectName("mcard")
        self.setStyleSheet(f"QFrame#mcard {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {a['bg']}, stop:1 #17112A);"
                           f" border: 1px solid {C['border']}; border-radius: 14px; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 10)
        lay.setSpacing(2)
        self.sprite = SpriteView(a["color"])
        self.sprite.setMinimumSize(100, 120)
        self.sprite.setToolTip(f"Duplo clique: chat rápido com {a['name']} • botão direito: expressões")
        self.sprite.mouseDoubleClickEvent = lambda e: on_chat(agent)
        lay.addWidget(self.sprite, 1)
        name = label(mascot.profile["name"].upper())
        name.setAlignment(Qt.AlignCenter)
        name.setStyleSheet(f"color: {a['color']}; font-family: '{theme.FONT_SERIF}'; font-size: 14pt; letter-spacing: 2px;")
        lay.addWidget(name)
        sub = label(mascot.profile["agent"].upper(), "dim")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet(f"color: {C['muted']}; font-size: 7.5pt; font-weight: 600; letter-spacing: 1px;")
        lay.addWidget(sub)
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addStretch(1)
        self.dot = Dot(C["dim"], 8)
        self.state = label("Aguardando", "muted")
        self.state.setStyleSheet(f"color: {C['muted']}; font-size: 8pt;")
        row.addWidget(self.dot)
        row.addWidget(self.state)
        row.addStretch(1)
        lay.addLayout(row)
        mascot.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self.sprite.set_image(self.m.image())
        self.sprite.bob = 1 if (self.m.state == "running" and (self.m.tick // 4) % 2) else 0
        self.state.setText(self.m.label)
        color = {"running": C["violet"], "success": C["success"], "approved": C["success"], "error": C["danger"],
                 "limit": C["danger"], "speaking": C["gold"], "listening": C["gold"]}.get(self.m.state, C["dim"])
        self.dot.set_color(color, self.m.state in ("running", "listening", "speaking"))


class MainWindow(QMainWindow):
    def __init__(self, store: Store, engine: Engine, demo: bool = False):
        super().__init__()
        self.store, self.engine, self.demo = store, engine, demo
        self.bridge: Bridge = bridge()
        engine.subscribe(self.bridge.listener)
        self.bridge.event.connect(self.on_event)
        self.pid: int | None = store.get_setting("ui.last_project")
        if self.pid is not None and not any(p["id"] == self.pid for p in store.projects()):
            self.pid = None
        self.setWindowTitle(f"Kaguya Studio {VERSION}" + (" — DEMONSTRAÇÃO (CLIs simuladas)" if demo else ""))
        self.setWindowIcon(QIcon(str(theme.asset("branding/kaguya.ico"))))
        self.resize(1480, 920)
        self.setMinimumSize(1180, 720)
        self.mascots = {a: Mascot(a, engine.home / f"mascote_{a}.json") for a in ("codex", "claude")}
        for m in self.mascots.values():
            m.open_chat.connect(self.quick_chat)
            m.open_studio.connect(self.bring_to_front)
        self.task_started_at: float | None = None
        self._build()
        self.voice = VoiceController(self)
        self._timer = QTimer(self, interval=220)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        QShortcut(QKeySequence("Ctrl+1"), self, lambda: self.go("chat"))
        QShortcut(QKeySequence("Ctrl+2"), self, lambda: self.go("queue"))
        QShortcut(QKeySequence("Ctrl+3"), self, lambda: self.go("memory"))
        QShortcut(QKeySequence("Ctrl+N"), self, self.add_project)
        QShortcut(QKeySequence("Ctrl+L"), self, lambda: self.chat.composer.edit.setFocus())
        QShortcut(QKeySequence("Ctrl+M"), self, lambda: self.chat.composer.mic_btn.toggle())
        self.refresh_all()
        for m in self.mascots.values():
            if m.prefs.visible:
                m.show_window()

    # ------------------------------------------------------------------ build
    def _build(self):
        root = QWidget()
        root.setObjectName("Root")
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.header = Header(self.demo)
        if self.demo:
            self.header.right.addWidget(Pill("MODO DEMONSTRAÇÃO • CLIs simuladas", C["warning"]))
        self.header.right.addWidget(Pill(f"v{VERSION}", C["gold"]))
        v.addWidget(self.header)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._sidebar())
        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(16, 14, 16, 14)
        cl.setSpacing(12)
        cl.addWidget(self._project_bar())
        self.stack = QStackedWidget()
        self.chat = ChatPage()
        self.queue = QueuePage(self)
        self.memory = MemoryPage(self)
        self.agents = AgentsPage(self)
        self.usage = UsagePage(self)
        self.diag = DiagnosticsPage(self)
        self.settings = SettingsPage(self)
        self.pages = {"chat": self.chat, "queue": self.queue, "memory": self.memory, "agents": self.agents,
                      "usage": self.usage, "diag": self.diag, "settings": self.settings}
        for p in self.pages.values():
            self.stack.addWidget(p)
        cl.addWidget(self.stack, 1)
        body.addWidget(center, 1)
        body.addWidget(self._right_panel())
        v.addLayout(body, 1)
        self.toast_label = QLabel(root)
        self.toast_label.setStyleSheet(f"background: {C['elevated']}; border: 1px solid {C['gold_d']}; border-radius: 10px;"
                                       f" padding: 9px 14px; color: {C['text']};")
        self.toast_label.hide()
        self.setCentralWidget(root)
        c = self.chat.composer
        c.send.connect(self.send_message)
        c.stop.connect(self.stop_task)
        c.speak.connect(lambda: self.voice.speak(self.chat.view.last_agent_text))
        c.mic.connect(lambda on: self.voice.ptt(on))

    def _sidebar(self) -> QWidget:
        side = QFrame()
        self.side = side
        side.setFixedWidth(232)
        side.setStyleSheet(f"QFrame#side {{ background: {C['sidebar']}; border-right: 1px solid {C['border_soft']}; }}")
        side.setObjectName("side")
        lay = QVBoxLayout(side)
        lay.setContentsMargins(12, 16, 12, 14)
        lay.setSpacing(3)
        self.side_titles = [label("ESPAÇO DE TRABALHO", "section"), label("PROJETOS", "section")]
        lay.addWidget(self.side_titles[0])
        lay.addSpacing(4)
        self.nav_group = QButtonGroup(self)
        self.nav_buttons = {}
        for key, ic, text in NAV:
            b = button(text, ic, "nav", checkable=True)
            b.setIconSize(QSize(18, 18))
            b.clicked.connect(lambda _=False, k=key: self.go(k))
            self.nav_group.addButton(b)
            self.nav_buttons[key] = b
            lay.addWidget(b)
        self.queue_badge = Pill("0", C["violet"])
        lay.addSpacing(14)
        lay.addWidget(self.side_titles[1])
        lay.addSpacing(4)
        self.project_box = QVBoxLayout()
        self.project_box.setSpacing(2)
        lay.addLayout(self.project_box)
        self.project_group = QButtonGroup(self)
        lay.addStretch(1)
        add = button("Vincular projeto", "folder-plus", tip="Ctrl+N")
        add.setStyleSheet(f"QPushButton {{ background: {C['gold_bg']}; border: 1px solid #6B5330; color: {C['gold']}; padding: 9px; }}"
                          f"QPushButton:hover {{ border-color: {C['gold']}; }}")
        add.setIcon(theme.icon("folder-plus", C["gold"]))
        add.clicked.connect(self.add_project)
        self.add_btn = add
        lay.addWidget(add)
        return side

    def _project_bar(self) -> QWidget:
        card = Card(padding=12, radius=14, accent=C["gold"])
        card.lay.setSpacing(6)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.p_icon = icon_label("folder", C["gold"], 26)
        row.addWidget(self.p_icon)
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(label("PROJETO ATUAL", "section"))
        self.p_name = label("Nenhum projeto vinculado")
        self.p_name.setStyleSheet(f"font-family: '{theme.FONT_DISPLAY}'; font-size: 14pt; font-weight: 600;")
        col.addWidget(self.p_name)
        row.addLayout(col)
        row.addSpacing(8)
        self.p_path = button("", "folder-open", "ghost", "Abrir a pasta do projeto")
        self.p_path.clicked.connect(lambda: self.pid is not None and open_path(self.store.project(self.pid)["directory"]))
        row.addWidget(self.p_path, 1, Qt.AlignLeft)
        self.p_git = Pill("", C["muted"])
        self.p_vault = Pill("", C["muted"])
        row.addWidget(self.p_git)
        row.addWidget(self.p_vault)
        edit = button("", "edit", "ghost", "Editar projeto (pastas, vault, testes)")
        edit.clicked.connect(self.edit_project)
        row.addWidget(edit)
        card.lay.addLayout(row)
        self.p_status = label("", "muted")
        self.p_status.setStyleSheet(f"color: {C['muted']}; font-size: 8.5pt;")
        card.lay.addWidget(self.p_status)
        return card

    def _right_panel(self) -> QWidget:
        panel = QFrame()
        self.right = panel
        panel.setObjectName("right")
        panel.setFixedWidth(336)
        panel.setStyleSheet(f"QFrame#right {{ background: {C['sidebar']}; border-left: 1px solid {C['border_soft']}; }}")
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setMinimumWidth(0)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(12, 14, 14, 14)
        lay.setSpacing(12)
        duo = QHBoxLayout()
        duo.setSpacing(8)
        self.mcards = {a: MascotCard(self.mascots[a], self.quick_chat) for a in ("codex", "claude")}
        for a in ("codex", "claude"):
            duo.addWidget(self.mcards[a], 1)
        lay.addLayout(duo)
        # agent status rows
        st = Card(padding=12)
        st.lay.addWidget(label("CONEXÃO DAS IAs", "section"))
        self.cli_rows = {}
        for a in ("codex", "claude"):
            r = QHBoxLayout()
            r.addWidget(icon_label(AGENT[a]["icon"], AGENT[a]["color"], 18))
            n = label(AGENT[a]["name"])
            n.setStyleSheet("font-weight: 600;")
            r.addWidget(n)
            r.addStretch(1)
            pill = Pill("não verificado", C["muted"])
            r.addWidget(pill)
            st.lay.addLayout(r)
            self.cli_rows[a] = pill
        chk = button("Verificar conexões", "refresh", "ghost")
        chk.clicked.connect(self.check_clis)
        st.lay.addWidget(chk)
        lay.addWidget(st)
        # running task
        tk = Card(padding=12, accent=C["violet"])
        head = QHBoxLayout()
        head.addWidget(label("TAREFA EM EXECUÇÃO", "section"))
        head.addStretch(1)
        self.t_clock = label("", "dim")
        head.addWidget(self.t_clock)
        tk.lay.addLayout(head)
        self.t_title = label("Nenhuma tarefa em andamento", "muted", wrap=True)
        tk.lay.addWidget(self.t_title)
        self.stepper = Stepper()
        tk.lay.addWidget(self.stepper)
        lay.addWidget(tk)
        # limits
        lm = Card(padding=12)
        lh = QHBoxLayout()
        lh.addWidget(label("LIMITES DA ASSINATURA", "section"))
        lh.addStretch(1)
        more = button("", "chevron-right", "ghost", "Uso e limites")
        more.clicked.connect(lambda: self.go("usage"))
        lh.addWidget(more)
        lm.lay.addLayout(lh)
        self.limit_rows = {}
        for a in ("codex", "claude"):
            r = QHBoxLayout()
            r.addWidget(icon_label(AGENT[a]["icon"], AGENT[a]["color"], 16))
            meter = Meter(AGENT[a]["color"])
            txt = label("indisponível", "dim")
            txt.setMinimumWidth(84)
            txt.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            r.addWidget(meter, 1)
            r.addWidget(txt)
            lm.lay.addLayout(r)
            self.limit_rows[a] = (meter, txt)
        self.limit_note = label("Somente dados oficiais; sem número inventado.", "dim", wrap=True)
        self.limit_note.setStyleSheet(f"color: {C['dim']}; font-size: 7.8pt;")
        lm.lay.addWidget(self.limit_note)
        lay.addWidget(lm)
        # vault
        vc = Card(padding=12, pattern=True)
        vh = QHBoxLayout()
        vh.addWidget(icon_label("brain", C["violet"], 16))
        vtitle = label("SEGUNDO CÉREBRO", "section")
        vtitle.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        vh.addWidget(vtitle, 1)
        vh.addStretch(1)
        self.v_state = Pill("", C["muted"])
        vh.addWidget(self.v_state)
        vc.lay.addLayout(vh)
        grid = QHBoxLayout()
        self.v_stats = {}
        for key, title in (("notes", "Notas"), ("drafts", "Rascunhos"), ("todo", "todo.md")):
            box = QVBoxLayout()
            n = label("—")
            n.setStyleSheet(f"font-family: '{theme.FONT_DISPLAY}'; font-size: 13pt; font-weight: 600; color: {C['text']};")
            n.setAlignment(Qt.AlignCenter)
            t = label(title, "dim")
            t.setAlignment(Qt.AlignCenter)
            t.setStyleSheet(f"color: {C['dim']}; font-size: 7.8pt;")
            box.addWidget(n)
            box.addWidget(t)
            grid.addLayout(box, 1)
            self.v_stats[key] = n
        vc.lay.addLayout(grid)
        lay.addWidget(vc)
        lay.addStretch(1)
        sc.setWidget(inner)
        outer.addWidget(sc)
        return panel

    # -------------------------------------------------------------- responsive
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.apply_layout_mode()

    def apply_layout_mode(self):
        w = self.width()
        compact = w < 1320
        mode = "compact" if compact else "medium" if w < 1520 else "wide"
        if getattr(self, "_mode", None) == mode:
            return
        self._mode = mode
        self.side.setFixedWidth(68 if compact else 204 if mode == "medium" else 232)
        self.right.setFixedWidth(292 if mode != "wide" else 336)
        for t in self.side_titles:
            t.setVisible(not compact)
        for key, ic, text in NAV:
            b = self.nav_buttons[key]
            b.setText("" if compact else (b.property("full") or text))
            b.setToolTip(text)
        self.add_btn.setText("" if compact else "Vincular projeto")
        self.refresh_projects()

    # -------------------------------------------------------------- navigation
    def go(self, key: str):
        self.stack.setCurrentWidget(self.pages[key])
        self.nav_buttons[key].setChecked(True)
        page = self.pages[key]
        if hasattr(page, "refresh"):
            page.refresh()

    def bring_to_front(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def toast(self, text: str, ms: int = 4200):
        self.toast_label.setText(text)
        self.toast_label.adjustSize()
        self.toast_label.setMaximumWidth(620)
        cw = self.centralWidget()
        self.toast_label.move((cw.width() - self.toast_label.width()) // 2, cw.height() - self.toast_label.height() - 22)
        self.toast_label.show()
        self.toast_label.raise_()
        QTimer.singleShot(ms, self.toast_label.hide)

    # ---------------------------------------------------------------- projects
    def select_project(self, pid: int | None):
        self.pid = pid
        self.store.set_setting("ui.last_project", pid)
        self.refresh_all()

    def add_project(self):
        dlg = ProjectDialog(self.store, self)
        if dlg.exec():
            self.select_project(dlg.pid)
            self.toast("Projeto vinculado. Os caminhos ficam salvos ao fechar e reabrir o Studio.")
            if not self.store.effective_vault(self.pid):
                self.toast("Projeto vinculado. Agora conecte o Segundo Cérebro (opcional) em Segundo Cérebro.")

    def edit_project(self):
        if self.pid is None:
            self.add_project()
            return
        dlg = ProjectDialog(self.store, self, self.store.project(self.pid))
        if dlg.exec():
            self.refresh_all()

    def refresh_projects(self):
        while self.project_box.count():
            w = self.project_box.takeAt(0).widget()
            if w:
                if isinstance(w, QAbstractButton):
                    self.project_group.removeButton(w)
                w.deleteLater()
        projects = self.store.projects()
        if self.pid is None and projects:
            self.pid = projects[0]["id"]
        for p in projects[:12]:
            running = self.engine.is_running(p["id"])
            b = button(p["name"], "sakura" if p["id"] == self.pid else "folder", "project", p["directory"], checkable=True,
                       color=C["gold"] if p["id"] == self.pid else C["dim"])
            b.setChecked(p["id"] == self.pid)
            if running:
                b.setText(p["name"] + "   ●")
            if getattr(self, "_mode", "") == "compact":
                b.setText("")
                b.setToolTip(f"{p['name']} — {p['directory']}")
            b.clicked.connect(lambda _=False, i=p["id"]: self.select_project(i))
            self.project_group.addButton(b)
            self.project_box.addWidget(b)
        if not projects:
            self.project_box.addWidget(label("Nenhum projeto ainda.\nVincule a pasta de um projeto para começar.", "dim", wrap=True))

    def refresh_header(self):
        if self.pid is None:
            self.p_name.setText("Nenhum projeto vinculado")
            self.p_path.setText("Clique em “Vincular projeto”")
            self.p_git.set("", C["muted"])
            self.p_vault.set("", C["muted"])
            self.p_status.setText("Vincule a pasta de um projeto. O vault do Obsidian é configurado à parte (Segundo Cérebro).")
            return
        p = self.store.project(self.pid)
        self.p_name.setText(p["name"])
        self.p_path.setText(p["directory"])
        chk = check_project_folder(p["directory"])
        if not chk.ok:
            self.p_git.set("pasta indisponível", C["danger"])
        elif chk.git_root:
            self.p_git.set("Git ✓" if chk.is_git_root else "Git (subpasta)", C["success"])
        else:
            self.p_git.set("sem Git: só leitura", C["warning"])
        vault = self.store.effective_vault(self.pid)
        if vault and Path(vault).is_dir():
            self.p_vault.set("Obsidian ✓" + (" (próprio)" if p.get("vault") else ""), C["violet"])
        elif vault:
            self.p_vault.set("vault indisponível", C["danger"])
        else:
            self.p_vault.set("sem Segundo Cérebro", C["dim"])
        self.refresh_status()

    def refresh_status(self):
        if self.pid is None:
            return
        running = self.engine.current_task(self.pid)
        pend = self.store.pending_count(self.pid)
        full = f"Fila de tarefas  ({pend})" if pend else "Fila de tarefas"
        self.nav_buttons["queue"].setProperty("full", full)
        if getattr(self, "_mode", "") != "compact":
            self.nav_buttons["queue"].setText(full)
        self.p_status.setText(f"Executando tarefa #{running}" if running else
                              f"Pronto • {pend} pendente(s) na fila" if pend else "Pronto • sem tarefas em execução")
        for a, pill in self.cli_rows.items():
            d = self.engine.diagnoses.get(a)
            if d:
                pill.set(d.label, STATE_COLORS.get(d.state, C["muted"]))
                pill.setToolTip(d.report())

    def refresh_side_panels(self):
        snap = claude_snapshot(self.store.latest_usage("claude"))
        stored = self.store.latest_usage("codex")
        for a in ("codex", "claude"):
            meter, txt = self.limit_rows[a]
            windows = []
            if a == "claude" and snap.available:
                windows = [(w.name, w.used_percent) for w in snap.windows]
            elif a == "codex" and stored and stored["payload"].get("available"):
                windows = [(w["name"], w["used_percent"]) for w in stored["payload"].get("windows", [])]
            if windows:
                name, used = windows[0]
                meter.set_value(used)
                txt.setText(f"{100 - used:.0f}% • {name.split(' ')[-1] if '5' not in name else '5 h'}")
                txt.setToolTip("\n".join(f"{n}: {u:.0f}% usado" for n, u in windows))
            else:
                meter.set_value(None)
                txt.setText("indisponível")
        vault = self.store.effective_vault(self.pid) if self.pid is not None else self.store.global_vault()
        idx = self.engine.vault_index(vault)
        if idx:
            st = idx.stats()
            self.v_state.set("vinculado", C["success"])
            self.v_stats["notes"].setText(str(st["notes"]) if st["notes"] else "—")
            ob = self.engine.outbox(self.pid) if self.pid is not None else None
            self.v_stats["drafts"].setText(str(len(ob.drafts())) if ob else "0")
            _p, items = read_todo(Path(vault))
            self.v_stats["todo"].setText(str(sum(1 for i in items if not i.done)) if _p else "—")
        else:
            self.v_state.set("sem vault", C["dim"])
            for n in self.v_stats.values():
                n.setText("—")

    def refresh_all(self):
        self.refresh_projects()
        self.refresh_header()
        self.refresh_side_panels()
        if self.pid is not None:
            self.chat.load_history(self.store.project_history(self.pid))
        else:
            self.chat.view.clear()
            self.chat.view.message("studio", "**Bem-vindo ao Kaguya Studio.**\n\n1. *Vincular projeto*: escolha a pasta do "
                                   "projeto (pode colar o caminho).\n2. *Segundo Cérebro*: conecte o vault do Obsidian "
                                   "(independente dos projetos).\n3. *Diagnóstico*: confirme Codex e Claude Code pela "
                                   "assinatura.\n\nDepois escreva para o Codex, o Claude ou a Equipe.")
        cur = self.stack.currentWidget()
        if hasattr(cur, "refresh"):
            cur.refresh()

    # ------------------------------------------------------------------ tasks
    def confirm_write(self) -> bool:
        p = self.store.project(self.pid)
        chk = check_project_folder(p["directory"])
        if not chk.git_root:
            QMessageBox.warning(self, "Edição bloqueada", "A pasta não está em um repositório Git, então não há como desfazer "
                                "alterações. Rode 'git init' ou desmarque 'Alterar arquivos'.\n\n" + "\n".join(chk.hints))
            return False
        from ..quality import git_snapshot
        snap = git_snapshot(Path(p["directory"]))
        extra = "\n\nATENÇÃO: o Git já tem alterações não commitadas. Faça commit/backup antes." if snap.get("status") else ""
        return QMessageBox.question(self, "Autorizar alterações?", "As IAs poderão editar arquivos deste repositório."
                                    + extra + "\n\nProsseguir?") == QMessageBox.Yes

    def send_message(self, text: str, target: str, forced: str, quick: bool = False) -> bool:
        if self.pid is None:
            QMessageBox.information(self, "Projeto", "Vincule primeiro a pasta de um projeto.")
            return False
        raw = f"{forced}: {text}" if forced else text
        try:
            intent = classify_message(raw, target)
        except ValueError as exc:
            QMessageBox.warning(self, "Mensagem", str(exc))
            return False
        perms = self.chat.composer.permissions() if not quick else {"write": False, "commands": False, "web": True,
                                                                     "run_tests": False, "mcp": False}
        if intent.kind != "execute":
            perms = {k: False for k in perms}
            perms["web"] = True
        if intent.target == "paralelo":
            perms["write"] = True
        if perms["write"] and intent.kind == "execute" and intent.target != "paralelo" and not self.confirm_write():
            return False
        if intent.interrupt and self.engine.is_running(self.pid):
            if QMessageBox.question(self, "AGORA", "Interromper a tarefa em execução? Ela ficará como 'interrompida' e "
                                    "pode ser reenfileirada.") == QMessageBox.Yes:
                self.engine.cancel(self.pid)
                self.engine.wait(self.pid, 15)
        tid = self.engine.submit(self.pid, intent, write=perms["write"], web=perms["web"], commands=perms["commands"],
                                 mcp=perms["mcp"], run_tests=perms["run_tests"])
        self.chat.view.message("user", f"**#{tid} · @{intent.target}**" + (f" · {intent.kind.upper()}" if intent.kind != "execute" else "")
                               + f"  \n{intent.text}")
        if intent.kind == "later":
            self.chat.view.message("studio", f"Tarefa #{tid} guardada para depois. Ela não interrompe nem muda o trabalho atual.")
        elif intent.kind == "idea":
            self.chat.view.message("studio", f"Ideia #{tid} guardada na fila e como rascunho para o Segundo Cérebro.")
        elif self.engine.is_running(self.pid) and self.engine.current_task(self.pid) != tid:
            self.chat.view.message("studio", f"Tarefa #{tid} entrou na fila e começa quando a atual terminar.")
        if not quick:
            self.chat.composer.edit.clear()
        self.refresh_status()
        return True

    def stop_task(self):
        if self.pid is not None and self.engine.cancel(self.pid):
            self.toast("Interrupção solicitada…")
        else:
            self.toast("Não há tarefa em execução neste projeto.")

    def quick_chat(self, agent: str):
        dlg = QuickChat(agent, self)
        dlg.submit.connect(lambda text, target, forced: self.send_message(text, target, forced, quick=True))
        dlg.show()

    def check_clis(self):
        cwd = self.store.project(self.pid)["directory"] if self.pid is not None else None
        for a in ("codex", "claude"):
            self.cli_rows[a].set("verificando…", C["violet"])
            run_bg(lambda a=a: self.engine.diagnose(a, cwd), lambda d: (self.refresh_status(),
                   self.diag.refresh() if self.stack.currentWidget() is self.diag else None))

    # ------------------------------------------------------------------ events
    def on_event(self, ev: dict):
        t = ev["type"]
        if ev.get("pid") not in (None, self.pid) and t not in ("diagnosis", "usage"):
            if t in ("task_done", "worker_idle", "task_started"):
                self.refresh_projects()
            return
        self.chat.on_event(ev)
        if t == "task_started":
            self.task_started_at = time.monotonic()
            self.t_title.setText(f"#{ev['task_id']} · {AGENT.get(ev['target'], AGENT['equipe'])['name']} — {ev['title'][:140]}")
            self.stepper.set_stage(None)
            if ev["target"] in ("codex", "claude"):
                self.stepper.set_stage("implementacao" if ev["target"] == "codex" else "revisao")
            self.refresh_projects()
        elif t == "stage":
            self.stepper.set_stage(ev["stage"], ev.get("cycle", 1), ev.get("max_cycles", 1))
        elif t == "agent_state":
            m = self.mascots.get(ev["agent"])
            if m:
                m.set_state(ev["state"])
            if ev["state"] == "running":
                self.cli_rows[ev["agent"]].set("Em execução", C["violet"])
        elif t == "verdict":
            v = ev["verdict"]["veredito"]
            self.mascots["claude" if self.engine.setting("team.reviewer") == "claude" else "codex"].set_state(
                "approved" if v == "aprovado" else "rejected" if v == "reprovado" else "thinking")
        elif t == "task_done":
            self.task_started_at = None
            st = ev["status"]
            self.stepper.set_stage("final", failed=st not in ("approved", "executed"))
            self.t_title.setText(self.t_title.text() + f"\n→ {st}")
            if self.store.get_setting("voice.autoread", False) and self.chat.view.last_agent_text:
                self.voice.speak(self.chat.view.last_agent_text)
            self.refresh_side_panels()
            self.refresh_projects()
            self.refresh_status()
            if self.stack.currentWidget() is self.queue:
                self.queue.refresh()
        elif t in ("queued", "worker_idle"):
            self.refresh_status()
            if self.stack.currentWidget() is self.queue:
                self.queue.refresh()
            if t == "worker_idle":
                for m in self.mascots.values():
                    if m.state == "running":
                        m.set_state("idle")
        elif t == "usage":
            self.refresh_side_panels()
        elif t == "learning":
            self.refresh_side_panels()
        elif t == "diagnosis":
            self.refresh_status()

    def _tick(self):
        for m in self.mascots.values():
            m.advance()
        if self.task_started_at:
            s = int(time.monotonic() - self.task_started_at)
            self.t_clock.setText(f"{s // 60:02d}:{s % 60:02d}")

    def closeEvent(self, e):
        busy = [p for p in self.store.projects() if self.engine.is_running(p["id"])]
        if busy and QMessageBox.question(self, "Encerrar", "Há IAs trabalhando. Fechar interrompe as tarefas (ficam como "
                                         "'interrompidas' e podem ser retomadas). Fechar mesmo assim?") != QMessageBox.Yes:
            e.ignore()
            return
        for p in busy:
            self.engine.cancel(p["id"])
        self.voice.shutdown()
        for m in self.mascots.values():
            if m.window:
                m.window.close()
        super().closeEvent(e)
