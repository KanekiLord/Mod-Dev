"""The official ChatGPT and Claude chats inside the Studio.

They are the real websites (chatgpt.com / claude.ai) in an embedded browser: the user signs in there
with their own account, exactly as in a normal browser. The Studio never reads the session, cookies
or the conversation, never types into the page and never calls private endpoints — it only offers a
"copy project context" button so the user can paste it. Cookies live in the Studio's own data folder.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from .theme import C
from .widgets import Card, button, label

SITES = {"chatgpt": ("ChatGPT", "https://chatgpt.com/", "codex"),
         "claude": ("Claude", "https://claude.ai/new", "claude")}

LIMITS_NOTE = (
    "Sobre os limites (conferido em 25/11/2026 nas páginas oficiais): no <b>Claude</b>, o chat do claude.ai e o "
    "Claude Code usam o <b>mesmo</b> limite da assinatura — usar o chat também gasta o limite do Claude Code. "
    "No <b>ChatGPT</b>, a OpenAI informa que o Codex e o \"ChatGPT Work\" dividem o mesmo limite do plano; o chat "
    "comum tem limites próprios por modelo. Nenhum dos dois é ilimitado: veja o uso em Uso e limites e nas páginas "
    "oficiais.")


def webengine_available() -> bool:
    try:
        import PySide6.QtWebEngineWidgets  # noqa: F401
        return True
    except Exception:
        return False


class WebChatsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.views: dict[str, object] = {}
        self.profile = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.site_btns = {}
        for key, (name, _url, agent) in SITES.items():
            b = button(name, agent, tip=f"Abrir o {name} oficial aqui dentro (com o seu login)", checkable=True)
            b.clicked.connect(lambda _=False, k=key: self.open_site(k))
            self.site_btns[key] = b
            bar.addWidget(b)
        bar.addStretch(1)
        self.ctx_btn = button("Copiar contexto do projeto", "file", "ghost",
                              "Copia um resumo do projeto e da última tarefa para você colar no chat (Ctrl+V)")
        self.ctx_btn.clicked.connect(self.copy_context)
        self.reload_btn = button("", "refresh", "ghost", "Recarregar")
        self.reload_btn.clicked.connect(self.reload)
        self.ext_btn = button("Abrir no navegador", "external", "ghost",
                              "Abre o site no seu navegador (útil para entrar com Google, que pode bloquear navegadores embutidos)")
        self.ext_btn.clicked.connect(self.open_external)
        for b in (self.ctx_btn, self.reload_btn, self.ext_btn):
            bar.addWidget(b)
        lay.addLayout(bar)
        self.stack = QStackedWidget()
        self.start = self._start_card()
        self.stack.addWidget(self.start)
        lay.addWidget(self.stack, 1)
        self.current: str | None = None

    def _start_card(self) -> QWidget:
        c = Card(accent=C["violet"])
        c.lay.addWidget(label("CHATGPT E CLAUDE (CHATS NORMAIS)", "section"))
        c.lay.addWidget(label("Converse com o ChatGPT e o Claude dos sites oficiais sem sair do Studio. Você entra com a "
                              "sua conta na própria página; o Studio não lê nem guarda suas conversas.", wrap=True))
        note = label(LIMITS_NOTE, "muted", wrap=True)
        note.setTextFormat(Qt.RichText)
        c.lay.addWidget(note)
        if not webengine_available():
            c.lay.addWidget(label("O navegador embutido não está disponível nesta cópia: os botões abrem o seu navegador.",
                                  wrap=True))
        row = QHBoxLayout()
        for key, (name, _url, agent) in SITES.items():
            b = button(f"Abrir {name}", agent, "primary" if key == "chatgpt" else None)
            b.clicked.connect(lambda _=False, k=key: self.open_site(k))
            row.addWidget(b)
        row.addStretch(1)
        c.lay.addLayout(row)
        c.lay.addStretch(1)
        return c

    # -------------------------------------------------------------- browser
    def _profile(self):
        if self.profile is None:
            from PySide6.QtWebEngineCore import QWebEngineProfile
            base = self.win.engine.home / "navegador"
            base.mkdir(parents=True, exist_ok=True)
            self.profile = QWebEngineProfile("kaguya-chats", self)
            self.profile.setPersistentStoragePath(str(base / "dados"))
            self.profile.setCachePath(str(base / "cache"))
            self.profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        return self.profile

    def _view(self, key: str):
        if key in self.views:
            return self.views[key]
        from PySide6.QtWebEngineCore import QWebEnginePage
        from PySide6.QtWebEngineWidgets import QWebEngineView

        studio = self

        class Page(QWebEnginePage):
            def createWindow(self, _type):
                # login pop-ups (e.g. "Continuar com…") open in a small window with the same profile
                popup = QWebEngineView()
                popup.setAttribute(Qt.WA_DeleteOnClose)
                popup.setPage(Page(studio._profile(), popup))
                popup.resize(520, 680)
                popup.setWindowTitle("Entrar")
                popup.page().windowCloseRequested.connect(popup.close)
                popup.show()
                return popup.page()

        view = QWebEngineView()
        view.setPage(Page(self._profile(), view))
        view.load(QUrl(SITES[key][1]))
        self.stack.addWidget(view)
        self.views[key] = view
        return view

    def open_site(self, key: str):
        self.current = key
        for k, b in self.site_btns.items():
            b.setChecked(k == key)
        if not webengine_available():
            self.open_external()
            return
        self.stack.setCurrentWidget(self._view(key))

    def reload(self):
        if self.current in self.views:
            self.views[self.current].reload()

    def open_external(self):
        QDesktopServices.openUrl(QUrl(SITES[self.current or "chatgpt"][1]))

    def context_text(self) -> str:
        win = self.win
        if win.pid is None:
            return "Estou desenvolvendo um mod de Minecraft no Kaguya Studio."
        p = win.store.project(win.pid)
        lines = [f"Contexto: projeto \"{p['name']}\" (mod de Minecraft) no Kaguya Studio."]
        tasks = [t for t in win.store.tasks(win.pid, 5) if t["kind"] == "execute"]
        if tasks:
            t = tasks[0]
            from .wake_ui import first_sentences
            lines.append(f"Última tarefa: {t['title'][:300]} — situação: {t['status']}.")
            if t.get("result"):
                lines.append("Resumo do resultado: " + first_sentences(t["result"], 500))
        lines.append("Minha pergunta: ")
        return "\n".join(lines)

    def copy_context(self):
        QGuiApplication.clipboard().setText(self.context_text())
        self.win.toast("Contexto copiado. Cole no chat com Ctrl+V e complete a pergunta.")
