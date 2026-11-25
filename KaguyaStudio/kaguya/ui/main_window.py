"""Main window: sidebar navigation, project bar, pages, and the right status panel."""
from __future__ import annotations

from pathlib import Path
import sqlite3
import sys
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
from .common import Bridge, bridge, open_path, open_url, run_bg
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
        self.sprite.setContextMenuPolicy(Qt.CustomContextMenu)
        self.sprite.customContextMenuRequested.connect(self._menu)
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

    def _menu(self, pos):
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.addAction(theme.icon("chat", C["text"]), "Chat rápido", lambda: self.m.open_chat.emit(self.m.agent))
        menu.addAction(theme.icon("window", C["text"]), "Mascote flutuante", self.m.toggle_window)
        if self.m.variants():
            vm = menu.addMenu("Visual")
            for key, text in self.m.variants():
                act = QAction(text, vm, checkable=True, checked=self.m.prefs.variant == key)
                act.triggered.connect(lambda _=False, k=key: self.m.set_variant(k))
                vm.addAction(act)
        em = menu.addMenu(f"Expressões ({len(self.m.profile['expressions'])})")
        for ex in self.m.profile["expressions"]:
            em.addAction(ex.replace("_", " ").capitalize(), lambda ex=ex: self.m.set_expression(ex))
        menu.exec(self.sprite.mapToGlobal(pos))

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
        # Tag events with their engine so a window only reacts to its own engine (and stops
        # reacting once closed).
        self._engine_tag = id(engine)
        self._listener = lambda d: self.bridge.event.emit({**d, "_engine": self._engine_tag})
        engine.subscribe(self._listener)
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
        self.gh_status = None
        self.repo_state = None
        self._build()
        self.voice = VoiceController(self)
        self._codex_busy = False
        self.audio_in, self.audio_out = [], []
        self._audio_checked = False
        self._audio_timer = QTimer(self, interval=5000)
        self._audio_timer.timeout.connect(lambda: self.check_audio_devices())
        self._audio_timer.start()
        QTimer.singleShot(1500, lambda: self.check_audio_devices(force=True))
        self._limits_timer = QTimer(self, interval=10 * 60 * 1000)
        self._limits_timer.timeout.connect(lambda: self.refresh_codex_limits())
        self._limits_timer.start()
        QTimer.singleShot(3500, lambda: self.refresh_codex_limits())
        QTimer.singleShot(2500, lambda: run_bg(self.refresh_github_status))
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
        c.devices.connect(self.devices_menu)

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
        self.p_git_btn = button("Criar repositório Git", "git", tip="Cria um repositório Git nesta pasta para as IAs "
                                "poderem editar com segurança (dá para desfazer qualquer alteração)")
        self.p_git_btn.clicked.connect(self.create_git_repo)
        self.p_git_btn.hide()
        row.addWidget(self.p_git_btn)
        self.p_gh = button("GitHub", "git", tip="Publicar, salvar versão, enviar e atualizar pelo GitHub")
        self.p_gh.clicked.connect(self.github_menu)
        self.p_gh.hide()
        row.addWidget(self.p_gh)
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

    def create_git_repo(self):
        if self.pid is None:
            return
        from .dialogs import GitInitDialog
        dlg = GitInitDialog(self.store.project(self.pid)["directory"], self)
        if dlg.exec():
            self.refresh_header()
            self.toast("Repositório Git criado. Agora as IAs podem editar com 'Alterar arquivos' (e tudo pode ser desfeito).")

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
        if not projects and getattr(self, "_mode", "") != "compact":
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
        self.p_path.setText(self.p_path.fontMetrics().elidedText(p["directory"], Qt.ElideMiddle, 340))
        self.p_path.setToolTip(f"Abrir a pasta do projeto\n{p['directory']}")
        chk = check_project_folder(p["directory"])
        if not chk.ok:
            self.p_git.set("pasta indisponível", C["danger"])
        elif chk.git_root:
            self.p_git.set("Git ✓" if chk.is_git_root else "Git (subpasta)", C["success"])
        else:
            self.p_git.set("sem Git: só leitura", C["warning"])
        self.p_git_btn.setVisible(chk.ok and not chk.git_root)
        self.p_gh.setVisible(bool(chk.git_root))
        if chk.git_root:
            self.refresh_repo_state()
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
                short = [("5 h" if ("5 hora" in n or "5 h" in n) else "sem." if "7 dias" in n or "Semanal" in n else n[:8], u)
                         for n, u in windows]
                meter.set_value(short[0][1])
                txt.setText("  ".join(f"{n} {100 - u:.0f}%" for n, u in short[:2]))
                txt.setToolTip("Restante por janela (fonte oficial):\n" +
                               "\n".join(f"{n}: {u:.0f}% usado, {100 - u:.0f}% restante" for n, u in windows))
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

    # ------------------------------------------------------------------ audio devices
    def check_audio_devices(self, force: bool = False):
        """Detect plugged/unplugged microphones and headsets (never while recording or speaking)."""
        from ..voice import devices as dv
        if getattr(self, "_audio_busy", False) or not dv.available():
            return
        if not force and hasattr(self, "voice") and self.voice.busy:
            return
        self._audio_busy = True

        def done(res):
            self._audio_busy = False
            ins, outs = res
            if self._audio_checked:
                for ch in filter(None, (dv.diff(self.audio_in, ins, "microfone"), dv.diff(self.audio_out, outs, "saída"))):
                    msg = []
                    if ch.added:
                        msg.append(f"{ch.kind.capitalize()} conectado: {', '.join(ch.added)}")
                    if ch.removed:
                        msg.append(f"{ch.kind.capitalize()} desconectado: {', '.join(ch.removed)}")
                    self.toast(" • ".join(msg))
            for key, lst, kind in (("voice.input_name", ins, "microfone"), ("voice.output_name", outs, "saída")):
                name = self.store.get_setting(key)
                if name and not dv.resolve(name, lst) and self._audio_checked and dv.resolve(name, self.audio_in + self.audio_out):
                    self.toast(f"O {kind} escolhido ({name}) foi desconectado: usando o padrão do Windows até ele voltar.")
            self._audio_checked = True
            self.audio_in, self.audio_out = ins, outs
            self.refresh_devices_ui()

        def fail(exc, tb):
            self._audio_busy = False
        run_bg(lambda: dv.list_devices(refresh=True), done, fail)

    def refresh_devices_ui(self):
        if hasattr(self, "settings"):
            self.settings.fill_devices(self.audio_in, self.audio_out)

    def devices_menu(self):
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QMenu
        from ..voice import devices as dv
        menu = QMenu(self)
        if not dv.available():
            menu.addAction("Acesso ao microfone não instalado nesta cópia").setEnabled(False)
        for title, key, lst, default in (("MICROFONE", "voice.input_name", self.audio_in, "Padrão do Windows"),
                                         ("SAÍDA (FONE/CAIXA)", "voice.output_name", self.audio_out, "Padrão do Windows")):
            menu.addSection(title)
            cur = self.store.get_setting(key)
            for name in [None] + [d.name for d in lst]:
                act = QAction(name or default, menu, checkable=True, checked=(cur == name) or (not cur and name is None))
                act.triggered.connect(lambda _=False, k=key, n=name: (self.store.set_setting(k, n), self.refresh_devices_ui(),
                                                                      self.toast(f"Usando: {n or 'padrão do Windows'}")))
                menu.addAction(act)
        menu.addSeparator()
        menu.addAction("Atualizar dispositivos", lambda: self.check_audio_devices(force=True))
        menu.addAction("Configurações de áudio…", lambda: self.go("settings"))
        btn = self.chat.composer.dev_btn
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    # ------------------------------------------------------------------ github
    def refresh_github_status(self):
        """Runs in a worker thread: diagnose the GitHub CLI (never asks for the token)."""
        from ..github import diagnose
        self.gh_status = diagnose(self.store.get_setting("cli.gh.path") or None, env=self.engine.env)
        return self.gh_status

    def refresh_repo_state(self, fetch: bool = False):
        from ..github import repo_status
        if self.pid is None:
            return
        folder = self.store.project(self.pid)["directory"]
        pid = self.pid

        def done(rs):
            if pid != self.pid:
                return
            self.repo_state = rs
            if rs.github_repo:
                sync = []
                if rs.ahead:
                    sync.append(f"↑{rs.ahead}")
                if rs.behind:
                    sync.append(f"↓{rs.behind}")
                if rs.changed:
                    sync.append(f"✎{rs.changed}")
                self.p_gh.setText("GitHub " + (" ".join(sync) if sync else "✓"))
                self.p_gh.setToolTip(f"{rs.github_repo} • ramo {rs.branch}\n↑ commits a enviar • ↓ a receber • ✎ arquivos sem commit")
            else:
                self.p_gh.setText("Publicar no GitHub" if rs.is_git else "GitHub")
                self.p_gh.setToolTip("Este repositório ainda não está no GitHub")
        run_bg(lambda: repo_status(folder, fetch=fetch), done)

    def github_menu(self):
        from PySide6.QtWidgets import QMenu
        rs = self.repo_state
        menu = QMenu(self)
        if rs and not rs.remote_url:
            menu.addAction(theme.icon("external", C["text"]), "Publicar no GitHub (privado)…", self.gh_publish)
        menu.addAction(theme.icon("check", C["text"]), "Salvar versão (commit)…", self.gh_commit)
        if rs and rs.remote_url:
            menu.addAction(theme.icon("send", C["text"]), "Enviar para o GitHub (push)", lambda: self.gh_action("push"))
            menu.addAction(theme.icon("download", C["text"]), "Atualizar do GitHub (pull)", lambda: self.gh_action("pull"))
            if rs.branch and rs.branch not in ("main", "master"):
                menu.addAction(theme.icon("git", C["text"]), f"Criar pull request de '{rs.branch}'", lambda: self.gh_action("pr"))
            menu.addAction(theme.icon("refresh", C["text"]), "Verificar sincronização", lambda: self.refresh_repo_state(fetch=True))
            if rs.web_url:
                menu.addAction(theme.icon("globe", C["text"]), "Abrir no navegador", lambda: open_url(rs.web_url))
        menu.exec(self.p_gh.mapToGlobal(self.p_gh.rect().bottomLeft()))

    def _need_gh(self) -> str | None:
        st = self.gh_status or self.refresh_github_status()
        if not st.ready:
            QMessageBox.information(self, "GitHub", "A GitHub CLI não está pronta: " + " ".join(st.details + st.fixes) +
                                    "\n\nVeja Diagnóstico › GitHub.")
            self.go("diag")
            return None
        return st.executable

    def gh_publish(self):
        from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QLineEdit, QVBoxLayout
        from ..github import publish, suggest_repo_name
        gh = self._need_gh()
        if not gh:
            return
        folder = self.store.project(self.pid)["directory"]
        dlg = QDialog(self)
        dlg.setWindowTitle("Publicar no GitHub")
        lay = QVBoxLayout(dlg)
        lay.addWidget(label(f"Conta: <b>{self.gh_status.login}</b>", wrap=True))
        lay.addWidget(label("Nome do repositório", "section"))
        name = QLineEdit(suggest_repo_name(folder))
        lay.addWidget(name)
        desc = QLineEdit()
        desc.setPlaceholderText("Descrição (opcional)")
        lay.addWidget(desc)
        private = QCheckBox("Repositório privado (recomendado)")
        private.setChecked(True)
        lay.addWidget(private)
        lay.addWidget(label("Os commits atuais serão enviados. Arquivos ignorados pelo .gitignore (build, run, logs) não sobem.",
                            "muted", wrap=True))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        if not dlg.exec():
            return
        self.toast("Publicando no GitHub…")
        run_bg(lambda: publish(folder, gh, name.text().strip(), private.isChecked(), desc.text()), self._gh_done)

    def gh_commit(self):
        from PySide6.QtWidgets import QInputDialog
        from ..github import commit_all
        rs = self.repo_state
        n = rs.changed if rs else 0
        msg, ok = QInputDialog.getText(self, "Salvar versão (commit)", f"{n} arquivo(s) alterado(s). Descreva a versão:")
        if not ok:
            return
        folder = self.store.project(self.pid)["directory"]
        run_bg(lambda: commit_all(folder, msg), self._gh_done)

    def gh_action(self, kind: str):
        from .. import github as ghm
        folder = self.store.project(self.pid)["directory"]
        if kind == "pr":
            gh = self._need_gh()
            if not gh:
                return
            fn = lambda: ghm.create_pr(folder, gh)
        elif kind == "push":
            fn = lambda: ghm.push(folder)
        else:
            fn = lambda: ghm.pull(folder)
        self.toast({"push": "Enviando…", "pull": "Atualizando…", "pr": "Criando pull request…"}[kind])
        run_bg(fn, self._gh_done)

    def _gh_done(self, res):
        if res.ok:
            self.toast(res.message + (f"  {res.url}" if res.url else ""))
            if res.url and "/pull/" in res.url:
                open_url(res.url)
        else:
            QMessageBox.warning(self, "GitHub", res.message)
        self.refresh_repo_state()

    # ------------------------------------------------------------------ limits
    def _attempt(self, agent: str, ok: bool, message: str = ""):
        from datetime import datetime as _dt
        self.store.set_setting(f"usage.{agent}.last_attempt", {"when": _dt.now().strftime("%d/%m %H:%M"), "ok": ok,
                                                                "message": message})

    def refresh_codex_limits(self, on_done=None, notify: bool = False):
        """Free official query (no model usage). Runs at startup, every 10 min and after Codex tasks."""
        from ..cli import discovery
        from ..usage import read_codex_limits
        if self._codex_busy:
            return
        diag = self.engine.diagnoses.get("codex")
        exe = diag.executable if diag and diag.executable else discovery.find_cli("codex", self.store.get_setting("cli.codex.path"))[0]
        if not exe:
            self._attempt("codex", False, "Codex não encontrado (veja Diagnóstico).")
            if on_done:
                on_done()
            return
        self._codex_busy = True

        def done(snap):
            self._codex_busy = False
            if snap.available:
                self.store.save_usage("codex", snap.source, snap.to_dict())
            self._attempt("codex", snap.available, snap.message)
            self.refresh_side_panels()
            if notify:
                self.toast("Limites do Codex atualizados." if snap.available else f"Codex: {snap.message[:160]}")
            if on_done:
                on_done()

        def fail(exc, tb):
            self._codex_busy = False
            self._attempt("codex", False, str(exc))
            if on_done:
                on_done()
        run_bg(lambda: read_codex_limits(exe, env=self.engine.env), done, fail)

    def refresh_claude_limits(self, on_done=None):
        """Claude has no free query: one minimal message returns the official utilisation."""
        from ..usage import probe_claude_limits
        if not self.store.get_setting("limits.claude_probe_ok", False):
            box = QMessageBox(QMessageBox.Question, "Atualizar limites do Claude",
                              "O Claude Code só informa a utilização da assinatura depois de uma resposta. Para atualizar "
                              "agora, o Studio envia UMA mensagem mínima (\"ok\", modelo mais leve, sem ferramentas), que "
                              "consome uma fração muito pequena da cota.\n\nDurante as tarefas isso é automático.", parent=self)
            yes = box.addButton("Atualizar", QMessageBox.AcceptRole)
            always = box.addButton("Atualizar e não perguntar de novo", QMessageBox.AcceptRole)
            box.addButton("Cancelar", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() not in (yes, always):
                if on_done:
                    on_done()
                return
            if box.clickedButton() is always:
                self.store.set_setting("limits.claude_probe_ok", True)
        try:
            exe, caps = self.engine.ensure_ready("claude", None)
        except Exception as exc:
            self._attempt("claude", False, str(exc))
            self.toast(f"Claude não está pronto: {str(exc)[:160]}")
            if on_done:
                on_done()
            return
        cwd = self.store.project(self.pid)["directory"] if self.pid is not None else str(self.engine.home)

        def done(payload):
            if payload:
                self.store.save_usage("claude", "Claude Code (rate_limit_event • consulta mínima)", payload)
                self._attempt("claude", True)
                self.toast("Limites do Claude atualizados.")
            else:
                self._attempt("claude", False, "O Claude Code respondeu sem dados de utilização.")
            self.refresh_side_panels()
            if on_done:
                on_done()

        def fail(exc, tb):
            self._attempt("claude", False, str(exc))
            self.toast(f"Claude: {str(exc)[:160]}")
            if on_done:
                on_done()
        run_bg(lambda: probe_claude_limits(exe, caps, cwd, env=self.engine.env), done, fail)

    # ------------------------------------------------------------------ events
    def on_event(self, ev: dict):
        if ev.get("_engine") != self._engine_tag:
            return
        try:
            self._handle_event(ev)
        except sqlite3.Error as exc:  # never let a storage hiccup break the UI loop
            print(f"Kaguya: evento ignorado ({ev.get('type')}): {exc}", file=sys.stderr)

    def detach(self):
        if self._listener in self.engine.listeners:
            self.engine.listeners.remove(self._listener)
        try:
            self.bridge.event.disconnect(self.on_event)
        except (RuntimeError, TypeError):
            pass

    def _handle_event(self, ev: dict):
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
            self.refresh_codex_limits()
            self.refresh_repo_state()
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
        self.detach()
        from .common import wait_background
        wait_background(5)
        super().closeEvent(e)
