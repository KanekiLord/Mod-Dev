"""Queue, Second Brain (Obsidian) and Agents/Skills pages."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QGridLayout, QHBoxLayout, QHeaderView, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QProgressBar, QScrollArea, QSplitter, QTableWidget,
                               QTableWidgetItem, QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from ..orchestrator import worktree
from ..vault.todo import proposal_markdown, read_todo
from . import theme
from .common import obsidian_uri, open_path, open_url, run_bg
from .dialogs import PathField, TextDialog
from .theme import AGENT, C
from .widgets import Card, EmptyState, Pill, button, icon_label, label

STATUS = {"queued": ("na fila", C["info"]), "running": ("executando", C["violet"]), "parked": ("guardada", C["gold"]),
          "approved": ("aprovada", C["success"]), "rejected": ("reprovada", C["danger"]),
          "pending_review": ("revisar", C["warning"]), "executed": ("concluída (validar)", C["success"]),
          "error": ("erro", C["danger"]), "cancelled": ("cancelada", C["dim"]), "interrupted": ("interrompida", C["warning"]),
          "blocked_limit": ("limite atingido", C["danger"]), "done": ("feita", C["success"])}
KIND = {"execute": "executar", "later": "DEPOIS", "idea": "IDEIA"}


def page_title(icon: str, title: str, subtitle: str) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(2, 0, 2, 4)
    lay.addWidget(icon_label(icon, C["gold"], 22))
    col = QVBoxLayout()
    col.setSpacing(0)
    col.addWidget(label(title, "h1"))
    col.addWidget(label(subtitle, "muted", wrap=True))
    lay.addLayout(col, 1)
    return w


def scroll(widget: QWidget) -> QScrollArea:
    s = QScrollArea()
    s.setWidgetResizable(True)
    s.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    s.setWidget(widget)
    return s


def item(text: str, color: str | None = None, data=None) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    if color:
        it.setForeground(QColor(color))
    if data is not None:
        it.setData(Qt.UserRole, data)
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    return it


def table(headers: list[str], stretch: int = -1) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setAlternatingRowColors(True)
    t.setShowGrid(False)
    t.setWordWrap(False)
    h = t.horizontalHeader()
    h.setHighlightSections(False)
    for i in range(len(headers)):
        h.setSectionResizeMode(i, QHeaderView.Stretch if i == (stretch if stretch >= 0 else len(headers) - 1)
                               else QHeaderView.ResizeToContents)
    t.verticalHeader().setDefaultSectionSize(34)
    return t


class QueuePage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(page_title("queue", "Fila de tarefas", "Tarefas DEPOIS e IDEIA ficam guardadas e só executam quando você mandar. "
                                 "Tudo persiste entre reinícios."))
        bar = QHBoxLayout()
        self.b_run = button("Executar agora", "play", "primary", "Ativa uma tarefa DEPOIS/IDEIA com as permissões do compositor")
        self.b_retry = button("Reenfileirar", "refresh", tip="Coloca de novo na fila uma tarefa interrompida/com erro")
        self.b_cancel = button("Cancelar", "x", "ghost")
        self.b_details = button("Detalhes e logs", "file")
        self.b_undo = button("Desfazer", "refresh", "ghost", "Volta os arquivos do projeto ao estado de antes desta tarefa "
                             "(ponto de restauração do modo autônomo)")
        self.b_todo = button("Copiar para todo.md", "book", "ghost", "Copia as tarefas guardadas no formato de checklist "
                             "(você cola no tasks/todo.md; o Studio não edita esse arquivo)")
        for b in (self.b_run, self.b_retry, self.b_cancel, self.b_details, self.b_undo, self.b_todo):
            bar.addWidget(b)
        bar.addStretch(1)
        refresh = button("", "refresh", "ghost", "Atualizar")
        refresh.clicked.connect(self.refresh)
        bar.addWidget(refresh)
        lay.addLayout(bar)
        self.table = table(["#", "Destino", "Tipo", "Situação", "Etapa", "Tarefa", "Criada"], stretch=5)
        self.table.itemSelectionChanged.connect(self._sel)
        self.table.doubleClicked.connect(self.details)
        lay.addWidget(self.table, 1)
        self.integrate = Card(accent=C["gold"])
        self.integrate.lay.addWidget(label("INTEGRAÇÃO SUPERVISIONADA (MODO PARALELO)", "section"))
        self.int_info = label("", "muted", wrap=True)
        self.integrate.lay.addWidget(self.int_info)
        self.int_row = QHBoxLayout()
        self.integrate.lay.addLayout(self.int_row)
        self.integrate.hide()
        lay.addWidget(self.integrate)
        self.b_run.clicked.connect(self.activate)
        self.b_retry.clicked.connect(self.retry)
        self.b_cancel.clicked.connect(self.cancel)
        self.b_details.clicked.connect(self.details)
        self.b_undo.clicked.connect(self.undo)
        self.b_todo.clicked.connect(self.copy_todo)
        self._sel()

    def selected(self) -> dict | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        tid = self.table.item(rows[0].row(), 0).data(Qt.UserRole)
        try:
            return self.win.store.get_task(tid)
        except ValueError:
            return None

    def _sel(self):
        t = self.selected()
        self.b_run.setEnabled(bool(t and t["status"] == "parked"))
        self.b_retry.setEnabled(bool(t and t["status"] in ("interrupted", "error", "cancelled", "blocked_limit")))
        self.b_cancel.setEnabled(bool(t and t["status"] in ("queued", "parked")))
        self.b_details.setEnabled(bool(t))
        self.b_undo.setEnabled(bool(t and t.get("checkpoint") and t["status"] != "running"))
        self._show_integration(t)

    def refresh(self):
        pid = self.win.pid
        self.table.setRowCount(0)
        if pid is None:
            return
        for t in self.win.store.tasks(pid):
            r = self.table.rowCount()
            self.table.insertRow(r)
            st, col = STATUS.get(t["status"], (t["status"], C["muted"]))
            a = AGENT.get(t["target"], AGENT["equipe"])
            self.table.setItem(r, 0, item(str(t["id"]), C["dim"], t["id"]))
            dest = item(a["name"], a["color"])
            dest.setIcon(theme.icon(a["icon"], a["color"]))
            self.table.setItem(r, 1, dest)
            self.table.setItem(r, 2, item(KIND.get(t["kind"], t["kind"]), C["gold"] if t["kind"] != "execute" else C["muted"]))
            self.table.setItem(r, 3, item("● " + st, col))
            self.table.setItem(r, 4, item(t.get("stage") or "", C["muted"]))
            title = item(t["title"].replace("\n", " ")[:200])
            title.setToolTip(t["title"][:2000])
            self.table.setItem(r, 5, title)
            self.table.setItem(r, 6, item((t["created_at"] or "")[5:16].replace("T", " "), C["dim"]))
        self._sel()

    def activate(self):
        t = self.selected()
        if not t:
            return
        perms = self.win.chat.composer.permissions()
        if perms["write"] and not perms["autonomous"] and not self.win.confirm_write():
            return
        self.win.store.activate_later(t["id"], allow_write=perms["write"], allow_web=perms["web"],
                                      allow_commands=perms["commands"], allow_mcp=perms["mcp"], run_tests=perms["run_tests"],
                                      autonomous=perms["autonomous"])
        self.win.engine.start_worker(self.win.pid)
        self.refresh()

    def undo(self, *, confirm: bool = True):
        t = self.selected()
        if not t or not t.get("checkpoint"):
            return
        try:
            files = self.win.engine.task_changes(t["id"])
        except Exception as exc:
            QMessageBox.warning(self, "Desfazer", str(exc))
            return
        lst = "\n".join(files[:25]) + (f"\n… e mais {len(files) - 25}" if len(files) > 25 else "")
        if confirm and QMessageBox.question(
                self, "Desfazer tarefa?", f"Voltar o projeto ao estado de antes da tarefa #{t['id']}?\n\n"
                + (f"{len(files)} arquivo(s) mudaram desde então (inclui mudanças suas feitas depois):\n{lst}"
                   if files else "Nenhum arquivo mudou desde o ponto de restauração.")) != QMessageBox.Yes:
            return
        try:
            changed = self.win.engine.undo_task(t["id"])
        except Exception as exc:
            QMessageBox.warning(self, "Desfazer", str(exc))
            return
        self.win.toast(f"Tarefa #{t['id']} desfeita: {len(changed)} arquivo(s) restaurado(s).")
        self.refresh()

    def retry(self):
        t = self.selected()
        if t and self.win.store.requeue(t["id"]):
            self.win.engine.start_worker(self.win.pid)
            self.refresh()

    def cancel(self):
        t = self.selected()
        if t:
            self.win.store.cancel_queued(t["id"])
            self.refresh()

    def details(self, *_):
        t = self.selected()
        if not t:
            return
        evs = self.win.store.events(t["id"])
        lines = [f"Tarefa #{t['id']} • {t['target']} • {t['status']} • etapa {t.get('stage') or '-'}",
                 f"Permissões: escrita={bool(t['allow_write'])} comandos={bool(t['allow_commands'])} web={bool(t['allow_web'])} "
                 f"mcp={bool(t['allow_mcp'])} testes={bool(t['run_tests'])}", "", t["title"], "", "— Eventos —"]
        lines += [f"[{e['moment'][11:19]}] {e['agent'] or '-'} {e['kind']}: {e['message'][:3000]}" for e in evs]
        lines += ["", "— Resultado —", t.get("result") or ""]
        logs = self.win.engine.home / "logs" / f"projeto-{t['project_id']}" / f"tarefa-{t['id']}"
        lines += ["", f"Logs completos (higienizados): {logs}"]
        TextDialog(f"Tarefa #{t['id']}", "\n".join(lines), self).exec()

    def copy_todo(self):
        pid = self.win.pid
        if pid is None:
            return
        parked = [t for t in self.win.store.tasks(pid) if t["status"] == "parked"]
        if not parked:
            QMessageBox.information(self, "todo.md", "Não há tarefas guardadas (DEPOIS/IDEIA).")
            return
        QGuiApplication.clipboard().setText(proposal_markdown(parked))
        QMessageBox.information(self, "todo.md", f"{len(parked)} linha(s) copiadas no formato de checklist.\n"
                                "Cole em tasks/todo.md no Obsidian. O Studio não altera esse arquivo sozinho.")

    def _show_integration(self, t):
        while self.int_row.count():
            w = self.int_row.takeAt(0).widget()
            if w:
                w.deleteLater()
        if not t or t["target"] != "paralelo":
            self.integrate.hide()
            return
        evs = [e for e in self.win.store.events(t["id"]) if e["kind"] == "worktree"]
        if not evs:
            self.integrate.hide()
            return
        self.integrate.show()
        infos = [json.loads(e["message"]) for e in evs]
        self.int_info.setText("Cada IA trabalhou em um ramo isolado. Veja o diff e integre um por vez; conflitos abortam a "
                              "integração sem alterar nada.")
        root = Path(self.win.store.project(t["project_id"])["directory"])
        from ..paths import git_root
        groot = git_root(root)
        for info in infos:
            if not info.get("branch"):
                continue
            b = button(f"Diff {info['agent']}", "eye", tip=info["branch"])
            b.clicked.connect(lambda _=False, br=info["branch"]: TextDialog(br, worktree.diff(Path(groot), br) or "(sem alterações)", self).exec())
            m = button(f"Integrar {info['agent']}", "git", "primary" if info.get("ok") else None)
            m.setEnabled(bool(info.get("committed")))
            m.clicked.connect(lambda _=False, br=info["branch"]: self._merge(groot, br))
            self.int_row.addWidget(b)
            self.int_row.addWidget(m)
        self.int_row.addStretch(1)

    def _merge(self, root, branch):
        if QMessageBox.question(self, "Integrar ramo", f"Integrar {branch} no ramo atual do projeto?\n"
                                "É feito um merge --no-ff; em caso de conflito nada é alterado.") != QMessageBox.Yes:
            return
        ok, msg = worktree.integrate(Path(root), branch)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Integração", msg)


class MemoryPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page_title("brain", "Segundo Cérebro", "Vault do Obsidian conectado de forma independente dos "
                                   "projetos. Leitura e índice ficam fora do vault; notas novas só entram após sua aprovação."))
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 6, 0)
        lay.setSpacing(12)
        # ---- link card
        link = Card(accent=C["violet"], pattern=True)
        link.lay.addWidget(label("VAULT GLOBAL", "section"))
        self.path = PathField("vault", "Escolha a pasta raiz do vault do Obsidian", win.store.global_vault() or "")
        link.lay.addWidget(self.path)
        row = QHBoxLayout()
        save = button("Salvar vault global", "check", "primary")
        save.clicked.connect(self.save_vault)
        disc = button("Desconectar", "x", "ghost")
        disc.clicked.connect(self.disconnect)
        openb = button("Abrir pasta", "folder-open", "ghost")
        openb.clicked.connect(lambda: open_path(self.win.store.global_vault() or ""))
        row.addWidget(save)
        row.addWidget(disc)
        row.addWidget(openb)
        row.addStretch(1)
        self.proj_vault = label("", "muted", wrap=True)
        link.lay.addLayout(row)
        link.lay.addWidget(self.proj_vault)
        lay.addWidget(link)
        # ---- index card
        idx = Card()
        head = QHBoxLayout()
        head.addWidget(label("ÍNDICE DE BUSCA", "section"))
        head.addStretch(1)
        self.b_index = button("Indexar / atualizar", "refresh")
        self.b_index.clicked.connect(self.reindex)
        head.addWidget(self.b_index)
        idx.lay.addLayout(head)
        self.idx_info = label("", "muted", wrap=True)
        idx.lay.addWidget(self.idx_info)
        self.progress = QProgressBar()
        self.progress.setFixedHeight(8)
        self.progress.hide()
        idx.lay.addWidget(self.progress)
        srow = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("Buscar nas notas (ex.: photon shader blockbench)")
        self.query.returnPressed.connect(self.search)
        sb = button("Buscar", "search", "primary")
        sb.clicked.connect(self.search)
        srow.addWidget(self.query, 1)
        srow.addWidget(sb)
        idx.lay.addLayout(srow)
        self.results = QListWidget()
        self.results.setMinimumHeight(220)
        self.results.itemDoubleClicked.connect(self.open_hit)
        self.results.addItem("Digite um termo e pressione Enter. Duplo clique abre a nota no Obsidian.")
        idx.lay.addWidget(self.results)
        lay.addWidget(idx)
        # ---- outbox + todo tabs
        tabs = QTabWidget()
        out = QWidget()
        ol = QVBoxLayout(out)
        ol.setContentsMargins(0, 8, 0, 0)
        orow = QHBoxLayout()
        ok = button("Aprovar selecionadas", "check", "primary")
        ok.clicked.connect(self.approve)
        dis = button("Descartar", "trash", "ghost")
        dis.clicked.connect(self.discard)
        orow.addWidget(label("Notas novas são criadas sem sobrescrever nenhum arquivo existente.", "muted"))
        orow.addStretch(1)
        orow.addWidget(dis)
        orow.addWidget(ok)
        ol.addLayout(orow)
        split = QSplitter()
        self.drafts = QListWidget()
        self.drafts.currentItemChanged.connect(self.preview)
        self.draft_view = QTextBrowser()
        split.addWidget(self.drafts)
        split.addWidget(self.draft_view)
        split.setSizes([300, 500])
        ol.addWidget(split, 1)
        tabs.addTab(out, theme.icon("inbox", C["muted"]), "Rascunhos para aprovar")
        todo = QWidget()
        tl = QVBoxLayout(todo)
        tl.setContentsMargins(0, 8, 0, 0)
        self.todo_info = label("", "muted", wrap=True)
        tl.addWidget(self.todo_info)
        self.todo_list = QListWidget()
        tl.addWidget(self.todo_list, 1)
        tabs.addTab(todo, theme.icon("book", C["muted"]), "tasks/todo.md (leitura)")
        tabs.setMinimumHeight(330)
        lay.addWidget(tabs)
        outer.addWidget(scroll(content), 1)

    def vault(self) -> str | None:
        return self.win.store.effective_vault(self.win.pid)

    def refresh(self):
        gv = self.win.store.global_vault()
        if gv and self.path.edit.text().strip() != gv:
            self.path.edit.setText(gv)
        pv = None
        if self.win.pid is not None:
            p = self.win.store.project(self.win.pid)
            pv = p.get("vault")
            self.proj_vault.setText(f"Projeto atual usa: {pv} (vault próprio)" if pv else
                                    "Projeto atual usa o vault global." if gv else "Nenhum vault vinculado ainda.")
        idx = self.win.engine.vault_index(self.vault())
        if idx:
            st = idx.stats()
            when = datetime.fromtimestamp(st["updated"]).strftime("%d/%m %H:%M") if st["updated"] else "nunca"
            self.idx_info.setText(f"{st['notes']} notas indexadas • {st['links']} link(s) • atualizado: {when}"
                                  + ("" if st["fts"] else " • (busca simples: FTS5 indisponível)"))
        else:
            self.idx_info.setText("Vincule um vault para indexar.")
        self.load_drafts()
        self.load_todo()

    def save_vault(self):
        if not (self.path.result and self.path.result.ok):
            QMessageBox.warning(self, "Vault", "Verifique o caminho do vault (veja as mensagens abaixo do campo).")
            return
        self.win.store.set_global_vault(self.path.value())
        self.win.refresh_all()
        self.reindex()

    def disconnect(self):
        if QMessageBox.question(self, "Desconectar", "Desconectar o vault global? Nenhuma nota será apagada.") == QMessageBox.Yes:
            self.win.store.set_global_vault(None)
            self.path.edit.clear()
            self.win.refresh_all()

    def reindex(self):
        idx = self.win.engine.vault_index(self.vault())
        if not idx:
            return
        self.b_index.setEnabled(False)
        self.progress.show()
        self.progress.setValue(0)

        def prog(n, total, rel):
            self.win.bridge.call.emit(lambda: (self.progress.setMaximum(max(total, 1)), self.progress.setValue(n)))

        def done(res):
            self.b_index.setEnabled(True)
            self.progress.hide()
            self.refresh()
            self.win.toast(f"Índice atualizado: {res['changed']} nota(s) lidas em {res['seconds']}s.")

        def fail(exc, tb):
            self.b_index.setEnabled(True)
            self.progress.hide()
            QMessageBox.warning(self, "Índice", f"Falha ao indexar: {exc}")
        run_bg(lambda: idx.update(prog), done, fail)

    def search(self):
        idx = self.win.engine.vault_index(self.vault())
        self.results.clear()
        if not idx:
            self.results.addItem("Vincule um vault primeiro.")
            return
        if idx.stats()["notes"] == 0:
            idx.update()
        hits = idx.search(self.query.text(), limit=15)
        if not hits:
            self.results.addItem("Nenhuma nota encontrada para esse termo.")
        for h in hits:
            it = QListWidgetItem(theme.icon("file", C["violet"]), f"{h.title}   —   {h.path}\n{h.excerpt[:240]}")
            it.setData(Qt.UserRole, h.path)
            it.setToolTip("Duplo clique abre no Obsidian")
            self.results.addItem(it)

    def open_hit(self, it):
        rel = it.data(Qt.UserRole)
        vault = self.vault()
        if rel and vault and not open_url(obsidian_uri(vault, rel)):
            open_path(str(Path(vault) / rel))

    def load_drafts(self):
        self.drafts.clear()
        ob = self.win.engine.outbox(self.win.pid) if self.win.pid is not None else None
        if not ob:
            self.draft_view.setPlainText("Vincule um vault para revisar rascunhos.")
            return
        for d in ob.drafts():
            warn = "  ⚠ título parecido já existe" if d["similar"] else ""
            it = QListWidgetItem(f"[{d['kind']}] {d['title']}{warn}")
            it.setData(Qt.UserRole, d)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            self.drafts.addItem(it)
        if not self.drafts.count():
            self.draft_view.setPlainText("Nenhum rascunho pendente.")

    def preview(self, cur, _prev=None):
        if not cur:
            return
        d = cur.data(Qt.UserRole)
        extra = ("\n\n---\n⚠ Notas parecidas: " + ", ".join(d["similar"])) if d["similar"] else ""
        self.draft_view.setMarkdown(f"**Destino:** `{d['relative']}`\n\n" + d["body"] + extra)

    def _checked(self) -> list[str]:
        return [self.drafts.item(i).data(Qt.UserRole)["filename"] for i in range(self.drafts.count())
                if self.drafts.item(i).checkState() == Qt.Checked]

    def approve(self):
        names = self._checked()
        ob = self.win.engine.outbox(self.win.pid)
        if not names or not ob:
            QMessageBox.information(self, "Rascunhos", "Marque os rascunhos que deseja criar no vault.")
            return
        done = ob.approve(names)
        self.win.toast(f"{len(done)} nota(s) criadas no vault (nenhuma sobrescrita).")
        self.refresh()

    def discard(self):
        ob = self.win.engine.outbox(self.win.pid)
        for n in self._checked():
            ob.discard(n)
        self.refresh()

    def load_todo(self):
        self.todo_list.clear()
        v = self.vault()
        if not v:
            self.todo_info.setText("Sem vault.")
            return
        path, items = read_todo(Path(v))
        if not path:
            self.todo_info.setText("tasks/todo.md não encontrado neste vault.")
            return
        openn = sum(1 for i in items if not i.done)
        self.todo_info.setText(f"{path} • {len(items)} itens ({openn} abertos). Somente leitura: o formato real será "
                               "confirmado antes de qualquer sincronização.")
        for i in items:
            mark = {"feito": "☑", "em andamento": "◐", "cancelado": "☒"}.get(i.state, "☐")
            it = QListWidgetItem(f"{'   ' * (i.indent // 2)}{mark} {i.text}" + (f"   · {i.section}" if i.section else ""))
            if i.done:
                it.setForeground(QColor(C["dim"]))
            self.todo_list.addItem(it)


class AgentsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(page_title("agents", "Agentes, skills e MCPs", "Inventário somente leitura do que está realmente "
                                 "instalado, conciliado com o catálogo dos 72 agentes. Nada é instalado ou alterado."))
        self.summary = QHBoxLayout()
        lay.addLayout(self.summary)
        bar = QHBoxLayout()
        b = button("Atualizar inventário", "refresh")
        b.clicked.connect(lambda: self.refresh(True))
        bar.addStretch(1)
        bar.addWidget(b)
        lay.addLayout(bar)
        self.tabs = QTabWidget()
        self.t_agents = table(["Agente", "Escopo", "Modelo", "Projeto (catálogo)", "Grupo", "Descrição"], stretch=5)
        self.t_skills = table(["Skill", "Escopo", "Descrição"], stretch=2)
        self.t_other = table(["Tipo", "Nome", "Escopo"], stretch=1)
        self.t_missing = table(["Agente do catálogo não encontrado", "Projeto", "Grupo", "Função"], stretch=3)
        self.tabs.addTab(self.t_agents, "Agentes instalados")
        self.tabs.addTab(self.t_skills, "Skills")
        self.tabs.addTab(self.t_other, "Plugins, MCPs e instruções")
        self.tabs.addTab(self.t_missing, "Catálogo não encontrado")
        lay.addWidget(self.tabs, 1)

    def refresh(self, force: bool = False):
        if self.win.pid is None:
            return
        while self.summary.count():
            w = self.summary.takeAt(0).widget()
            if w:
                w.deleteLater()

        def done(inv):
            for text, color in ((f"{len(inv.agents)} agentes instalados", C["violet"]),
                                (f"{len(inv.catalog_found)}/{inv.catalog_total} do catálogo encontrados", C["success"]),
                                (f"{len(inv.catalog_missing)} do catálogo ausentes", C["warning"]),
                                (f"{len(inv.skills)} skills", C["gold"]), (f"{len(inv.mcp_servers)} MCPs", C["info"])):
                self.summary.addWidget(Pill(text, color))
            self.summary.addStretch(1)
            self._fill(inv)
        run_bg(lambda: self.win.engine.inventory(self.win.pid, refresh=force), done)

    def _fill(self, inv):
        from ..inventory import load_catalog
        from ..appdirs import CATALOG
        for t in (self.t_agents, self.t_skills, self.t_other, self.t_missing):
            t.setRowCount(0)
        for a in inv.agents:
            r = self.t_agents.rowCount()
            self.t_agents.insertRow(r)
            for c, (v, col) in enumerate(((a.name, C["text"]), (a.scope, C["muted"]), (a.model or "padrão", C["gold"]),
                                          (a.catalog_project or "fora do catálogo", C["muted"]), (a.catalog_group, C["dim"]),
                                          (a.description, C["muted"]))):
                it = item(v, col)
                if c == 0:
                    it.setToolTip(a.path)
                self.t_agents.setItem(r, c, it)
        for s in inv.skills:
            r = self.t_skills.rowCount()
            self.t_skills.insertRow(r)
            for c, v in enumerate((s["name"], s["scope"], s["description"])):
                self.t_skills.setItem(r, c, item(v))
        rows = [("Plugin", p, "global") for p in inv.plugins] + [("MCP", m["name"], m["scope"]) for m in inv.mcp_servers] + \
               [("Instruções", i, "") for i in inv.instructions]
        for kind, name, scope in rows:
            r = self.t_other.rowCount()
            self.t_other.insertRow(r)
            for c, v in enumerate((kind, name, scope)):
                self.t_other.setItem(r, c, item(v))
        cat = {c["nome"]: c for c in load_catalog(CATALOG)}
        for n in inv.catalog_missing:
            c = cat.get(n, {})
            r = self.t_missing.rowCount()
            self.t_missing.insertRow(r)
            for col, v in enumerate((n, c.get("projeto", ""), c.get("grupo", ""), c.get("funcao", ""))):
                self.t_missing.setItem(r, col, item(v, C["dim"] if col else C["warning"]))
        if not inv.agents:
            self.tabs.setTabText(0, "Agentes instalados (nenhum encontrado)")
        else:
            self.tabs.setTabText(0, f"Agentes instalados ({len(inv.agents)})")
