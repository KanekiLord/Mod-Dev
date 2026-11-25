"""Kaguya Browser: tabs, favourites, history, private tabs, per-tab sharing with Kaguya/Miwa and YouTube Intelligence.

Privacy model (spec 03): a tab is personal by default — no assistant sees it. Sharing is per tab and per assistant,
always visible (coloured frame, ● in the tab title, a banner and a timeline). Only what is visible on the page goes
to the assistant, as data, when the user asks something. Cookies, logins, storage and form values never leave the
browser. Personal tabs keep logins in the Studio's data folder; private tabs keep nothing.
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QRect, Qt, QTimer, QUrl
from PySide6.QtWidgets import (QComboBox, QCompleter, QDialog, QFileDialog, QFrame, QHBoxLayout, QLineEdit,
                               QListWidget, QListWidgetItem, QMenu, QMessageBox, QPushButton, QSplitter, QTabWidget,
                               QTextBrowser, QVBoxLayout, QWidget)

from ..browser import page as pagemod
from ..browser import youtube as yt
from ..browser.data import HOME, SEARCH, BrowserData, to_url
from ..browser.share import NAMES, AccessDenied, ShareRegistry
from .page_webchats import webengine_available
from .theme import AGENT, C
from .widgets import Card, button, label

def _icon_path(name: str, color: str = C["muted"]) -> str:
    """A themed copy of an icon on disk (style sheets need a file; the originals are monochrome templates)."""
    import tempfile
    from .theme import _svg_bytes
    out = Path(tempfile.gettempdir()) / f"kaguya-icon-{name}-{color.strip('#')}.svg"
    try:
        if not out.exists():
            out.write_bytes(_svg_bytes(name, color))
    except OSError:
        pass
    return out.as_posix()


EXECUTABLES = (".exe", ".msi", ".bat", ".cmd", ".ps1", ".vbs", ".scr", ".jar", ".com", ".appx", ".msix")
DONE = ("executed", "approved", "pending_review", "failed", "cancelled", "interrupted", "error", "rejected", "done")


def home_html(favorites: list[dict], engine: str) -> str:
    import html
    tiles = "".join(f'<a class="t" href="{html.escape(f["url"])}">{html.escape(f["title"][:40])}<span>'
                    f'{html.escape(f["url"][:50])}</span></a>' for f in favorites[:24]) or \
        '<p class="e">Sem favoritos ainda: abra um site e clique na estrela ☆.</p>'
    action = SEARCH.get(engine, SEARCH["duckduckgo"])[1].split("?")[0]
    field = "search_query" if engine == "youtube" else "q"
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Início</title><style>
    body{{background:#120d1c;color:#e9e3f5;font-family:Segoe UI,Inter,sans-serif;margin:0;padding:48px 8%}}
    h1{{font-weight:300;letter-spacing:.3em;color:#e8c27a;margin:0 0 6px}} p.s{{color:#9d90b8;margin:0 0 26px}}
    form{{display:flex;gap:8px;margin-bottom:34px}} input{{flex:1;padding:13px 16px;border-radius:12px;border:1px solid
    #3a2d55;background:#1c1530;color:#fff;font-size:15px}} button{{padding:0 20px;border-radius:12px;border:0;
    background:#e8c27a;color:#24170a;font-weight:600}} .g{{display:grid;grid-template-columns:repeat(auto-fill,
    minmax(190px,1fr));gap:12px}} a.t{{display:block;padding:14px;border-radius:12px;background:#1c1530;border:1px
    solid #2e2445;color:#e9e3f5;text-decoration:none}} a.t span{{display:block;color:#8a7da6;font-size:11px;
    margin-top:6px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}} .e{{color:#8a7da6}}</style></head>
    <body><h1>KAGUYA BROWSER</h1><p class="s">Abas pessoais: nenhuma IA vê o que você abre, até você compartilhar
    uma aba.</p><form action="{action}"><input name="{field}" placeholder="Pesquisar ou digitar endereço" autofocus>
    <button>Ir</button></form><div class="g">{tiles}</div></body></html>"""


class BrowserPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.data = BrowserData(win.engine.home / "navegador" / "navegador.sqlite3")
        self.shares = ShareRegistry(on_change=lambda tab_id: QTimer.singleShot(0, self, lambda: self._share_changed(tab_id)))
        self.views: dict[int, object] = {}       # tab_id → QWebEngineView
        self.private: set[int] = set()
        self.reports: dict[int, yt.Report] = {}
        self.pending: dict[int, tuple[int, str]] = {}   # task id → (tab id, agent)
        self.last_answer: dict[int, str] = {}
        self._next_id = 1
        self._profiles: dict[str, object] = {}
        self.bridge = None
        self.confirm_hook = None          # tests: callable(message) -> bool instead of a dialog
        self._dialogs: list = []
        self._started = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        # toolbar
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.back_btn = button("", "skip-back", "ghost", "Voltar")
        self.fwd_btn = button("", "skip-forward", "ghost", "Avançar")
        self.reload_btn = button("", "refresh", "ghost", "Recarregar")
        self.home_btn = button("", "home", "ghost", "Página inicial")
        self.address = QLineEdit()
        self.address.setPlaceholderText("Pesquisar ou digitar endereço")
        self.address.returnPressed.connect(lambda: self.open_url(self.address.text()))
        self.completer = QCompleter([])
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchContains)
        self.address.setCompleter(self.completer)
        self.address.textEdited.connect(lambda t: self.completer.model().setStringList(self.data.suggestions(t)))
        self.star = button("☆", None, "ghost", "Adicionar/remover dos favoritos", checkable=True)
        self.star.clicked.connect(self.toggle_favorite)
        self.menu_btn = button("Favoritos", "list", "ghost", "Favoritos, histórico e mecanismo de pesquisa")
        self.menu = QMenu(self.menu_btn)
        self.menu.aboutToShow.connect(self._fill_menu)
        self.menu_btn.setMenu(self.menu)
        self.back_btn.clicked.connect(lambda: self._cur() and self._cur().back())
        self.fwd_btn.clicked.connect(lambda: self._cur() and self._cur().forward())
        self.reload_btn.clicked.connect(lambda: self._cur() and self._cur().reload())
        self.home_btn.clicked.connect(lambda: self.open_url(HOME))
        for w in (self.back_btn, self.fwd_btn, self.reload_btn, self.home_btn):
            bar.addWidget(w)
        bar.addWidget(self.address, 1)
        bar.addWidget(self.star)
        bar.addWidget(self.menu_btn)
        lay.addLayout(bar)
        # sharing strip
        strip = QHBoxLayout()
        strip.setSpacing(6)
        self.share_label = label("", "dim")
        self.share_btns = {}
        for a in ("codex", "claude"):
            b = button(AGENT[a]['mascot'], a, "chip", checkable=True,
                       tip=f"{AGENT[a]['mascot']} passa a poder ler ESTA aba quando você perguntar algo")
            b.clicked.connect(lambda on, a=a: self.set_share(a, on))
            self.share_btns[a] = b
        self.control_btns = {}
        for a in ("codex", "claude"):
            b = button(AGENT[a]['mascot'], "window", "chip", checkable=True,
                       tip=f"Controle supervisionado: {AGENT[a]['mascot']} pode rolar, clicar e digitar SÓ nesta aba "
                           "(nunca senhas; compras/envios/logins pedem sua confirmação). Você assume quando quiser.")
            b.clicked.connect(lambda on, a=a: self.set_control(a, on))
            self.control_btns[a] = b
        self.timeline_btn = button("Linha do tempo", "clock", "ghost", "Quem acessou esta aba e quando", checkable=True)
        self.timeline_btn.clicked.connect(lambda on: self.timeline.setVisible(on))
        lay.addWidget(self.share_label)   # status on its own line (never cut)
        strip.addWidget(label("Compartilhar com:", "dim"))
        for b in self.share_btns.values():
            strip.addWidget(b)
        strip.addSpacing(14)
        strip.addWidget(label("Pode controlar:", "dim"))
        for b in self.control_btns.values():
            strip.addWidget(b)
        strip.addStretch(1)
        strip.addWidget(self.timeline_btn)
        lay.addLayout(strip)
        # ask strip
        ask = QHBoxLayout()
        self.ask_agent = QComboBox()
        for a in ("claude", "codex"):
            self.ask_agent.addItem(AGENT[a]["mascot"], a)
        self.ask_edit = QLineEdit()
        self.ask_edit.setPlaceholderText("Pergunte sobre esta aba (ex.: resuma; o que muda na versão 1.20?; explique o trecho selecionado)")
        self.ask_edit.returnPressed.connect(lambda: self.ask(self.ask_agent.currentData(), self.ask_edit.text()))
        self.ask_btn = button("Perguntar", "send", "primary")
        self.ask_btn.clicked.connect(lambda: self.ask(self.ask_agent.currentData(), self.ask_edit.text()))
        ask.addWidget(self.ask_agent)
        ask.addWidget(self.ask_edit, 1)
        ask.addWidget(self.ask_btn)
        lay.addLayout(ask)
        # body: tabs | side panel
        self.split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(6)
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.setObjectName("browserTabs")
        self.tabs.setStyleSheet(
            f"#browserTabs QTabBar::tab {{ padding: 6px 12px; margin-right: 2px; border-radius: 8px 8px 0 0;"
            f" background: {C['surface']}; color: {C['muted']}; }}"
            f" #browserTabs QTabBar::tab:selected {{ color: {C['text']}; border-bottom: 2px solid {C['gold']}; }}"
            f" #browserTabs QTabBar::close-button {{ image: url({_icon_path('x')}); subcontrol-position: right; }}"
            f" #browserTabs QTabBar::close-button:hover {{ background: rgba(255,255,255,0.12); border-radius: 4px; }}"
            f" #browserTabs QTabBar QToolButton {{ background: {C['surface2']}; border: 1px solid {C['border']};"
            f" border-radius: 6px; }}")
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(lambda _i: self._sync())
        corner = QWidget()
        cl = QHBoxLayout(corner)
        cl.setContentsMargins(0, 0, 0, 0)
        self.new_btn = button("", "plus", "ghost", "Nova aba")
        self.new_btn.clicked.connect(lambda: self.new_tab(HOME))
        self.priv_btn = button("Anônima", "eye", "ghost", "Nova aba anônima: não grava histórico nem login")
        self.priv_btn.clicked.connect(lambda: self.new_tab(HOME, private=True))
        cl.addWidget(self.new_btn)
        cl.addWidget(self.priv_btn)
        self.tabs.setCornerWidget(corner, Qt.TopRightCorner)
        self.banner = QFrame()
        self.banner.setObjectName("controlBanner")
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(10, 6, 10, 6)
        self.banner_label = label("", None, wrap=True)
        self.take_btn = button("Assumir controle", "pause", "ghost", "Você volta a controlar; a IA espera")
        self.take_btn.clicked.connect(self.take_over)
        self.back_ctrl_btn = button("Devolver controle", "play", "ghost")
        self.back_ctrl_btn.clicked.connect(self.give_back)
        self.stop_ctrl_btn = button("Parar", "stop", "ghost", "Tira o controle de todas as IAs desta aba")
        self.stop_ctrl_btn.clicked.connect(lambda: self.stop_control(self.current_id()))
        bl.addWidget(self.banner_label, 1)
        for b in (self.take_btn, self.back_ctrl_btn, self.stop_ctrl_btn):
            bl.addWidget(b)
        self.banner.hide()
        ll.addWidget(self.banner)
        ll.addWidget(self.tabs, 1)
        self.answer = QTextBrowser()
        self.answer.setOpenExternalLinks(False)
        self.answer.anchorClicked.connect(lambda u: self.open_url(u.toString(), new_tab=True))
        self.answer.setMaximumHeight(230)
        self.answer.hide()
        ll.addWidget(self.answer)
        self.timeline = QListWidget()
        self.timeline.setMaximumHeight(140)
        self.timeline.hide()
        ll.addWidget(self.timeline)
        self.split.addWidget(left)
        from .page_work import scroll
        self.side = scroll(self._youtube_panel())   # scrolls on small windows instead of squeezing the text
        self.side.setMinimumWidth(310)
        self.side.setMaximumWidth(400)
        self.split.addWidget(self.side)
        self.split.setStretchFactor(0, 1)
        self.side.hide()
        self.fallback = Card()
        self.fallback.lay.addWidget(label("O navegador embutido não está disponível nesta cópia.", "h2"))
        self.fallback.lay.addWidget(label("Atualize o Studio pelo instalador; enquanto isso, links abrem no seu "
                                          "navegador padrão.", wrap=True))
        lay.addWidget(self.split, 1)
        lay.addWidget(self.fallback)
        self.fallback.setVisible(not webengine_available())
        self.split.setVisible(webengine_available())
        self._poll = QTimer(self)
        self._poll.setInterval(1500)
        self._poll.timeout.connect(self._check_answers)

    # ------------------------------------------------------------------ setup
    def refresh(self):
        if not self._started and webengine_available():
            self._started = True
            self.new_tab(HOME)
        self._ensure_bridge()
        self._sync()

    def _ensure_bridge(self):
        """Local bridge for the browser tools (127.0.0.1 only; created on the GUI thread)."""
        if self.bridge is not None or not webengine_available():
            return self.bridge
        from ..browser.bridge import make_bridge
        try:
            self.bridge = make_bridge(self._tool, self)
        except RuntimeError:
            return None
        bridge = self.bridge

        def issue(agent, task_id):
            if not self.shares.shared_tabs(agent) and not self.win.store.get_setting("browser.research", True):
                return None
            return {"port": bridge.port, "token": bridge.tokens.issue(agent, task_id)}
        self.win.engine.browser_bridge = issue
        self.win.engine.browser_release = bridge.tokens.revoke
        return bridge

    def _profile(self, private: bool, agents: bool = False):
        key = "agents" if agents else "private" if private else "personal"
        if key not in self._profiles:
            from PySide6.QtWebEngineCore import QWebEngineProfile
            if private or agents:
                prof = QWebEngineProfile(self)   # off-the-record: nothing written; assistants never see your logins
            else:
                base = self.win.engine.home / "navegador" / "pessoal"
                base.mkdir(parents=True, exist_ok=True)
                prof = QWebEngineProfile("kaguya-navegador", self)
                prof.setPersistentStoragePath(str(base / "dados"))
                prof.setCachePath(str(base / "cache"))
                prof.setPersistentCookiesPolicy(QWebEngineProfile.AllowPersistentCookies)
            prof.downloadRequested.connect(self._download)
            self._profiles[key] = prof
        return self._profiles[key]

    def new_tab(self, url: str = HOME, private: bool = False, select: bool = True, owner: str = ""):
        from PySide6.QtWebEngineCore import QWebEnginePage
        from PySide6.QtWebEngineWidgets import QWebEngineView
        studio = self
        tab_id = self._next_id
        self._next_id += 1

        class Page(QWebEnginePage):
            def createWindow(self, _type):   # target=_blank / window.open → new tab with the same privacy
                return studio.new_tab("about:blank", private=private, owner=owner).page()

        frame = QFrame()
        frame.setObjectName("browserFrame")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(2, 2, 2, 2)
        view = QWebEngineView(frame)
        view.setPage(Page(self._profile(private, agents=bool(owner)), view))
        view.tab_id, view.private, view.frame = tab_id, private or bool(owner), frame
        if owner:   # research tab of an assistant: isolated profile, shared with and controlled by it, visible to you
            self.shares.tab(tab_id).owner = owner
            self.shares.share(tab_id, owner)
            self.shares.allow_control(tab_id, owner)
        fl.addWidget(view)
        self.views[tab_id] = view
        if private or owner:
            self.private.add(tab_id)
        view.titleChanged.connect(lambda _t, v=view: self._title(v))
        view.urlChanged.connect(lambda _u, v=view: self._url_changed(v))
        view.loadFinished.connect(lambda ok, v=view: self._loaded(v, ok))
        idx = self.tabs.addTab(frame, "Anônima" if private else "Nova aba")
        if select:
            self.tabs.setCurrentIndex(idx)
        self._navigate(view, url)
        return view

    def close_tab(self, index: int):
        frame = self.tabs.widget(index)
        view = next((v for v in self.views.values() if v.frame is frame), None)
        if view is not None:
            self.shares.closed(view.tab_id)
            self.views.pop(view.tab_id, None)
            self.reports.pop(view.tab_id, None)
            self.private.discard(view.tab_id)
        self.tabs.removeTab(index)
        frame.deleteLater()
        if self.tabs.count() == 0:
            self.new_tab(HOME)

    def _cur(self):
        frame = self.tabs.currentWidget()
        return next((v for v in self.views.values() if v.frame is frame), None)

    def current_id(self) -> int | None:
        v = self._cur()
        return v.tab_id if v else None

    # ------------------------------------------------------------- navigation
    def _navigate(self, view, url: str):
        if url in (HOME, "about:home"):
            view.setHtml(home_html(self.data.favorites(), self.win.store.get_setting("browser.search", "duckduckgo")),
                         QUrl("about:blank"))
        else:
            view.load(QUrl(url))

    def open_url(self, text: str, new_tab: bool = False, private: bool | None = None):
        if not webengine_available():
            from .common import open_url
            open_url(to_url(text))
            return None
        url = to_url(text, self.win.store.get_setting("browser.search", "duckduckgo"))
        if not self._started:
            self._started = True
            return self.new_tab(url, private=bool(private))
        if new_tab or self._cur() is None:
            return self.new_tab(url, private=bool(private) if private is not None else False)
        self._navigate(self._cur(), url)
        return self._cur()

    def _title(self, view):
        i = self.tabs.indexOf(view.frame)
        if i < 0:
            return
        t = view.title() or view.url().toString() or "Nova aba"
        st = self.shares.tab(view.tab_id)
        prefix = (f"🔎 {NAMES[st.owner]}: " if st.owner else ("● " if st.shared else "") +
                  ("🕶 " if view.private else ""))
        self.tabs.setTabText(i, prefix + t[:26])
        self.tabs.setTabToolTip(i, t)
        if view.url().scheme() in ("http", "https") and not st.owner:
            self.data.visit(view.url().toString(), view.title(), view.private)

    def _url_changed(self, view):
        if view is self._cur():
            self._sync_address()
        tid = view.tab_id
        if yt.video_id(view.url().toString()):
            QTimer.singleShot(1800, self, lambda: self.scan_youtube(tid))   # YouTube changes videos without reloading
        else:
            self.reports.pop(tid, None)
            if view is self._cur():
                self.side.hide()

    def _loaded(self, view, ok: bool):
        self._title(view)
        if view is self._cur():
            self._sync()

    def _sync_address(self):
        v = self._cur()
        if v is None:
            return
        u = v.url().toString()
        self.address.setText("" if u in ("about:blank", "") else u)
        self.star.setChecked(bool(u) and self.data.is_favorite(u))
        self.star.setText("★" if self.star.isChecked() else "☆")

    def _sync(self):
        self._sync_address()
        tid = self.current_id()
        if tid is None:
            return
        t = self.shares.tab(tid)
        for a, b in self.share_btns.items():
            b.blockSignals(True)
            b.setChecked(a in t.readers)
            b.blockSignals(False)
        for a, b in self.control_btns.items():
            b.blockSignals(True)
            b.setChecked(a in t.controllers)
            b.setEnabled(a in t.readers and not t.owner)
            b.blockSignals(False)
        acting = t.controller if t.controller != "user" else ""
        if acting or t.held or t.owner:
            if t.held:
                text = "Você assumiu o controle desta aba. As IAs esperam até você devolver."
            elif t.owner:
                text = f"Aba de pesquisa da {NAMES[t.owner]} (isolada: sem seus logins)."
            else:
                text = f"{NAMES[acting]} está controlando esta aba. Você pode assumir ou parar a qualquer momento."
            self.banner_label.setText(text)
            color = AGENT[acting or t.owner]["color"] if (acting or t.owner) else C["gold"]
            self.banner.setStyleSheet(f"#controlBanner {{ background: {C['surface2']}; border: 1px solid {color};"
                                      f" border-radius: 8px; }}")
            self.take_btn.setVisible(bool(acting) and not t.held)
            self.back_ctrl_btn.setVisible(t.held)
            self.stop_ctrl_btn.setVisible(bool(t.controllers))
            self.banner.show()
        else:
            self.banner.hide()
        if t.readers:
            who = " e ".join(f"{NAMES[a]} (desde {t.since.get(a, '')})" for a in sorted(t.readers))
            self.share_label.setText(f"Esta aba está compartilhada com {who}.")
            self.share_label.setStyleSheet(f"color: {C['gold']};")
        else:
            self.share_label.setText("Aba pessoal: nenhuma IA vê esta aba." +
                                     (" Anônima: sem histórico nem login guardado." if tid in self.private else ""))
            self.share_label.setStyleSheet("")
        view = self.views.get(tid)
        if view is not None:
            color = AGENT[sorted(t.readers)[0]]["color"] if t.readers else "transparent"
            view.frame.setStyleSheet(f"#browserFrame {{ border: 2px solid {color}; border-radius: 6px; }}")
        self.timeline.clear()
        for when, who, what in t.timeline[-60:]:
            self.timeline.addItem(f"{when}  {NAMES.get(who, who)} {what}")
        self.timeline.scrollToBottom()
        rep = self.reports.get(tid)
        self.side.setVisible(rep is not None)
        if rep is not None:
            self._show_report(rep)

    def _share_changed(self, tab_id: int):
        view = self.views.get(tab_id)
        if view is not None:
            self._title(view)
        if tab_id == self.current_id():
            self._sync()

    # ---------------------------------------------------------------- sharing
    def set_share(self, agent: str, on: bool, tab_id: int | None = None):
        tab_id = tab_id if tab_id is not None else self.current_id()
        if tab_id is None:
            return
        self.shares.share(tab_id, agent, on)
        self._sync()

    def set_control(self, agent: str, on: bool, tab_id: int | None = None):
        tab_id = tab_id if tab_id is not None else self.current_id()
        if tab_id is None:
            return
        try:
            self.shares.allow_control(tab_id, agent, on)
        except AccessDenied as exc:
            self.win.toast(str(exc))
        self._ensure_bridge()
        self._sync()

    def take_over(self):
        tid = self.current_id()
        if tid is not None:
            self.shares.take_control(tid, "user")
            self._sync()

    def give_back(self):
        tid = self.current_id()
        if tid is not None:
            self.shares.give_back(tid)
            self._sync()

    def stop_control(self, tab_id: int | None = None):
        self.shares.stop_control(tab_id)
        self._sync()

    def stop_all(self):
        """'Pausar tudo': no assistant controls any tab, and every browser token dies."""
        self.shares.stop_control()
        if self.bridge is not None:
            self.bridge.tokens.revoke_all()
        self._sync()

    def _ensure_shared(self, tab_id: int, agent: str, confirm=None) -> bool:
        if self.shares.can_read(tab_id, agent):
            return True
        msg = (f"Esta aba ainda é pessoal. Compartilhar com {NAMES[agent]}?\n\n{NAMES[agent]} vai receber o título, o "
               "endereço e o texto visível desta aba (nunca senhas, cookies ou o que você digitou em formulários).")
        ok = confirm(msg) if confirm else QMessageBox.question(self, "Compartilhar aba", msg) == QMessageBox.Yes
        if ok:
            self.set_share(agent, True, tab_id)
        return ok

    # -------------------------------------------------------------------- ask
    def _project(self, need_real: bool = False) -> int | None:
        win = self.win
        if win.pid is not None and not win.store.is_pc(win.pid):
            return win.pid
        if need_real:
            return None
        folder = win.engine.home / "navegador" / "pesquisas"
        folder.mkdir(parents=True, exist_ok=True)
        for p in win.store.projects():
            if Path(p["directory"]) == folder and not p.get("removed"):
                return p["id"]
        return win.store.add_project("Pesquisas do navegador", folder)

    def _submit(self, agent: str, question: str, context: str, label_line: str, tab_id: int,
                attachments: list[str] | None = None, kind: str = "execute", need_project: bool = False,
                browser: bool = False) -> int | None:
        from ..messages import Intent
        pid = self._project(need_project)
        if pid is None:
            QMessageBox.information(self, "Projeto", "Para comparar com o seu projeto, selecione o projeto primeiro "
                                    "(barra do topo).")
            return None
        intent = Intent(kind=kind, target=agent, text=question.strip() + "\n\n" + label_line)
        tid = self.win.engine.submit(pid, intent, write=False, web=True, commands=False, context=context,
                                     attachments=attachments, browser=browser)
        if kind == "execute":
            self.pending[tid] = (tab_id, agent)
            self._poll.start()
            self.answer.show()
            self.answer.setHtml(f"<p style='color:{C['muted']}'>{NAMES[agent]} está lendo… a resposta aparece aqui e "
                                f"na Conversa (tarefa #{tid}).</p>")
        self.win.refresh_projects() if hasattr(self.win, "refresh_projects") else None
        return tid

    def ask(self, agent: str, question: str, confirm=None, on_sent=None):
        """Send the visible content of the current tab, as data, with the user's question."""
        question = (question or "").strip()
        view = self._cur()
        if view is None or not question:
            return False
        tid = view.tab_id
        if not self._ensure_shared(tid, agent, confirm):
            return False
        try:
            self.shares.check_read(tid, agent, "leu o texto visível da página (pergunta do usuário)")
        except AccessDenied as exc:
            self.win.toast(str(exc))
            return False

        def got(raw):
            snap = pagemod.parse_snapshot(raw or "{}")
            ctx, findings = pagemod.build_context(snap, NAMES[agent])
            if findings:
                self.shares.log(tid, "user", "ALERTA: a página tem texto tentando dar ordens a IAs ("
                                + "; ".join(f["why"] for f in findings) + ")")
            rep = self.reports.get(tid)
            if rep is not None:   # on a video page, the video report is attached too
                ctx += "\n\n" + rep.context()
            if agent in self.shares.tab(tid).controllers:
                ctx += (f"\n\nCONTROLE: você pode agir nesta aba (id {tid}) com as ferramentas kaguya_browser, "
                        "supervisionado pelo usuário.")
            task = self._submit(agent, question, ctx, pagemod.chat_label(snap), tid,
                                attachments=[p for _t, p in rep.frames] if rep else None,
                                browser=agent in self.shares.tab(tid).controllers)
            self.ask_edit.clear()
            if on_sent:
                on_sent(task, ctx, findings)
        view.page().runJavaScript(pagemod.EXTRACT_JS, 0, got)
        return True

    def _check_answers(self):
        for task_id in list(self.pending):
            try:
                t = self.win.store.get_task(task_id)
            except Exception:
                self.pending.pop(task_id, None)
                continue
            if t.get("status") not in DONE:
                continue
            tab, agent = self.pending.pop(task_id)
            text = t.get("result") or "(sem resposta)"
            self.last_answer[tab] = text
            self.answer.show()
            self.answer.setMarkdown(f"**{NAMES[agent]}** (tarefa #{task_id}, {t.get('status')}):\n\n{text[:12000]}")
        if not self.pending:
            self._poll.stop()

    # -------------------------------------------------------------- favourites
    def toggle_favorite(self):
        v = self._cur()
        if v is None:
            return
        u = v.url().toString()
        if not u or u == "about:blank":
            self.star.setChecked(False)
            return
        if self.data.is_favorite(u):
            self.data.remove_favorite(u)
        else:
            self.data.add_favorite(u, v.title())
        self._sync_address()

    def _fill_menu(self):
        self.menu.clear()
        favs = self.data.favorites()
        for f in favs[:40]:
            self.menu.addAction(f["title"][:60], lambda u=f["url"]: self.open_url(u))
        if not favs:
            self.menu.addAction("Nenhum favorito ainda").setEnabled(False)
        self.menu.addSeparator()
        self.menu.addAction("Histórico…", self.show_history)
        eng = self.menu.addMenu("Mecanismo de pesquisa")
        cur = self.win.store.get_setting("browser.search", "duckduckgo")
        for key, (name, _u) in SEARCH.items():
            a = eng.addAction(("✓ " if key == cur else "   ") + name)
            a.triggered.connect(lambda _=False, k=key: self.win.store.set_setting("browser.search", k))
        self.menu.addAction("Parar de compartilhar todas as abas", self.revoke_all)

    def revoke_all(self):
        self.shares.revoke_all()
        self._sync()
        self.win.toast("Nenhuma aba está compartilhada agora.")

    def show_history(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Histórico do Kaguya Browser")
        dlg.resize(680, 520)
        lay = QVBoxLayout(dlg)
        search = QLineEdit()
        search.setPlaceholderText("Buscar no histórico")
        lst = QListWidget()

        def fill():
            lst.clear()
            for h in self.data.history(search.text()):
                it = QListWidgetItem(f"{h['visited_at'].replace('T', ' ')}   {h['title'][:70]}\n{h['url'][:110]}")
                it.setData(Qt.UserRole, h["url"])
                lst.addItem(it)
        search.textChanged.connect(fill)
        lst.itemActivated.connect(lambda it: (self.open_url(it.data(Qt.UserRole), new_tab=True), dlg.accept()))
        clear = button("Apagar histórico", "trash", "ghost")
        clear.clicked.connect(lambda: (self.data.clear_history(), fill()))
        lay.addWidget(search)
        lay.addWidget(lst, 1)
        lay.addWidget(clear)
        fill()
        dlg.exec()

    # --------------------------------------------------------------- downloads
    def _download(self, req):
        name = req.downloadFileName() or "download"
        risky = name.lower().endswith(EXECUTABLES)
        if risky and QMessageBox.warning(
                self, "Baixar programa?", f"“{name}” é um programa/script. Só baixe se confia no site.\n\nBaixar mesmo "
                "assim?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            req.cancel()
            return
        start = str(Path.home() / "Downloads" / name)
        path, _ = QFileDialog.getSaveFileName(self, "Salvar download", start)
        if not path:
            req.cancel()
            return
        req.setDownloadDirectory(str(Path(path).parent))
        req.setDownloadFileName(Path(path).name)
        req.accept()
        self.win.toast(f"Baixando {Path(path).name}…")

    # ----------------------------------------------------------------- YouTube
    def _youtube_panel(self) -> QWidget:
        p = Card(accent=C["sakura"])
        p.setMinimumWidth(300)
        p.setMaximumWidth(380)
        p.lay.addWidget(label("YOUTUBE INTELLIGENCE", "section"))
        self.yt_title = label("", "h2", wrap=True)
        self.yt_levels = label("", "dim", wrap=True)
        self.yt_levels.setTextFormat(Qt.RichText)
        p.lay.addWidget(self.yt_title)
        p.lay.addWidget(self.yt_levels)
        self.yt_chapters = QListWidget()
        self.yt_chapters.setMaximumHeight(170)
        self.yt_chapters.itemActivated.connect(lambda it: self.seek(it.data(Qt.UserRole)))
        self.yt_chapters.itemClicked.connect(lambda it: self.seek(it.data(Qt.UserRole)))
        p.lay.addWidget(self.yt_chapters)
        self.yt_caps_btn = button("Ler legendas / transcrição", "file", None,
                                  "Usa as legendas que o próprio YouTube oferece para este vídeo (nível B)")
        self.yt_caps_btn.clicked.connect(lambda: self.fetch_captions())
        self.yt_frame_btn = button("Capturar quadro (nível C)", "eye", "ghost",
                                   "Guarda uma imagem do que está na tela agora, com o tempo do vídeo")
        self.yt_frame_btn.clicked.connect(lambda: self.capture_frame())
        p.lay.addWidget(self.yt_caps_btn)
        p.lay.addWidget(self.yt_frame_btn)
        p.lay.addWidget(label("Enviar para a IA escolhida na barra de pergunta:", "dim", wrap=True))
        self.yt_actions = {}
        for key, text, ic in (("video", "Analisar o vídeo", "sparkle"), ("estudar", "Estudar este trecho", "book"),
                              ("comparar", "Comparar com meu projeto", "layers")):
            b = button(text, ic)
            b.clicked.connect(lambda _=False, k=key: self.youtube_action(k))
            self.yt_actions[key] = b
            p.lay.addWidget(b)
        row = QHBoxLayout()
        self.yt_note = button("Criar nota", "brain", "ghost", "Rascunho no Segundo Cérebro (você revisa antes)")
        self.yt_note.clicked.connect(lambda: self.youtube_note())
        self.yt_later = button("Para depois", "clock", "ghost", "Guarda o pedido na fila 'para depois'")
        self.yt_later.clicked.connect(lambda: self.youtube_action("video", later=True))
        row.addWidget(self.yt_note)
        row.addWidget(self.yt_later)
        p.lay.addLayout(row)
        p.lay.addStretch(1)
        return p

    def scan_youtube(self, tab_id: int, done=None):
        view = self.views.get(tab_id)
        if view is None or not yt.video_id(view.url().toString()):
            return

        def got(raw):
            import json
            try:
                info = json.loads(raw or "{}")
            except ValueError:
                info = {}
            url = view.url().toString()
            old = self.reports.get(tab_id)
            rep = yt.Report.from_page(url, info)
            if old is not None and old.video_id == rep.video_id:   # keep captions/frames already collected
                rep.frames = old.frames
                if old.segments and not rep.segments:
                    rep.segments, rep.text_source = old.segments, old.text_source
            if not rep.meta:   # page did not expose the data: official oEmbed gives title + channel
                try:
                    rep.meta, rep.meta_source = yt.oembed(url), "oEmbed oficial (só título e canal)"
                except Exception:
                    pass
            rep.tracks = info.get("tracks") or []
            self.reports[tab_id] = rep
            if tab_id == self.current_id():
                self._sync()
            if done:
                done(rep)
        view.page().runJavaScript(yt.PAGE_JS, 0, got)

    def _show_report(self, rep: yt.Report):
        self.yt_title.setText(rep.meta.get("title") or "Vídeo do YouTube")
        lv = rep.levels()
        self.yt_levels.setText("<br>".join(f"<b>{k}</b>: {v}" for k, v in lv.items()))
        self.yt_chapters.clear()
        for t, x in rep.meta.get("chapters") or []:
            it = QListWidgetItem(f"{yt.fmt_ts(t)}  {x}")
            it.setData(Qt.UserRole, t)
            self.yt_chapters.addItem(it)
        self.yt_chapters.setVisible(self.yt_chapters.count() > 0)
        self.yt_caps_btn.setEnabled(bool(rep.tracks) or not rep.segments)
        self.yt_actions["estudar"].setEnabled(rep.time is not None and bool(rep.segments))

    def seek(self, seconds):
        v = self._cur()
        if v is not None and seconds is not None:
            v.page().runJavaScript(f"(function(){{var v=document.querySelector('video');if(v){{v.currentTime={int(seconds)};}}"
                                   "return !!v;})()")

    def fetch_captions(self, done=None, timeout_s: float = 12):
        tab_id = self.current_id()
        rep = self.reports.get(tab_id)
        view = self.views.get(tab_id)
        if rep is None or view is None:
            return
        track = yt.pick_track(rep.tracks)
        if track is None:
            rep.text_problem = ("este vídeo não tem legendas disponíveis; se a página oferecer “Mostrar transcrição”, "
                                "abra o painel e clique de novo")
            self.scan_youtube(tab_id, done)
            return
        self.yt_caps_btn.setEnabled(False)
        self.yt_caps_btn.setText("Lendo legendas…")
        state = {"left": int(timeout_s / 0.4)}

        def finish():
            self.yt_caps_btn.setText("Ler legendas / transcrição")
            self.yt_caps_btn.setEnabled(True)
            self._sync()
            if done:
                done(rep)

        def poll():
            def got(raw):
                import json
                st = json.loads(raw or "{}")
                if st.get("state") == "done":
                    rep.set_captions(st.get("body") or "", track)
                    finish()
                elif st.get("state") == "error" or state["left"] <= 0:
                    rep.text_problem = "não foi possível ler as legendas agora (" + (st.get("error") or "tempo esgotado") + ")"
                    finish()
                else:
                    state["left"] -= 1
                    QTimer.singleShot(400, self, poll)
            view.page().runJavaScript(yt.CAPTION_POLL_JS, 0, got)
        view.page().runJavaScript(yt.caption_fetch_js(track["url"]), 0, lambda _r: QTimer.singleShot(300, self, poll))

    def capture_frame(self, confirm=None, done=None):
        tab_id = self.current_id()
        rep = self.reports.get(tab_id)
        view = self.views.get(tab_id)
        if rep is None or view is None:
            return None
        if not self.win.store.get_setting("browser.frames_ok", False):
            msg = ("Capturar uma imagem do que está na tela agora para a IA analisar?\n\nUse só com vídeos que você pode "
                   "analisar (seus, abertos/educacionais ou com permissão). A imagem fica no seu PC.")
            ok = confirm(msg) if confirm else QMessageBox.question(self, "Capturar quadro", msg) == QMessageBox.Yes
            if not ok:
                return None
            self.win.store.set_setting("browser.frames_ok", True)

        def got(raw):
            import json
            info = json.loads(raw or "{}")
            t = info.get("time") or 0
            r = info.get("video_rect")
            zoom = view.zoomFactor()
            area = QRect(int(r[0] * zoom), int(r[1] * zoom), int(r[2] * zoom), int(r[3] * zoom)) if r else view.rect()
            img = view.grab(area.intersected(view.rect()))
            folder = self.win.engine.home / "navegador" / "quadros"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{rep.video_id}_{int(t)}s.png"
            img.save(str(path))
            rep.frames.append((float(t), str(path)))
            self.shares.log(tab_id, "user", f"capturou o quadro em {yt.fmt_ts(t)}")
            self._sync()
            if done:
                done(path)
        view.page().runJavaScript(yt.PAGE_JS, 0, got)
        return True

    def youtube_action(self, action: str, later: bool = False, confirm=None):
        tab_id = self.current_id()
        rep = self.reports.get(tab_id)
        if rep is None:
            return None
        agent = self.ask_agent.currentData()
        if not self._ensure_shared(tab_id, agent, confirm):
            return None
        self.shares.check_read(tab_id, agent, f"recebeu o relatório do vídeo ({action})")
        project = ""
        if action == "comparar":
            pid = self._project(need_real=True)
            project = self.win.store.project(pid)["name"] if pid else ""
        question, ctx = yt.prompt_for(action, rep, project)
        line = f"🎬 Vídeo: {rep.meta.get('title') or rep.url} — {rep.url}"
        return self._submit(agent, question, ctx, line, tab_id, attachments=[p for _t, p in rep.frames],
                            kind="later" if later else "execute", need_project=action == "comparar")

    def youtube_note(self):
        tab_id = self.current_id()
        rep = self.reports.get(tab_id)
        if rep is None:
            return None
        pid = self._project()
        ob = self.win.engine.outbox(pid) if pid is not None else None
        if ob is None:
            self.win.toast("Conecte o Segundo Cérebro (Obsidian) para criar notas.")
            return None
        summary = self.last_answer.get(tab_id, "")
        note = ob.stage("pesquisa", rep.meta.get("title") or rep.url, yt.note_markdown(rep, summary),
                        source=rep.url, project=self.win.store.project(pid)["name"])
        self.win.toast(f"Nota em revisão no Segundo Cérebro: {note.name}")
        return note

    # ------------------------------------------------------------ browser tools (called through the bridge)
    def confirm_async(self, message: str, done):
        """Ask the user without blocking the Studio (the assistant's tool call waits for the answer)."""
        if self.confirm_hook is not None:
            done(bool(self.confirm_hook(message)))
            return
        box = QMessageBox(QMessageBox.Question, "A IA quer fazer algo importante", message,
                          QMessageBox.Yes | QMessageBox.No, self.window())
        box.setDefaultButton(QMessageBox.No)
        box.setWindowModality(Qt.NonModal)
        box.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self._dialogs.append(box)

        def finished(code):
            self._dialogs.remove(box) if box in self._dialogs else None
            done(code == QMessageBox.Yes)
        box.finished.connect(finished)
        box.open()
        self.win.toast("Uma IA está pedindo confirmação no navegador.")

    def _tool(self, agent: str, tool: str, args: dict, reply):
        who = NAMES.get(agent, agent)

        def view_of(tab):
            try:
                tab = int(tab)
            except (TypeError, ValueError):
                raise AccessDenied("Informe o número da aba (veja browser_tabs).")
            v = self.views.get(tab)
            if v is None:
                raise AccessDenied(f"A aba {tab} não existe mais.")
            return tab, v

        def after_load(view, msg):
            QTimer.singleShot(1200, self, lambda: reply(True, f"{msg}\nAgora: {view.title()} — {view.url().toString()}"))

        try:
            if tool == "browser_tabs":
                rows = []
                for tab_id in self.shares.shared_tabs(agent):
                    v = self.views.get(tab_id)
                    if v is None:
                        continue
                    t = self.shares.tab(tab_id)
                    ctl = "pode controlar" if agent in t.controllers and not t.held else "só leitura"
                    rows.append(f"aba {tab_id}: {v.title()[:80]} — {v.url().toString()} ({ctl}"
                                + (", sua aba de pesquisa" if t.owner == agent else "") + ")")
                self.shares.log(self.current_id() or 0, agent, "listou as abas compartilhadas")
                reply(True, "\n".join(rows) if rows else "Nenhuma aba foi compartilhada com você. Use browser_research "
                      "para abrir sua própria aba de pesquisa, se precisar.")
                return
            if tool == "browser_research":
                url = to_url(str(args.get("url", "")), self.win.store.get_setting("browser.search", "duckduckgo"))
                if pagemod.EXECUTABLE_LINK.search(url):
                    reply(False, "Abrir downloads de programas não é permitido numa aba de pesquisa.")
                    return
                v = self.new_tab(url, select=False, owner=agent)
                self.shares.log(v.tab_id, agent, f"abriu a aba de pesquisa {url}")
                self.win.toast(f"{who} abriu uma aba de pesquisa: {url[:80]}")
                after_load(v, f"Aba de pesquisa {v.tab_id} aberta.")
                return
            tab, v = view_of(args.get("tab"))
            if tool == "browser_read":
                self.shares.check_read(tab, agent, "leu o texto visível da página (ferramenta)")

                def got(raw):
                    ctx, findings = pagemod.build_context(pagemod.parse_snapshot(raw or "{}"), who, limit=14000)
                    if findings:
                        self.shares.log(tab, "user", "ALERTA: texto tentando dar ordens a IAs nesta página")
                    reply(True, ctx)
                v.page().runJavaScript(pagemod.EXTRACT_JS, 0, got)
                return
            if tool == "browser_elements":
                self.shares.check_read(tab, agent, "listou links/botões/campos")
                v.page().runJavaScript(pagemod.js(pagemod.ELEMENTS_JS, str(args.get("filter") or "")), 0,
                                       lambda raw: reply(True, pagemod.format_elements(json.loads(raw or "[]"))))
                return
            if tool in ("browser_click", "browser_type"):
                el = int(args.get("element", 0))
                if agent not in self.shares.tab(tab).controllers:   # permission first, before touching the page
                    self.shares.log(tab, agent, "tentou agir na aba sem permissão (negado)")
                    raise AccessDenied(f"{who} não pode controlar esta aba (só leitura).")

                def described(raw):
                    d = json.loads(raw or "{}")
                    if not d.get("exists"):
                        reply(False, f"Elemento [{el}] não encontrado; chame browser_elements de novo.")
                        return
                    label_ = d.get("label") or d.get("href") or d.get("tag", "")
                    if tool == "browser_type":
                        if d.get("secret"):
                            self.shares.log(tab, agent, f"tentou digitar num campo de senha/cartão [{el}] (bloqueado)")
                            reply(False, "Proibido: este campo é de senha, cartão ou código. Peça ao usuário para "
                                  "preencher ele mesmo.")
                            return
                        text = str(args.get("text", ""))
                        submit = bool(args.get("submit"))
                        action = f"digitar “{text[:60]}” em [{el}] {label_[:60]}" + (" e enviar" if submit else "")
                    else:
                        submit = bool(d.get("submit"))
                        action = f"clicar em [{el}] {label_[:80]}"
                    try:
                        self.shares.check_control(tab, agent, action)
                    except AccessDenied as exc:
                        reply(False, str(exc))
                        return
                    risky = (submit or pagemod.is_high_impact(label_) or d.get("download")
                             or bool(pagemod.EXECUTABLE_LINK.search(d.get("href") or "")))

                    def go(ok: bool):
                        if not ok:
                            self.shares.log(tab, "user", f"recusou: {action}")
                            reply(False, "O usuário NÃO autorizou esta ação. Não tente de novo; pergunte o que ele prefere.")
                            return
                        if risky:
                            self.shares.log(tab, "user", f"autorizou: {action}")
                        code = (pagemod.js(pagemod.TYPE_JS, el, str(args.get("text", "")), submit) if tool == "browser_type"
                                else pagemod.js(pagemod.CLICK_JS, el))

                        def done(r):
                            if r == "secret":
                                reply(False, "Proibido: campo de senha/cartão.")
                            elif r != "ok":
                                reply(False, f"Elemento [{el}] sumiu da página; chame browser_elements de novo.")
                            else:
                                after_load(v, f"Feito: {action}.")
                        v.page().runJavaScript(code, 0, done)
                    if risky:
                        self.confirm_async(f"{who} quer {action}\n\nna página {v.title()[:80]}\n{v.url().toString()[:120]}"
                                           "\n\nPermitir?", go)
                    else:
                        go(True)
                v.page().runJavaScript(pagemod.js(pagemod.DESCRIBE_JS, el), 0, described)
                return
            if tool == "browser_scroll":
                d = str(args.get("direction", "down"))
                self.shares.check_control(tab, agent, f"rolou a página ({d})")
                v.page().runJavaScript(pagemod.js(pagemod.SCROLL_JS, d), 0, lambda r: reply(True, f"Rolado ({d}); posição {r}."))
                return
            if tool == "browser_navigate":
                url = to_url(str(args.get("url", "")), self.win.store.get_setting("browser.search", "duckduckgo"))
                self.shares.check_control(tab, agent, f"abriu {url}")
                if pagemod.EXECUTABLE_LINK.search(url):
                    def nav(ok):
                        if ok:
                            v.load(QUrl(url))
                            after_load(v, f"Abrindo {url}.")
                        else:
                            reply(False, "O usuário NÃO autorizou abrir esse download.")
                    self.confirm_async(f"{who} quer abrir um download:\n{url}\n\nPermitir?", nav)
                    return
                v.load(QUrl(url))
                after_load(v, f"Abrindo {url}.")
                return
            if tool == "browser_back":
                self.shares.check_control(tab, agent, "voltou uma página")
                v.back()
                after_load(v, "Voltou.")
                return
            reply(False, f"Ferramenta desconhecida: {tool}")
        except AccessDenied as exc:
            reply(False, str(exc))
        finally:
            QTimer.singleShot(0, self, self._sync)
