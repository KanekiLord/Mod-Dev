"""Extensões (Kaguya Extension Hub): what Codex and Claude Code really have, with evidence — and supervised changes."""
from __future__ import annotations

import html
import shlex

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLineEdit,
                               QListWidget, QMessageBox, QPlainTextEdit, QSplitter, QTableWidget, QTableWidgetItem,
                               QTextBrowser, QVBoxLayout, QWidget)

from ..hub.model import KINDS, LABELS, PROVIDERS, STATES
from .common import open_path, run_bg
from .page_work import page_title
from .theme import AGENT, C
from .widgets import Card, button, label

STATE_COLOR = {"descoberto": C["dim"], "configurado": C["muted"], "habilitado": C["info"],
               "carregado_na_sessao": C["violet"], "conectado": C["success"], "capacidade_verificada": C["success"]}
BAD = {"falha": C["danger"], "requer_login": C["warning"], "requer_aprovacao": C["warning"], "requer_reinicio": C["gold"],
       "removido": C["dim"], "desabilitado": C["dim"], "somente_web": C["gold"], "indisponivel": C["danger"]}
PAGE = 400


def _item(text: str, color: str | None = None, data=None) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    if color:
        from PySide6.QtGui import QColor
        it.setForeground(QColor(color))
    if data is not None:
        it.setData(Qt.UserRole, data)
    return it


class PlanDialog(QDialog):
    """Shows exactly what will run and asks for an explicit review before anything changes."""

    def __init__(self, parent, plan):
        super().__init__(parent)
        self.plan = plan
        self.setWindowTitle("Plano de mudança — precisa da sua aprovação")
        self.resize(720, 520)
        lay = QVBoxLayout(self)
        rev = plan.review or {}
        parts = [f"<h3>{html.escape(plan.kind)} · {html.escape(plan.name)}</h3>",
                 f"<p><b>Comando oficial que vai rodar:</b><br><code>{html.escape(plan.display)}</code></p>",
                 "<p><b>O que muda:</b></p><ul>" + "".join(f"<li>{html.escape(c)}</li>" for c in plan.changes) + "</ul>",
                 "<p><b>Revisão de segurança</b></p><ul>"
                 f"<li>Origem: {html.escape(str(rev.get('origem', '')))}</li>"
                 f"<li>Permissões: {html.escape(', '.join(rev.get('permissoes') or []) or '—')}</li>"
                 f"<li>Custos: {html.escape(str(rev.get('custos', '')))}</li>"
                 f"<li>Segredos: {html.escape(', '.join(rev.get('segredos') or []) or '—')}</li>"
                 f"<li>Scripts: {html.escape(str(rev.get('scripts', '')))}</li></ul>"]
        if plan.warnings:
            parts.append(f"<p style='color:{C['warning']}'>⚠ " + "<br>⚠ ".join(html.escape(w) for w in plan.warnings)
                         + "</p>")
        parts.append(f"<p><b>Para desfazer:</b> {html.escape(plan.rollback)}</p>")
        view = QTextBrowser()
        view.setHtml("".join(parts))
        lay.addWidget(view, 1)
        self.reviewed = QCheckBox("Revisei a origem, as permissões e os custos e autorizo esta mudança")
        lay.addWidget(self.reviewed)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Aprovar e executar")
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        self.buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        self.reviewed.toggled.connect(self.buttons.button(QDialogButtonBox.Ok).setEnabled)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)


