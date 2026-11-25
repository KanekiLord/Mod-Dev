"""Usage & limits, Diagnostics and Settings pages."""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGridLayout, QHBoxLayout, QLineEdit, QMessageBox,
                               QSpinBox, QVBoxLayout, QWidget)

from ..appdirs import legacy_v3_database
from ..cli import discovery
from ..cli.discovery import STATE_LABELS
from ..quality import run_checks
from ..usage import INTERACTIVE_HINT, OFFICIAL_PAGES, claude_snapshot, local_summary, read_codex_limits
from ..voice import stt
from ..voice.tts import Speaker
from . import theme
from .common import open_path, open_url, pick_file, run_bg
from .dialogs import ProjectDialog, TextDialog
from .page_work import page_title, scroll, table, item
from .theme import AGENT, C
from .widgets import Card, Meter, Pill, Toggle, button, icon_label, label

STATE_COLORS = {"pronto": C["success"], "autenticado": C["success"], "encontrado": C["warning"],
                "nao_autenticado": C["warning"], "sem_permissao": C["danger"], "nao_instalado": C["danger"],
                "erro": C["danger"], "limite": C["danger"], "em_execucao": C["violet"]}


def agent_head(agent: str, extra: QWidget | None = None) -> QHBoxLayout:
    a = AGENT[agent]
    row = QHBoxLayout()
    row.addWidget(icon_label(a["icon"], a["color"], 24))
    t = label(f"{a['name']}", "h2")
    t.setStyleSheet(f"color: {a['color']};")
    row.addWidget(t)
    row.addWidget(label("CLI oficial • assinatura" if agent == "codex" else "Claude Code • assinatura", "dim"))
    row.addStretch(1)
    if extra:
        row.addWidget(extra)
    return row


