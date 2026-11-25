"""Kaguya Browser: tabs, favourites, history, private tabs, per-tab sharing with Kaguya/Miwa and YouTube Intelligence.

Privacy model (spec 03): a tab is personal by default — no assistant sees it. Sharing is per tab and per assistant,
always visible (coloured frame, ● in the tab title, a banner and a timeline). Only what is visible on the page goes
to the assistant, as data, when the user asks something. Cookies, logins, storage and form values never leave the
browser. Personal tabs keep logins in the Studio's data folder; private tabs keep nothing.
"""
from __future__ import annotations

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
            b = button(f"Compartilhar com {AGENT[a]['mascot']}", a, "chip", checkable=True,
                       tip=f"{AGENT[a]['mascot']} passa a poder ler ESTA aba quando você perguntar algo")
            b.clicked.connect(lambda on, a=a: self.set_share(a, on))
            self.share_btns[a] = b
        self.timeline_btn = button("Linha do tempo", "clock", "ghost", "Quem acessou esta aba e quando", checkable=True)
        self.timeline_btn.clicked.connect(lambda on: self.timeline.setVisible(on))
        strip.addWidget(self.share_label, 1)
        for b in (*self.share_btns.values(), self.timeline_btn):
            strip.addWidget(b)
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
            f" #browserTabs QTabBar::close-button:hover {{ background: rgba(255,255,255,0.12); border-radius: 4px; }}")
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
        self.side = self._youtube_panel()
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
        self._sync()

    def _profile(self, private: bool):
        key = "private" if private else "personal"
        if key not in self._profiles:
            from PySide6.QtWebEngineCore import QWebEngineProfile
            if private:
                prof = QWebEngineProfile(self)   # off-the-record: nothing written to disk
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

    def new_tab(self, url: str = HOME, private: bool = False, select: bool = True):
        from PySide6.QtWebEngineCore import QWebEnginePage
        from PySide6.QtWebEngineWidgets import QWebEngineView
        studio = self
        tab_id = self._next_id
        self._next_id += 1

        class Page(QWebEnginePage):
            def createWindow(self, _type):   # target=_blank / window.open → new tab with the same privacy
                return studio.new_tab("about:blank", private=private).page()

        frame = QFrame()
        frame.setObjectName("browserFrame")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(2, 2, 2, 2)
        view = QWebEngineView(frame)
        view.setPage(Page(self._profile(private), view))
        view.tab_id, view.private, view.frame = tab_id, private, frame
        fl.addWidget(view)
        self.views[tab_id] = view
        if private:
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
        shared = self.shares.tab(view.tab_id).shared
        self.tabs.setTabText(i, ("● " if shared else "") + ("🕶 " if view.private else "") + t[:26])
        self.tabs.setTabToolTip(i, t)
        if view.url().scheme() in ("http", "https"):
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
                attachments: list[str] | None = None, kind: str = "execute", need_project: bool = False) -> int | None:
        from ..messages import Intent
        pid = self._project(need_project)
        if pid is None:
            QMessageBox.information(self, "Projeto", "Para comparar com o seu projeto, selecione o projeto primeiro "
                                    "(barra do topo).")
            return None
        intent = Intent(kind=kind, target=agent, text=question.strip() + "\n\n" + label_line)
        tid = self.win.engine.submit(pid, intent, write=False, web=True, commands=False, context=context,
                                     attachments=attachments)
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
            task = self._submit(agent, question, ctx, pagemod.chat_label(snap), tid,
                                attachments=[p for _t, p in rep.frames] if rep else None)
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