class InstallDialog(QDialog):
    def __init__(self, parent, projects: list[dict]):
        super().__init__(parent)
        self.setWindowTitle("Solicitar instalação de MCP")
        self.resize(620, 520)
        lay = QVBoxLayout(self)
        lay.addWidget(label("O Hub monta um plano com o comando oficial do cliente escolhido. Nada é instalado antes da "
                            "sua aprovação, e a outra IA não recebe cópia (ela pode pedir o trabalho pelo Studio).",
                            "dim", wrap=True))
        form = QFormLayout()
        self.provider = QComboBox()
        self.provider.addItem("Miwa — Claude Code", "claude")
        self.provider.addItem("Kaguya — Codex", "codex")
        self.scope = QComboBox()
        for k, t in (("user", "Todas as minhas sessões (usuário)"), ("project", "Projeto (.mcp.json, compartilhável)"),
                     ("local", "Só este projeto, só para mim")):
            self.scope.addItem(t, k)
        self.project = QComboBox()
        for p in projects:
            self.project.addItem(p["name"], p["directory"])
        self.name = QLineEdit()
        self.name.setPlaceholderText("ex.: blender")
        self.command = QLineEdit()
        self.command.setPlaceholderText("servidor local: ex. uvx   (deixe vazio se for URL)")
        self.args = QLineEdit()
        self.args.setPlaceholderText("argumentos: ex. blender-mcp")
        self.url = QLineEdit()
        self.url.setPlaceholderText("servidor remoto: https://…   (deixe vazio se for comando)")
        self.env = QPlainTextEdit()
        self.env.setPlaceholderText("variáveis, uma por linha: NOME=valor  (os valores vão só para o cliente oficial)")
        self.env.setFixedHeight(80)
        self.origin = QLineEdit()
        self.origin.setPlaceholderText("de onde vem (página oficial / repositório) — revise antes de aprovar")
        for t, w in (("IA", self.provider), ("Escopo", self.scope), ("Projeto", self.project), ("Nome", self.name),
                     ("Comando", self.command), ("Argumentos", self.args), ("URL", self.url), ("Variáveis", self.env),
                     ("Origem", self.origin)):
            form.addRow(t, w)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Ver o plano")
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def values(self) -> dict:
        env = {}
        for line in self.env.toPlainText().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
        return {"provider": self.provider.currentData(), "scope": self.scope.currentData(),
                "project": self.project.currentData() or "", "name": self.name.text().strip(),
                "command": self.command.text().strip(), "args": shlex.split(self.args.text(), posix=False) if
                self.args.text().strip() else [], "url": self.url.text().strip(), "env": env,
                "origin": self.origin.text().strip()}


class HubPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self._busy = False
        self._shown = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page_title("layers", "Extensões", "MCPs, plugins, skills, agentes e hooks que o Codex e o "
                                   "Claude Code já têm — detectados sozinhos, com o estado real e a evidência."))
        top = QHBoxLayout()
        self.summary = label("", "muted", wrap=True)
        self.summary.setTextFormat(Qt.RichText)
        top.addWidget(self.summary, 1)
        self.sync_btn = button("Sincronizar agora", "refresh", "primary", "Relê as configurações dos clientes (só leitura)")
        self.sync_btn.clicked.connect(lambda: self.sync())
        self.install_btn = button("Solicitar instalação…", "plus", None, "Monta um plano com o comando oficial; você aprova")
        self.install_btn.clicked.connect(self.request_install)
        self.web_btn = button("Plugin só da web…", "globe", "ghost",
                              "Registrar um plugin/conector que existe só no ChatGPT/Claude web (nunca usável pela CLI)")
        self.web_btn.clicked.connect(self.register_web)
        self.log_btn = button("Histórico", "clock", "ghost")
        self.log_btn.clicked.connect(self.show_log)
        for b in (self.sync_btn, self.install_btn, self.web_btn, self.log_btn):
            top.addWidget(b)
        outer.addLayout(top)
        filt = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar por nome, descrição ou ferramenta")
        self.search.textChanged.connect(lambda: self.refresh_table())
        self.f_provider = QComboBox()
        self.f_provider.addItem("Todas as IAs", "")
        for k, t in PROVIDERS.items():
            self.f_provider.addItem(t, k)
        self.f_kind = QComboBox()
        self.f_kind.addItem("Todos os tipos", "")
        for k, t in KINDS.items():
            self.f_kind.addItem(t, k)
        self.f_status = QComboBox()
        self.f_status.addItem("Todos os estados", "")
        for k in STATES + ["requer_login", "requer_aprovacao", "requer_reinicio", "falha", "desabilitado",
                           "somente_web", "removido"]:
            self.f_status.addItem(LABELS[k], k)
        self.f_project = QComboBox()
        for w in (self.f_provider, self.f_kind, self.f_status, self.f_project):
            w.currentIndexChanged.connect(lambda _=0: self.refresh_table())
        filt.addWidget(self.search, 2)
        for w in (self.f_provider, self.f_kind, self.f_status, self.f_project):
            filt.addWidget(w, 1)
        outer.addLayout(filt)
        self.problems = label("", wrap=True)
        self.problems.setStyleSheet(f"color: {C['warning']};")
        self.problems.hide()
        outer.addWidget(self.problems)
        split = QSplitter(Qt.Horizontal)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Nome", "Tipo", "IA", "Escopo", "Versão", "Estado", "Condições"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self.show_detail)
        split.addWidget(self.table)
        side = Card()
        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(False)
        side.lay.addWidget(self.detail, 1)
        acts = QHBoxLayout()
        self.test_btn = button("Testar conexão", "pulse", None, "Teste oficial do cliente; nenhuma ferramenta é executada")
        self.test_btn.clicked.connect(lambda: self.test_selected(False))
        self.tools_btn = button("Listar ferramentas", "list", "ghost",
                                "Inicia o servidor só para listar as ferramentas (metadados; nada é executado)")
        self.tools_btn.clicked.connect(lambda: self.test_selected(True))
        acts.addWidget(self.test_btn)
        acts.addWidget(self.tools_btn)
        side.lay.addLayout(acts)
        acts2 = QHBoxLayout()
        self.open_btn = button("Abrir configuração original", "folder-open", "ghost")
        self.open_btn.clicked.connect(self.open_source)
        self.toggle_btn = button("Desativar", "pause", "ghost")
        self.toggle_btn.clicked.connect(self.toggle_selected)
        self.remove_btn = button("Remover…", "trash", "ghost")
        self.remove_btn.clicked.connect(self.remove_selected)
        for b in (self.open_btn, self.toggle_btn, self.remove_btn):
            acts2.addWidget(b)
        side.lay.addLayout(acts2)
        side.setMinimumWidth(360)
        split.addWidget(side)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        outer.addWidget(split, 1)
        self.more = label("", "dim")
        outer.addWidget(self.more)

    @property
    def hub(self):
        return self.win.engine.hub

    # ------------------------------------------------------------------ data
    def refresh(self):
        cur = self.f_project.currentData()
        self.f_project.blockSignals(True)
        self.f_project.clear()
        self.f_project.addItem("Todos os projetos", "")
        for p in self.win.store.projects():
            if not p.get("removed"):
                self.f_project.addItem(p["name"], p["directory"])
        self.f_project.setCurrentIndex(max(0, self.f_project.findData(cur)))
        self.f_project.blockSignals(False)
        if not self.hub.last_scan and not self._busy:
            self.sync()
        self.refresh_table()

    def sync(self, done=None):
        if self._busy:
            return
        self._busy = True
        self.sync_btn.setEnabled(False)
        self.sync_btn.setText("Sincronizando…")

        def finish(events):
            self._busy = False
            self.sync_btn.setEnabled(True)
            self.sync_btn.setText("Sincronizar agora")
            self.refresh_table()
            if done:
                done(events)

        def fail(exc, _tb):
            finish([])
            self.win.toast(f"Não foi possível sincronizar: {exc}")
        run_bg(self.hub.scan, finish, fail)

    def refresh_table(self):
        reg = self.hub.registry
        counts = reg.counts()
        chips = []
        for k in STATES + ["requer_login", "requer_aprovacao", "requer_reinicio", "falha", "somente_web", "removido"]:
            if counts.get(k):
                color = STATE_COLOR.get(k) or BAD.get(k, C["muted"])
                chips.append(f"<span style='color:{color}'><b>{counts[k]}</b> {LABELS[k]}</span>")
        last = self.hub.last_scan or "ainda não"
        self.summary.setText(" · ".join(chips) + f"  <span style='color:{C['dim']}'>— última sincronização: {last}</span>")
        probs = [f"{src}: {msg}" for items in self.hub.problems.values() for src, msg in items]
        self.problems.setText("⚠ " + "\n⚠ ".join(probs[:6]) if probs else "")
        self.problems.setVisible(bool(probs))
        items, total = reg.query(self.search.text(), self.f_provider.currentData() or "", self.f_kind.currentData() or "",
                                 self.f_status.currentData() or "", self.f_project.currentData() or "", limit=PAGE)
        self._shown = items
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(items))
        for r, e in enumerate(items):
            who = {"claude": "Miwa", "codex": "Kaguya", "web": "web"}.get(e.provider, e.provider)
            name = ("   ↳ " if e.parent else "") + e.name
            self.table.setItem(r, 0, _item(name, data=e.id))
            self.table.setItem(r, 1, _item(KINDS.get(e.kind, e.kind)))
            self.table.setItem(r, 2, _item(who, AGENT.get(e.provider, {}).get("color")))
            self.table.setItem(r, 3, _item(e.scope + (f" · {e.project.split('/')[-1].split(chr(92))[-1]}" if e.project else "")))
            self.table.setItem(r, 4, _item(e.version or "—", C["dim"]))
            self.table.setItem(r, 5, _item(LABELS.get(e.state, e.state), STATE_COLOR.get(e.state)))
            flag = next((f for f in e.flags if f in BAD), "")
            self.table.setItem(r, 6, _item(", ".join(LABELS.get(f, f) for f in e.flags), BAD.get(flag)))
        self.table.setUpdatesEnabled(True)
        self.table.resizeColumnsToContents()
        self.more.setText(f"Mostrando {len(items)} de {total}" + (" — refine a busca para ver o resto" if total > len(items)
                                                                   else ""))
        if not items:
            self.detail.setHtml(f"<p style='color:{C['muted']}'>Nada encontrado com esses filtros.</p>")

    def selected(self):
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return None
        ext_id = self.table.item(rows[0].row(), 0).data(Qt.UserRole)
        return self.hub.registry.get(ext_id)

    def show_detail(self):
        e = self.selected()
        if e is None:
            return
        reg = self.hub.registry
        esc = html.escape
        kids = [k for k in reg.all() if k.parent == e.name and k.provider == e.provider]
        rows = [("IA", PROVIDERS.get(e.provider, e.provider)), ("Tipo", KINDS.get(e.kind, e.kind)), ("Escopo", e.scope),
                ("Projeto", e.project or "—"), ("Versão", e.version or "—"), ("Origem", e.source),
                ("Vem do plugin", e.parent or "—"), ("Transporte", e.transport or "—"),
                ("Comando (segredos ocultos)", e.command or "—"),
                ("Variáveis (só nomes)", ", ".join(e.env_keys) or "—"),
                ("Permissões", "; ".join(e.permissions) or "—"), ("Custo", e.details.get("custo", "—")),
                ("Evidência", e.evidence or "—"), ("Última verificação", e.last_verified or "nunca")]
        real_session = "sessão real" in (e.evidence or "")

        def step(s):
            reached = STATES.index(s) <= e.level()
            note = " (pelo teste oficial, não por uma sessão)" if (s == "carregado_na_sessao" and reached
                                                                      and not real_session) else ""
            color = STATE_COLOR.get(s, C["dim"]) if reached else C["dim"]
            return f"<span style='color:{color}'>{'●' if reached else '○'} {LABELS[s]}{note}</span><br>"
        states = "".join(step(s) for s in STATES)
        flags = " ".join(f"<span style='color:{BAD.get(f, C['muted'])}'>⚠ {LABELS.get(f, f)}</span>" for f in e.flags)
        hist = reg.history(e.id, 8)
        parts = [f"<h3>{esc(e.name)}</h3>", f"<p>{esc(e.description)}</p>" if e.description else "",
                 f"<p>{states}</p>", f"<p>{flags}</p>" if flags else "",
                 "<table>" + "".join(f"<tr><td style='color:{C['muted']};padding-right:8px'>{esc(k)}</td>"
                                     f"<td>{esc(str(v))}</td></tr>" for k, v in rows) + "</table>"]
        if e.tools:
            parts.append("<p><b>Ferramentas:</b> " + esc(", ".join(e.tools[:60])) + "</p>")
        if kids:
            parts.append("<p><b>Componentes deste plugin:</b> " + esc(", ".join(f"{KINDS.get(k.kind, k.kind)} {k.name}"
                                                                                for k in kids)) + "</p>")
        if e.kind in ("skill", "agent", "command") and e.description and any(
                w in e.description.lower() for w in ("ignore all", "ignore as instru", "rm -rf", "system prompt")):
            parts.append(f"<p style='color:{C['warning']}'>⚠ A descrição contém texto que parece dar ordens a IAs. "
                         "É só texto do arquivo: o Studio não obedece nem executa.</p>")
        if hist:
            parts.append("<p><b>Histórico</b><br>" + "<br>".join(
                f"{esc(h['ts'][5:16].replace('T', ' '))} {esc(h['event'])}: {esc(h['old_status'] or '')} → "
                f"{esc(h['new_status'] or '')} {esc(('— ' + h['summary']) if h['summary'] else '')}" for h in hist) + "</p>")
        self.detail.setHtml("".join(parts))
        removed = "removido" in e.flags
        self.test_btn.setEnabled(not removed and e.provider != "web")
        self.tools_btn.setVisible(e.kind == "mcp" and e.transport == "stdio")
        self.toggle_btn.setVisible(e.kind == "plugin" and e.provider == "claude" and not removed)
        self.toggle_btn.setText("Ativar" if "desabilitado" in e.flags else "Desativar")
        self.remove_btn.setVisible(not removed and (e.kind == "plugin" or (e.kind == "mcp" and not e.parent))
                                   and e.provider in ("claude", "codex") and e.scope != "builtin")

    # ------------------------------------------------------------------ actions
    def test_selected(self, list_tools: bool, done=None):
        e = self.selected()
        if e is None:
            return
        if list_tools and QMessageBox.question(
                self, "Listar ferramentas", f"Iniciar “{e.name}” só para perguntar quais ferramentas ele tem?\n\n"
                "Ele roda no seu PC com a configuração do próprio cliente; nenhuma ferramenta é executada.") != \
                QMessageBox.Yes:
            return
        from ..hub.probe import Prober
        prober = Prober(self.hub.registry, lambda: self.hub.exes() or {})
        self.test_btn.setEnabled(False)

        def finish(res):
            self.test_btn.setEnabled(True)
            self.win.toast(("✓ " if res.get("ok") else "✗ ") + res.get("evidence", "")[:180], 6000)
            self.refresh_table()
            self._select(e.id)
            if done:
                done(res)
        run_bg(lambda: prober.test(e.id, list_tools=list_tools), finish,
               lambda exc, tb: finish({"ok": False, "evidence": str(exc)}))

    def _select(self, ext_id: str):
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).data(Qt.UserRole) == ext_id:
                self.table.selectRow(r)
                return

    def open_source(self):
        e = self.selected()
        if e is None:
            return
        from pathlib import Path
        p = Path(e.source)
        if p.exists():
            open_path(str(p if p.is_dir() else p.parent))
        else:
            self.win.toast("A origem não é um arquivo (lista oficial do cliente).")

    def _lifecycle(self):
        from ..hub.lifecycle import Lifecycle
        return Lifecycle(self.hub.registry, self.win.engine.home, exes=lambda: self.hub.exes() or {},
                         rescan=self.hub.scan)

    def run_plan(self, plan, dialog=None, done=None):
        """Show the plan; only an explicit approval runs the official command."""
        dlg = (dialog or PlanDialog)(self, plan)
        if not dlg.exec():
            plan.status = "recusada"
            return None
        lc = self._lifecycle()
        aid = lc.approve(plan, reviewed=dlg.reviewed.isChecked())

        def finish(p):
            self.refresh_table()
            ok = p.status == "executada"
            self.win.toast(("✓ Feito: " if ok else "✗ Não deu certo: ") + (p.result or p.display)[:200], 7000)
            if done:
                done(p)
        run_bg(lambda: lc.apply(plan, aid), finish, lambda exc, tb: self.win.toast(f"Falhou: {exc}"))
        return aid

    def request_install(self, values: dict | None = None, dialog=None, done=None):
        if values is None:
            d = InstallDialog(self, [p for p in self.win.store.projects() if not p.get("removed")])
            if not d.exec():
                return None
            values = d.values()
        try:
            plan = self._lifecycle().plan_install_mcp(values["provider"], values["name"], values["scope"],
                                                      project=values.get("project", ""), command=values.get("command", ""),
                                                      args=values.get("args"), url=values.get("url", ""),
                                                      env=values.get("env"), origin=values.get("origin", ""))
        except (ValueError, RuntimeError) as exc:
            QMessageBox.information(self, "Instalação", str(exc))
            return None
        self.run_plan(plan, dialog, done)
        return plan

    def remove_selected(self, dialog=None, done=None):
        e = self.selected()
        if e is None:
            return None
        try:
            plan = self._lifecycle().plan_remove(e.id)
        except (ValueError, RuntimeError) as exc:
            QMessageBox.information(self, "Remover", str(exc))
            return None
        self.run_plan(plan, dialog, done)
        return plan

    def toggle_selected(self, dialog=None, done=None):
        e = self.selected()
        if e is None:
            return None
        try:
            plan = self._lifecycle().plan_toggle_plugin(e.id, enable="desabilitado" in e.flags)
        except (ValueError, RuntimeError) as exc:
            QMessageBox.information(self, "Plugin", str(exc))
            return None
        self.run_plan(plan, dialog, done)
        return plan

    def register_web(self, name: str | None = None, surface: str = "ChatGPT Web", note: str = ""):
        from PySide6.QtWidgets import QInputDialog
        from ..hub.adapters import web_only
        if name is None:
            name, ok = QInputDialog.getText(self, "Plugin só da web",
                                            "Nome do plugin/conector que você usa no ChatGPT ou no Claude web:")
            if not ok or not name.strip():
                return
            surface, ok = QInputDialog.getItem(self, "Plugin só da web", "Onde ele existe?",
                                               ["ChatGPT Web", "Claude.ai (web/app)"], 0, False)
            if not ok:
                return
        self.hub.registry.add_manual(web_only(name.strip(), surface, note))
        self.refresh_table()
        self.win.toast(f"“{name}” registrado como só da web: o Studio e as CLIs não usam a conexão da conta web.")

    def show_log(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Histórico do Hub")
        dlg.resize(760, 520)
        lay = QVBoxLayout(dlg)
        lst = QListWidget()
        for h in self.hub.registry.log(400):
            lst.addItem(f"{h['ts'].replace('T', ' ')}  [{h['actor']}] {h['event']}  {h['extension_id']}  "
                        f"{h['old_status'] or ''} → {h['new_status'] or ''}  {h['summary'] or ''}")
        lay.addWidget(lst, 1)
        clear = button("Limpar histórico", "trash", "ghost", "Apaga o histórico e os itens removidos (o catálogo atual fica)")

        def do_clear():
            if QMessageBox.question(dlg, "Histórico", "Apagar o histórico do Hub?") == QMessageBox.Yes:
                self.hub.registry.clear_history()
                lst.clear()
        clear.clicked.connect(do_clear)
        lay.addWidget(clear)
        dlg.exec()