class UsageCard(Card):
    def __init__(self, win, agent: str):
        super().__init__(accent=AGENT[agent]["color"], pattern=True)
        self.win, self.agent = win, agent
        self.state = Pill("…", C["muted"])
        self.lay.addLayout(agent_head(agent, self.state))
        self.lay.addWidget(label("COTA DA ASSINATURA (FONTE OFICIAL)", "section", wrap=True))
        self.windows = QVBoxLayout()
        self.windows.setSpacing(10)
        self.lay.addLayout(self.windows)
        self.source = label("", "dim", wrap=True)
        self.lay.addWidget(self.source)
        row = QHBoxLayout()
        self.refresh_btn = button("Atualizar agora", "refresh")
        self.refresh_btn.clicked.connect(self.fetch)
        if agent == "claude":
            self.refresh_btn.setToolTip("O Claude Code só informa a utilização durante uma tarefa real; não há consulta "
                                        "sem custo. Os dados são atualizados automaticamente a cada execução.")
        term = button(INTERACTIVE_HINT[agent].split(" ")[0], "terminal", "ghost", "Abre a CLI interativa no terminal: "
                      + INTERACTIVE_HINT[agent])
        term.clicked.connect(self.open_terminal)
        row.addWidget(self.refresh_btn)
        row.addWidget(term)
        for title, url in OFFICIAL_PAGES[agent][:1]:
            b = button("Página oficial", "external", "ghost", title)
            b.clicked.connect(lambda _=False, u=url: open_url(u))
            row.addWidget(b)
        row.addStretch(1)
        self.lay.addLayout(row)
        self.lay.addSpacing(4)
        self.lay.addWidget(label("USO LOCAL MEDIDO (NÃO É SALDO DA CONTA)", "section", wrap=True))
        self.local = label("", "muted", wrap=True)
        self.lay.addWidget(self.local)

    def show_snapshot(self, snap):
        while self.windows.count():
            it = self.windows.takeAt(0)
            if it.layout():
                while it.layout().count():
                    w = it.layout().takeAt(0).widget()
                    if w:
                        w.deleteLater()
            elif it.widget():
                it.widget().deleteLater()
        if snap.available and snap.windows:
            for w in snap.windows:
                grid = QGridLayout()
                grid.setHorizontalSpacing(10)
                name = label(w.name)
                name.setStyleSheet("font-weight: 600;")
                grid.addWidget(name, 0, 0)
                pct = label(f"{w.remaining_percent:.0f}% restante")
                pct.setStyleSheet(f"color: {AGENT[self.agent]['color']}; font-weight: 700;")
                grid.addWidget(pct, 0, 1, Qt.AlignRight)
                m = Meter(AGENT[self.agent]["color"])
                m.set_value(w.used_percent)
                grid.addWidget(m, 1, 0, 1, 2)
                grid.addWidget(label(f"{w.used_percent:.0f}% usado • {w.reset_text()}", "dim"), 2, 0, 1, 2)
                self.windows.addLayout(grid)
            blocked = "  •  LIMITE ATINGIDO" if snap.blocked else ""
            self.source.setText(f"Fonte: {snap.source} • {snap.age_text()}" + (f" • plano {snap.plan}" if snap.plan else "") + blocked)
        else:
            row = QHBoxLayout()
            m = Meter()
            m.set_value(None)
            row.addWidget(icon_label("info", C["warning"], 16))
            row.addWidget(label("Quota não disponível automaticamente", ""), 1)
            self.windows.addLayout(row)
            self.windows.addWidget(m)
            self.source.setText(snap.message + f"  Consulte {INTERACTIVE_HINT[self.agent]} ou a página oficial.")

    def refresh_local(self):
        five = local_summary(self.win.store, self.agent, 5)
        week = local_summary(self.win.store, self.agent, 24 * 7)

        def fmt(d):
            return (f"{d['runs']} execução(ões) • {d['input_tokens']:,} tokens de entrada • {d['output_tokens']:,} de saída"
                    f" • {d['cached_tokens']:,} em cache").replace(",", ".")
        self.local.setText(f"Últimas 5 h: {fmt(five)}\nÚltimos 7 dias: {fmt(week)}\n"
                           "Medido a partir da saída oficial das execuções feitas pelo Studio; outros usos da conta "
                           "(app, web, outras sessões) não aparecem aqui.")
        diag = self.win.engine.diagnoses.get(self.agent)
        if diag:
            self.state.set(diag.label, STATE_COLORS.get(diag.state, C["muted"]))
        else:
            self.state.set("não verificado", C["muted"])

    def load_cached(self):
        from ..usage import UsageSnapshot, Window
        if self.agent == "claude":
            snap = claude_snapshot(self.win.store.latest_usage("claude"))
            if not snap.available:
                snap.message = ("Ainda não há dado oficial. Clique em 'Atualizar agora' (envia 1 mensagem mínima) ou "
                                "rode uma tarefa: o Claude Code informa a utilização a cada resposta.")
        else:
            stored = self.win.store.latest_usage("codex")
            if stored and stored["payload"].get("available"):
                p = stored["payload"]
                snap = UsageSnapshot("codex", True, p.get("source", ""), [Window(**w) for w in p.get("windows", [])],
                                     p.get("plan", ""), p.get("captured_at"), p.get("message", ""), p.get("blocked", False))
            else:
                snap = UsageSnapshot("codex", False, "", message="Clique em 'Atualizar agora' para consultar o Codex.")
        self.show_snapshot(snap)
        last = self.win.store.get_setting(f"usage.{self.agent}.last_attempt")
        if last:
            state = "ok" if last.get("ok") else "falhou: " + last.get("message", "")[:220]
            self.source.setText((self.source.text() + "\n" if self.source.text() else "") +
                                f"Última tentativa {last.get('when', '')}: {state}")
        self.refresh_local()

    def fetch(self):
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("Atualizando…")

        def done(_=None):
            self.refresh_btn.setEnabled(True)
            self.refresh_btn.setText("Atualizar agora")
            self.load_cached()
        if self.agent == "claude":
            self.win.refresh_claude_limits(done)
        else:
            self.win.refresh_codex_limits(done, notify=True)

    def open_terminal(self):
        diag = self.win.engine.diagnoses.get(self.agent)
        exe = diag.executable if diag and diag.executable else None
        if not exe:
            self.win.toast("Rode o diagnóstico primeiro.")
            return
        cwd = self.win.store.project(self.win.pid)["directory"] if self.win.pid else None
        try:
            discovery.open_interactive(self.agent, exe, cwd)
        except RuntimeError as exc:
            QMessageBox.information(self, "Terminal", str(exc))


class UsagePage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page_title("gauge", "Uso e limites", "Somente dados fornecidos pelos clientes oficiais. Quando não há "
                                   "dado confiável, o painel diz 'indisponível' — nunca mostra porcentagens inventadas."))
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 6, 0)
        grid = QHBoxLayout()
        self.cards = {a: UsageCard(win, a) for a in ("codex", "claude")}
        for c in self.cards.values():
            grid.addWidget(c, 1)
        lay.addLayout(grid)
        eco = Card()
        eco.lay.addWidget(label("ECONOMIA", "section"))
        eco.lay.addWidget(label("• Tarefas nunca são iniciadas quando o cliente oficial já informou limite atingido; a fila "
                                "pausa após falhas para não consumir cota.\n• Ajuste subagentes, ciclos da Equipe e "
                                "paralelismo em Configurações. O Studio nunca compra créditos nem usa API faturada.",
                                "muted", wrap=True))
        lay.addWidget(eco)
        lay.addStretch(1)
        outer.addWidget(scroll(content), 1)

    def refresh(self):
        for c in self.cards.values():
            c.load_cached()


class CliCard(Card):
    def __init__(self, win, agent: str):
        super().__init__(accent=AGENT[agent]["color"])
        self.win, self.agent = win, agent
        self.state = Pill("não verificado", C["muted"])
        self.lay.addLayout(agent_head(agent, self.state))
        self.info = label("", wrap=True, selectable=True)
        self.info.setTextFormat(Qt.RichText)
        self.lay.addWidget(self.info)
        row = QHBoxLayout()
        self.b_diag = button("Diagnosticar", "pulse", "primary")
        self.b_diag.clicked.connect(self.run)
        self.b_login = button("Entrar", "key", tip="Abre um terminal com o login oficial da CLI")
        self.b_login.clicked.connect(self.login)
        self.b_pick = button("Escolher executável…", "folder-open", "ghost")
        self.b_pick.clicked.connect(self.pick)
        self.b_test = button("Teste real", "play", "ghost", "Envia uma mensagem mínima pela assinatura para confirmar "
                             "que a execução headless funciona (consome uma fração muito pequena da cota)")
        self.b_test.clicked.connect(self.smoke)
        for b in (self.b_diag, self.b_login, self.b_pick, self.b_test):
            row.addWidget(b)
        row.addStretch(1)
        self.lay.addLayout(row)

    def display(self, diag):
        if diag is None:
            self.info.setText(f"<span style='color:{C['muted']}'>Clique em Diagnosticar.</span>")
            return
        self.state.set(diag.label, STATE_COLORS.get(diag.state, C["muted"]))
        rows = []
        if diag.executable:
            exe = diag.executable if len(diag.executable) <= 70 else diag.executable[:22] + "…" + diag.executable[-44:]
            rows.append(f"<b>Executável:</b> <code>{exe}</code> <span style='color:{C['dim']}'>({diag.found_by})</span>")
            self.info.setToolTip(diag.executable)
        if diag.version:
            rows.append(f"<b>Versão:</b> {diag.version}")
        if diag.auth_method:
            rows.append(f"<b>Login:</b> {diag.auth_method}" + (f" • plano {diag.plan}" if diag.plan else ""))
        rows += [f"<span style='color:{C['muted']}'>• {d}</span>" for d in diag.details]
        rows += [f"<span style='color:{C['warning']}'>⚠ {w}</span>" for w in diag.warnings]
        rows += [f"<span style='color:{C['gold']}'>→ {f}</span>" for f in diag.fixes]
        rows.append(f"<span style='color:{C['dim']}'>Verificado em {diag.checked_at[:19].replace('T', ' ')}</span>")
        self.info.setText("<br>".join(rows))
        self.b_test.setEnabled(diag.usable)
        self.b_login.setEnabled(bool(diag.executable))

    def run(self):
        self.b_diag.setEnabled(False)
        self.state.set("verificando…", C["violet"])
        cwd = self.win.store.project(self.win.pid)["directory"] if self.win.pid else None
        run_bg(lambda: self.win.engine.diagnose(self.agent, cwd),
               lambda d: (self.b_diag.setEnabled(True), self.display(d), self.win.refresh_status()),
               lambda e, tb: (self.b_diag.setEnabled(True), self.info.setText(f"Erro inesperado: {e}<br><pre>{tb[-800:]}</pre>")))

    def login(self):
        d = self.win.engine.diagnoses.get(self.agent)
        if not d or not d.executable:
            return
        try:
            discovery.open_login_terminal(self.agent, d.executable)
            self.win.toast("Conclua o login no terminal aberto e depois clique em Diagnosticar.")
        except RuntimeError as exc:
            QMessageBox.information(self, "Login", str(exc))

    def pick(self):
        filt = "Executáveis (*.exe *.cmd *.bat);;Todos (*)" if os.name == "nt" else ""
        path = pick_file(self, f"Executável do {AGENT[self.agent]['name']}", "", filt)
        if path:
            self.win.store.set_setting(f"cli.{self.agent}.path", path)
            self.run()

    def smoke(self):
        if QMessageBox.question(self, "Teste real", f"Enviar uma mensagem mínima ao {AGENT[self.agent]['name']} pela sua "
                                "assinatura (somente leitura, sem arquivos)? Consome uma fração muito pequena da cota.") != QMessageBox.Yes:
            return
        if self.win.pid is None:
            QMessageBox.information(self, "Teste real", "Vincule um projeto primeiro (o teste roda nessa pasta, somente leitura).")
            return
        from ..messages import Intent
        self.win.engine.submit(self.win.pid, Intent("execute", self.agent, "Teste de conexão do Kaguya Studio: responda "
                               "apenas 'OK, conectado' e o nome do modelo em uso. Não leia nem altere arquivos."), web=False)
        self.win.go("chat")


class GitHubCard(Card):
    """GitHub CLI status: install, login (official browser flow) and account shown — never the token."""

    def __init__(self, win):
        super().__init__(accent=C["text"])
        self.win = win
        head = QHBoxLayout()
        head.addWidget(icon_label("git", C["text"], 24))
        t = label("GitHub", "h2")
        head.addWidget(t)
        head.addWidget(label("GitHub CLI oficial (gh) • login pelo navegador", "dim"))
        head.addStretch(1)
        self.state = Pill("não verificado", C["muted"])
        head.addWidget(self.state)
        self.lay.addLayout(head)
        self.info = label("Clique em Diagnosticar.", "muted", wrap=True)
        self.info.setTextFormat(Qt.RichText)
        self.lay.addWidget(self.info)
        row = QHBoxLayout()
        b = button("Diagnosticar", "pulse", "primary")
        b.clicked.connect(self.run)
        self.b_login = button("Entrar no GitHub", "key", tip="Abre 'gh auth login --web' no terminal; você autoriza no navegador")
        self.b_login.clicked.connect(self.login)
        inst = button("Instalar GitHub CLI", "external", "ghost")
        inst.clicked.connect(lambda: open_url("https://cli.github.com/"))
        pick = button("Escolher executável…", "folder-open", "ghost")
        pick.clicked.connect(self.pick)
        for w in (b, self.b_login, inst, pick):
            row.addWidget(w)
        row.addStretch(1)
        self.lay.addLayout(row)

    def display(self, st):
        if st is None:
            return
        color = {"pronto": C["success"], "nao_autenticado": C["warning"], "nao_instalado": C["danger"]}.get(st.state, C["danger"])
        self.state.set(st.label, color)
        rows = []
        if st.executable:
            rows.append(f"<b>Executável:</b> <code>{st.executable}</code>" + (f" • {st.version}" if st.version else ""))
        rows += [f"<span style='color:{C['muted']}'>• {d}</span>" for d in st.details]
        rows += [f"<span style='color:{C['gold']}'>→ {f}</span>" for f in st.fixes]
        self.info.setText("<br>".join(rows))
        self.b_login.setEnabled(bool(st.executable))

    def run(self):
        self.state.set("verificando…", C["violet"])
        run_bg(lambda: self.win.refresh_github_status(), lambda st: self.display(st))

    def login(self):
        from ..github import login_command
        st = self.win.gh_status
        if not st or not st.executable:
            return
        args = login_command(st.executable)
        try:
            discovery.open_console(args)
            self.win.toast("Conclua o login no navegador e depois clique em Diagnosticar.")
        except Exception as exc:
            QMessageBox.information(self, "GitHub", f"Rode no terminal: {' '.join(args)}\n\n({exc})")

    def pick(self):
        filt = "Executáveis (*.exe *.cmd *.bat);;Todos (*)" if os.name == "nt" else ""
        path = pick_file(self, "Executável da GitHub CLI (gh)", "", filt)
        if path:
            self.win.store.set_setting("cli.gh.path", path)
            self.run()


class DiagnosticsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page_title("pulse", "Diagnóstico", "Conexão real com as CLIs oficiais, motivo exato de cada falha e "
                                   "como corrigir. Nenhum segredo é exibido ou gravado."))
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 6, 0)
        lay.setSpacing(12)
        self.cards = {a: CliCard(win, a) for a in ("codex", "claude")}
        for c in self.cards.values():
            lay.addWidget(c)
        self.gh_card = GitHubCard(win)
        lay.addWidget(self.gh_card)
        q = Card()
        q.lay.addWidget(label("VERIFICAÇÕES DO PROJETO", "section"))
        q.lay.addWidget(label("Checagens feitas pelo próprio Studio (não pelas IAs). Testes executam código do repositório e "
                              "por isso pedem confirmação.", "muted", wrap=True))
        qr = QHBoxLayout()
        b1 = button("Checagem segura (Git)", "shield")
        b1.clicked.connect(lambda: self.quality(False))
        b2 = button("Executar testes do projeto", "bug")
        b2.clicked.connect(lambda: self.quality(True))
        b3 = button("Abrir pasta de logs", "folder-open", "ghost")
        b3.clicked.connect(lambda: open_path(str(self.win.engine.home / "logs")))
        b4 = button("Exportar relatório", "download", "ghost", "Relatório JSON sem segredos para compartilhar ao pedir ajuda")
        b4.clicked.connect(self.export)
        for b in (b1, b2, b3, b4):
            qr.addWidget(b)
        qr.addStretch(1)
        q.lay.addLayout(qr)
        self.q_out = label("", "code", wrap=True, selectable=True)
        q.lay.addWidget(self.q_out)
        lay.addWidget(q)
        lay.addStretch(1)
        outer.addWidget(scroll(content), 1)

    def refresh(self):
        for a, c in self.cards.items():
            c.display(self.win.engine.diagnoses.get(a))
        self.gh_card.display(self.win.gh_status)

    def quality(self, tests: bool):
        if self.win.pid is None:
            return
        if tests and QMessageBox.question(self, "Executar testes", "Os testes executam código do próprio projeto. "
                                          "Use apenas em repositórios confiáveis. Continuar?") != QMessageBox.Yes:
            return
        proj = self.win.store.project(self.win.pid)
        self.q_out.setText("Executando…")
        run_bg(lambda: run_checks(Path(proj["directory"]), run_tests=tests, test_command=proj.get("test_command")),
               lambda checks: self.q_out.setText("\n\n".join(f"{c.name}: {c.status}\n{c.details[-1500:]}" for c in checks)))

    def export(self):
        data = {"gerado_em": datetime.now().isoformat(timespec="seconds"), "versao": __import__("kaguya").VERSION,
                "sistema": os.name, "clis": {k: v.to_dict() for k, v in self.win.engine.diagnoses.items()},
                "projetos": [{"nome": p["name"], "pasta": p["directory"], "vault_proprio": bool(p.get("vault"))}
                             for p in self.win.store.projects()],
                "vault_global_definido": bool(self.win.store.global_vault()),
                "aviso": "Sem conteúdo de notas, tokens ou credenciais. Revise caminhos antes de compartilhar."}
        out = self.win.engine.home / "diagnosticos" / f"diagnostico_{datetime.now():%Y%m%d_%H%M%S}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.win.toast(f"Relatório salvo em {out}")
        open_path(str(out.parent))


class SettingsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page_title("settings", "Configurações", "Projetos, equipe, economia, voz e mascotes."))
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 6, 0)
        lay.setSpacing(12)
        # projects
        pc = Card()
        head = QHBoxLayout()
        head.addWidget(label("PROJETOS VINCULADOS", "section"))
        head.addStretch(1)
        add = button("Vincular projeto", "folder-plus", "primary")
        add.clicked.connect(win.add_project)
        edit = button("Editar", "edit")
        edit.clicked.connect(self.edit_project)
        rem = button("Desvincular", "x", "ghost", "Remove da lista do Studio. Nenhum arquivo é apagado.")
        rem.clicked.connect(self.remove_project)
        for b in (edit, rem, add):
            head.addWidget(b)
        pc.lay.addLayout(head)
        self.projects = table(["Projeto", "Pasta", "Vault", "Testes"], stretch=1)
        self.projects.setMinimumHeight(170)
        pc.lay.addWidget(self.projects)
        lay.addWidget(pc)
        # team & economy
        tc = Card()
        tc.lay.addWidget(label("EQUIPE E ECONOMIA", "section"))
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        self.impl = QComboBox()
        self.impl.addItems(["Codex implementa, Claude revisa", "Claude implementa, Codex revisa"])
        self.impl.setCurrentIndex(0 if win.engine.setting("team.implementer") == "codex" else 1)
        self.impl.currentIndexChanged.connect(self.save_team)
        self.cycles = QSpinBox(minimum=1, maximum=5, value=int(win.engine.setting("team.max_cycles")))
        self.cycles.setMaximumWidth(170)
        self.cycles.valueChanged.connect(lambda v: win.store.set_setting("team.max_cycles", v))
        self.subagents = QSpinBox(minimum=0, maximum=6, value=int(win.engine.setting("economy.max_subagents")))
        self.subagents.setMaximumWidth(170)
        self.subagents.valueChanged.connect(lambda v: win.store.set_setting("economy.max_subagents", v))
        self.workers = QSpinBox(minimum=1, maximum=4, value=int(win.engine.setting("parallel.max_workers")))
        self.workers.setMaximumWidth(170)
        self.workers.valueChanged.connect(lambda v: win.store.set_setting("parallel.max_workers", v))
        self.timeout = QSpinBox(minimum=5, maximum=240, value=int(win.engine.setting("run.timeout_min")), suffix=" min")
        self.timeout.setMaximumWidth(170)
        self.timeout.valueChanged.connect(lambda v: win.store.set_setting("run.timeout_min", v))
        self.review_model = QLineEdit(win.engine.setting("models.review") or "")
        self.review_model.setPlaceholderText("padrão da CLI (ex.: sonnet para revisões mais econômicas)")
        self.review_model.editingFinished.connect(lambda: win.store.set_setting("models.review", self.review_model.text().strip()))
        form.addRow("Papéis da Equipe", self.impl)
        form.addRow("Máx. ciclos de correção", self.cycles)
        form.addRow("Máx. subagentes por tarefa", self.subagents)
        form.addRow("Trabalhadores paralelos", self.workers)
        form.addRow("Tempo limite por execução", self.timeout)
        form.addRow("Modelo do revisor", self.review_model)
        tc.lay.addLayout(form)
        self.t_continue = Toggle("Continuar a conversa anterior (sessão por projeto)", bool(win.engine.setting("session.continue")))
        self.t_continue.toggled.connect(lambda v: win.store.set_setting("session.continue", v))
        self.t_suggest = Toggle("Sugerir agentes instalados adequados à tarefa", bool(win.engine.setting("agents.suggest")))
        self.t_suggest.toggled.connect(lambda v: win.store.set_setting("agents.suggest", v))
        tc.lay.addWidget(self.t_continue)
        tc.lay.addWidget(self.t_suggest)
        lay.addWidget(tc)
        # computer use
        dc = Card(accent=C["gold"])
        dc.lay.addWidget(label("USO DO COMPUTADOR (MOUSE E TECLADO)", "section"))
        dc.lay.addWidget(label("Ligue \"Usar o PC\" na conversa para a IA ver a tela e usar mouse/teclado nas tarefas. "
                               "Restringir a uma janela protege o resto do seu computador e o que aparece nas capturas. "
                               "Para parar: botão Parar do aviso, Ctrl+Alt+End ou mouse no canto superior esquerdo.",
                               "muted", wrap=True))
        dform = QFormLayout()
        dform.setHorizontalSpacing(18)
        self.desk_window = QLineEdit(str(win.engine.setting("desktop.window") or ""))
        self.desk_window.setPlaceholderText("vazio = tela inteira (não recomendado)")
        self.desk_window.editingFinished.connect(
            lambda: win.store.set_setting("desktop.window", self.desk_window.text().strip()))
        self.desk_max = QSpinBox(minimum=10, maximum=2000, value=int(win.engine.setting("desktop.max_actions")))
        self.desk_max.setMaximumWidth(170)
        self.desk_max.valueChanged.connect(lambda v: win.store.set_setting("desktop.max_actions", v))
        dform.addRow("Somente a janela com título contendo", self.desk_window)
        dform.addRow("Máx. ações por tarefa", self.desk_max)
        dc.lay.addLayout(dform)
        lay.addWidget(dc)
        # voice
        vc = Card()
        vc.lay.addWidget(label("VOZ LOCAL (SEM API PAGA)", "section"))
        self.voice_info = label("", "muted", wrap=True)
        vc.lay.addWidget(self.voice_info)
        from ..voice.neural import DEFAULT_PRESET, PRESETS
        nrow = QHBoxLayout()
        self.neural_info = label("", "muted", wrap=True)
        self.neural_btn = button("Baixar vozes neurais (~120 MB)", "download", "primary")
        self.neural_btn.clicked.connect(self.download_neural)
        from PySide6.QtWidgets import QProgressBar
        self.neural_progress = QProgressBar()
        self.neural_progress.setFixedHeight(8)
        self.neural_progress.hide()
        nrow.addWidget(self.neural_info, 1)
        nrow.addWidget(self.neural_btn)
        vc.lay.addLayout(nrow)
        vc.lay.addWidget(self.neural_progress)
        vform = QFormLayout()
        self.engine_combo = QComboBox()
        for key, text in (("auto", "Automático (neural se instalada)"), ("neural", "Vozes neurais (Kokoro)"),
                          ("windows", "Vozes do Windows")):
            self.engine_combo.addItem(text, key)
            if key == win.store.get_setting("voice.engine", "auto"):
                self.engine_combo.setCurrentIndex(self.engine_combo.count() - 1)
        self.engine_combo.currentIndexChanged.connect(lambda: win.store.set_setting("voice.engine", self.engine_combo.currentData()))
        vform.addRow("Motor de voz", self.engine_combo)
        self.neural_combos = {}
        for agent, title in (("codex", "Voz neural da Kaguya"), ("claude", "Voz neural da Claude")):
            box = QHBoxLayout()
            cb = QComboBox()
            for pid, preset in PRESETS.items():
                cb.addItem(preset.label, pid)
                if pid == win.store.get_setting(f"voice.neural_{agent}", DEFAULT_PRESET[agent]):
                    cb.setCurrentIndex(cb.count() - 1)
            cb.currentIndexChanged.connect(lambda _=0, a=agent, c=cb: win.store.set_setting(f"voice.neural_{a}", c.currentData()))
            prev = button("Ouvir amostra", "play", "ghost")
            prev.clicked.connect(lambda _=False, a=agent: self.preview_voice(a))
            box.addWidget(cb, 1)
            box.addWidget(prev)
            self.neural_combos[agent] = cb
            vform.addRow(title, box)
        self.voice_combos = {}
        for agent, title in (("codex", "Voz do Windows da Kaguya"), ("claude", "Voz do Windows da Claude")):
            cb = QComboBox()
            cb.addItem("Automática (pt-BR se instalada)", "")
            cb.currentIndexChanged.connect(lambda _=0, a=agent, c=cb: win.store.set_setting(f"voice.voice_{a}", c.currentData()))
            self.voice_combos[agent] = cb
            vform.addRow(title, cb)
        self.stt_model = QComboBox()
        for k, v in stt.MODELS.items():
            self.stt_model.addItem(f"{k} — {v}", k)
        self.stt_model.setCurrentIndex(list(stt.MODELS).index(win.store.get_setting("voice.model", "small")))
        self.stt_model.currentIndexChanged.connect(lambda: win.store.set_setting("voice.model", self.stt_model.currentData()))
        vform.addRow("Modelo de transcrição", self.stt_model)
        self.mic_dev = QComboBox()
        self.out_dev = QComboBox()
        self.mic_dev.currentIndexChanged.connect(lambda: self._save_dev("input", self.mic_dev))
        self.out_dev.currentIndexChanged.connect(lambda: self._save_dev("output", self.out_dev))
        vform.addRow("Microfone", self.mic_dev)
        vform.addRow("Saída (fone/caixa)", self.out_dev)
        arow = QHBoxLayout()
        ref = button("Atualizar dispositivos", "refresh", "ghost")
        ref.clicked.connect(lambda: self.win.check_audio_devices(force=True))
        self.mic_test = button("Testar microfone", "mic")
        self.mic_test.clicked.connect(self.test_mic)
        self.mic_meter = Meter(C["success"])
        self.mic_meter.setFixedWidth(160)
        self.mic_meter.set_value(0)
        snd = button("Testar som", "volume")
        snd.clicked.connect(lambda: self.win.voice.speak("Olá! Este é o teste de som do Kaguya Studio.", "codex"))
        for w in (ref, self.mic_test, self.mic_meter, snd):
            arow.addWidget(w)
        arow.addStretch(1)
        self._filling = False
        vc.lay.addLayout(vform)
        vc.lay.addLayout(arow)
        self.t_consent = Toggle("Autorizo baixar o modelo de transcrição escolhido (uma vez, fica no computador)",
                                bool(win.store.get_setting("voice.model_consent", False)))
        self.t_consent.toggled.connect(lambda v: win.store.set_setting("voice.model_consent", v))
        self.t_autoread = Toggle("Ler respostas automaticamente", bool(win.store.get_setting("voice.autoread", False)))
        self.t_autoread.toggled.connect(lambda v: win.store.set_setting("voice.autoread", v))
        vc.lay.addWidget(self.t_consent)
        vc.lay.addWidget(self.t_autoread)
        lay.addWidget(vc)
        # mascots & migration
        mc = Card()
        mc.lay.addWidget(label("MASCOTES E MIGRAÇÃO", "section"))
        mrow = QHBoxLayout()
        for agent in ("codex", "claude"):
            b = button(f"{AGENT[agent]['mascot']} flutuante", "window", tip="Mostrar/ocultar na área de trabalho")
            b.clicked.connect(lambda _=False, a=agent: win.mascots[a].toggle_window())
            mrow.addWidget(b)
        self.kaguya_variant = QComboBox()
        km = win.mascots["codex"]
        for key, text in km.variants():
            self.kaguya_variant.addItem(text, key)
            if key == km.prefs.variant:
                self.kaguya_variant.setCurrentIndex(self.kaguya_variant.count() - 1)
        self.kaguya_variant.currentIndexChanged.connect(lambda: km.set_variant(self.kaguya_variant.currentData()))
        mrow.addWidget(label("Visual da Kaguya", "dim"))
        mrow.addWidget(self.kaguya_variant)
        imp = button("Importar dados da V3.x", "download", "ghost", "Copia projetos e fila da V3 (o banco antigo não é alterado)")
        imp.clicked.connect(self.import_v3)
        mrow.addWidget(imp)
        mrow.addStretch(1)
        mc.lay.addLayout(mrow)
        mc.lay.addWidget(label(f"Dados do Studio: {win.engine.home}", "dim", selectable=True))
        lay.addWidget(mc)
        lay.addStretch(1)
        outer.addWidget(scroll(content), 1)
        self._voices_loaded = False

    def save_team(self):
        impl = "codex" if self.impl.currentIndex() == 0 else "claude"
        self.win.store.set_setting("team.implementer", impl)
        self.win.store.set_setting("team.reviewer", "claude" if impl == "codex" else "codex")

    def refresh(self):
        self.projects.setRowCount(0)
        gv = self.win.store.global_vault()
        for p in self.win.store.projects():
            r = self.projects.rowCount()
            self.projects.insertRow(r)
            self.projects.setItem(r, 0, item(p["name"], C["gold"], p["id"]))
            self.projects.setItem(r, 1, item(p["directory"]))
            self.projects.setItem(r, 2, item(p.get("vault") or (f"global: {gv}" if gv else "—"), C["muted"]))
            self.projects.setItem(r, 3, item(p.get("test_command") or "automático", C["dim"]))
        st = stt.status(self.win.engine.home / "modelos", self.win.store.get_setting("voice.model", "small"))
        tts = Speaker.backend()
        parts = [f"Leitura: {tts or 'indisponível neste sistema'}."]
        if st.ready:
            parts.append("Transcrição: faster-whisper + sounddevice instalados" + (" • modelo já baixado." if st.model_cached else
                                                                                   " • modelo ainda não baixado."))
        else:
            parts.append(f"Transcrição: faltam {', '.join(st.missing)}. Instale com o botão no INSTALAR.bat (opção voz) ou: "
                         f"{stt.INSTALL_CMD}")
        self.voice_info.setText(" ".join(parts))
        self.refresh_neural()
        if not self._voices_loaded and os.name == "nt":
            self._voices_loaded = True
            run_bg(Speaker().voices, self._fill_voices)

    def _fill_voices(self, voices):
        for agent, cb in self.voice_combos.items():
            cur = self.win.store.get_setting(f"voice.voice_{agent}", "") or self.win.store.get_setting("voice.tts_voice", "")
            for name, culture in voices:
                cb.addItem(f"{name} ({culture})", name)
                if name == cur:
                    cb.setCurrentIndex(cb.count() - 1)

    def refresh_neural(self):
        from ..voice import neural
        v = self.win.voice.neural
        if not neural.package_available():
            self.neural_info.setText("Vozes neurais: o motor não está incluído nesta cópia (atualize o Studio).")
            self.neural_btn.hide()
        elif v.installed():
            self.neural_info.setText("Vozes neurais instaladas: fala natural em pt-BR, local e gratuita.")
            self.neural_btn.hide()
        else:
            self.neural_info.setText("Vozes neurais (Kokoro): fala natural em pt-BR, roda no seu PC sem custo. "
                                     "Download único de ~120 MB (só após você clicar).")
            self.neural_btn.show()

    def download_neural(self):
        v = self.win.voice.neural
        self.neural_btn.setEnabled(False)
        self.neural_progress.show()
        self.neural_progress.setValue(0)

        def prog(done, total):
            self.win.bridge.call.emit(lambda: (self.neural_progress.setMaximum(total), self.neural_progress.setValue(done)))

        def done(_):
            self.neural_btn.setEnabled(True)
            self.neural_progress.hide()
            self.refresh_neural()
            self.win.toast("Vozes neurais instaladas. Use 'Ouvir amostra' para escolher a voz de cada IA.")

        def fail(exc, tb):
            self.neural_btn.setEnabled(True)
            self.neural_progress.hide()
            QMessageBox.warning(self, "Vozes neurais", f"Não foi possível baixar: {exc}")
        run_bg(lambda: v.download(prog), done, fail)

    def preview_voice(self, agent: str):
        if not self.win.voice.neural.ready:
            self.win.toast("Baixe as vozes neurais primeiro.")
            return
        name = "Kaguya" if agent == "codex" else "Claude"
        self.win.voice.stop_speaking()
        if not self.win.voice.say(f"Oi! Eu sou a {name}. Esta é a minha voz no Kaguya Studio.", agent):
            self.win.toast("Saída de áudio indisponível nesta cópia.")

    def fill_devices(self, ins, outs):
        self._filling = True
        for combo, devs, key, default in ((self.mic_dev, ins, "voice.input_name", "Microfone padrão do Windows"),
                                          (self.out_dev, outs, "voice.output_name", "Saída padrão do Windows")):
            cur = self.win.store.get_setting(key)
            combo.clear()
            combo.addItem(default, None)
            for d in devs:
                combo.addItem(d.name + ("  (padrão)" if d.default else ""), d.name)
                if d.name == cur:
                    combo.setCurrentIndex(combo.count() - 1)
            if cur and combo.currentData() != cur:
                combo.addItem(f"{cur}  (desconectado)", cur)
                combo.setCurrentIndex(combo.count() - 1)
        self._filling = False

    def _save_dev(self, kind: str, combo):
        if self._filling:
            return
        self.win.store.set_setting(f"voice.{kind}_name", combo.currentData())
        self.win.refresh_devices_ui()

    def test_mic(self):
        from ..voice import devices as dv
        if not dv.available():
            QMessageBox.information(self, "Microfone", "O acesso ao microfone não está instalado nesta cópia.")
            return
        self.mic_test.setEnabled(False)
        self.mic_test.setText("Fale algo… (3 s)")
        dev = self.win.voice.input_index()
        levels = []

        def work():
            rec = stt.Recorder(dev, max_seconds=4, level=lambda v: (levels.append(v),
                               self.win.bridge.call.emit(lambda v=v: self.mic_meter.set_value(v * 100))))
            rec.start()
            import time as _t
            _t.sleep(3)
            rec.stop()
            return max(levels or [0])

        def done(peak):
            self.mic_test.setEnabled(True)
            self.mic_test.setText("Testar microfone")
            self.mic_meter.set_value(peak * 100)
            self.win.toast("Microfone funcionando: o Studio captou sua voz." if peak > 0.08 else
                           "Quase nenhum som captado. Confira o microfone escolhido e a permissão de microfone do Windows.")

        def fail(exc, tb):
            self.mic_test.setEnabled(True)
            self.mic_test.setText("Testar microfone")
            QMessageBox.warning(self, "Microfone", f"Não foi possível abrir o microfone: {exc}")
        run_bg(work, done, fail)

    def _selected_pid(self):
        rows = self.projects.selectionModel().selectedRows()
        return self.projects.item(rows[0].row(), 0).data(Qt.UserRole) if rows else self.win.pid

    def edit_project(self):
        pid = self._selected_pid()
        if pid is None:
            return
        dlg = ProjectDialog(self.win.store, self.win, self.win.store.project(pid))
        if dlg.exec():
            self.win.refresh_all()

    def remove_project(self):
        pid = self._selected_pid()
        if pid is None:
            return
        name = self.win.store.project(pid)["name"]
        if QMessageBox.question(self, "Desvincular", f"Desvincular '{name}' do Studio?\nNenhum arquivo será apagado; "
                                "o histórico fica guardado e volta se você vincular a mesma pasta.") == QMessageBox.Yes:
            self.win.engine.cancel(pid)
            self.win.store.remove_project(pid)
            if self.win.pid == pid:
                self.win.pid = None
            self.win.refresh_all()

    def import_v3(self):
        db = legacy_v3_database()
        if not db:
            path = pick_file(self, "Banco da V3 (studio.sqlite3)", "", "SQLite (*.sqlite3 *.db)")
            db = Path(path) if path else None
        if not db:
            return
        self.win.store.set_setting("migration.v3.done", None)
        rep = self.win.store.import_v3(db)
        QMessageBox.information(self, "Importação", f"{rep['projects']} projeto(s) e {rep['tasks']} tarefa(s) importados."
                                + (f"\nVault global: {rep['vault']}" if rep["vault"] else ""))
        self.win.refresh_all()
