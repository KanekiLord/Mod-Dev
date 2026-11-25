"""Início: a dashboard with *real* state only (projects, assistants, queue, Second Brain, active modes).

Numbers come from the store, the engine and the official limit readers; anything unknown is shown as such.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from .. import persona
from .page_work import scroll
from .theme import AGENT, C
from .widgets import Card, Dot, Pill, SpriteView, button, label

STATE_COLOR = {"ready": C["success"], "error": C["danger"]}


def _stat(value: str, caption: str, color: str = C["text"]) -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    v = label(value)
    v.setStyleSheet(f"font-size: 18pt; font-weight: 700; color: {color};")
    lay.addWidget(v)
    lay.addWidget(label(caption, "dim"))
    w.value_label = v
    return w


class HomePage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(12)
        # greeting
        hero = Card(accent=C["gold"])
        hrow = QHBoxLayout()
        self.sprites = {}
        for a in ("codex", "claude"):
            sp = SpriteView(AGENT[a]["color"], aura=False)
            sp.setFixedSize(92, 92)
            self.sprites[a] = sp
            hrow.addWidget(sp)
        col = QVBoxLayout()
        self.hello = label("", "h1")
        self.subtitle = label("", "muted", wrap=True)
        self.subtitle.setMinimumWidth(10)
        col.addWidget(self.hello)
        col.addWidget(self.subtitle)
        quick = QGridLayout()
        quick.setHorizontalSpacing(6)
        quick.setVerticalSpacing(4)
        for i, (text, icon, fn, tip) in enumerate((
                ("Conversar", "chat", lambda: win.go("chat"), "Abrir a conversa"),
                ("Modo Live", "wave", lambda: win.start_live(None), "Conversa por voz contínua"),
                ("Chamar pelo nome", "mic", lambda: win.set_wake(not win.wake.running), "Liga/desliga a escuta por nome"),
                ("Meu computador", "window", win.open_pc_mode, "Assistentes fora dos projetos"),
                ("Personalidades", "sparkle", lambda: win.go("persona"), "Jeito de falar, nome, voz"),
                ("ChatGPT e Claude", "globe", lambda: win.go("webchats"), "Chats oficiais com o seu login"))):
            b = button(text, icon, "ghost", tip)
            b.clicked.connect(fn)
            quick.addWidget(b, i // 3, i % 3)
        col.addLayout(quick)
        hrow.addLayout(col, 1)
        hero.lay.addLayout(hrow)
        lay.addWidget(hero)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        # assistants
        self.ai_card = Card()
        self.ai_card.lay.addWidget(label("IAS", "section"))
        self.ai_rows = {}
        for a in ("codex", "claude"):
            row = QHBoxLayout()
            dot = Dot(C["dim"], 9)
            name = label("")
            name.setStyleSheet(f"color: {AGENT[a]['color']}; font-weight: 700;")
            state = label("", "muted")
            limit = Pill("", C["dim"])
            row.addWidget(dot)
            row.addWidget(name)
            row.addWidget(state, 1)
            row.addWidget(limit)
            self.ai_card.lay.addLayout(row)
            self.ai_rows[a] = (dot, name, state, limit)
        self.ai_card.lay.addWidget(label("Limites só da fonte oficial; sem número inventado.", "dim"))
        b = button("Uso e limites", "gauge", "ghost")
        b.clicked.connect(lambda: win.go("usage"))
        self.ai_card.lay.addWidget(b, 0, Qt.AlignLeft)
        # queue
        self.q_card = Card()
        self.q_card.lay.addWidget(label("FILA DE TAREFAS", "section"))
        qrow = QHBoxLayout()
        self.q_stats = {k: _stat("0", t, c) for k, t, c in (("running", "executando", C["violet"]),
                                                            ("queued", "na fila", C["info"]),
                                                            ("parked", "guardadas", C["gold"]),
                                                            ("review", "para revisar", C["warning"]))}
        for w in self.q_stats.values():
            qrow.addWidget(w)
        self.q_card.lay.addLayout(qrow)
        self.q_last = label("", "muted", wrap=True)
        self.q_last.setMinimumWidth(10)
        self.q_card.lay.addWidget(self.q_last)
        b = button("Abrir fila", "queue", "ghost")
        b.clicked.connect(lambda: win.go("queue"))
        self.q_card.lay.addWidget(b, 0, Qt.AlignLeft)
        # projects
        self.p_card = Card()
        self.p_card.lay.addWidget(label("PROJETOS", "section"))
        self.p_list = QVBoxLayout()
        self.p_card.lay.addLayout(self.p_list)
        b = button("Vincular projeto", "folder-plus", "ghost")
        b.clicked.connect(win.add_project)
        self.p_card.lay.addWidget(b, 0, Qt.AlignLeft)
        # second brain
        self.m_card = Card()
        self.m_card.lay.addWidget(label("SEGUNDO CÉREBRO", "section"))
        mrow = QHBoxLayout()
        self.m_stats = {k: _stat("—", t) for k, t in (("notes", "notas indexadas"), ("drafts", "em revisão"))}
        for w in self.m_stats.values():
            mrow.addWidget(w)
        self.m_card.lay.addLayout(mrow)
        self.m_vault = label("", "dim", wrap=True)
        self.m_vault.setMinimumWidth(10)
        self.m_card.lay.addWidget(self.m_vault)
        b = button("Abrir Segundo Cérebro", "brain", "ghost")
        b.clicked.connect(lambda: win.go("memory"))
        self.m_card.lay.addWidget(b, 0, Qt.AlignLeft)
        # modes
        self.mode_card = Card()
        self.mode_card.lay.addWidget(label("MODOS ATIVOS", "section"))
        self.mode_box = QVBoxLayout()
        self.mode_card.lay.addLayout(self.mode_box)
        grid.addWidget(self.ai_card, 0, 0)
        grid.addWidget(self.q_card, 0, 1)
        grid.addWidget(self.p_card, 1, 0)
        grid.addWidget(self.m_card, 1, 1)
        grid.addWidget(self.mode_card, 2, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        lay.addStretch(1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll(content))

    # ------------------------------------------------------------------ data
    def refresh(self):
        win, store = self.win, self.win.store
        p = persona.load(store, "codex")
        who = p.nickname or ""
        hour = datetime.now().hour
        part = "Bom dia" if 5 <= hour < 12 else "Boa tarde" if hour < 18 else "Boa noite"
        self.hello.setText(f"{part}{', ' + who if who else ''}!")
        k, m = AGENT["codex"]["mascot"], AGENT["claude"]["mascot"]
        self.subtitle.setText(f"{k} (Codex) e {m} (Claude Code) estão no seu Studio. Peça algo na conversa, chame pelo "
                              "nome ou deixe ideias para depois.")
        for a, sp in self.sprites.items():
            sp.set_image(win.mascots[a].image())
        # assistants: diagnosis + official limits
        from ..usage import claude_snapshot
        for a, (dot, name, state, limit) in self.ai_rows.items():
            name.setText(f"{AGENT[a]['mascot']} · {AGENT[a]['name']}")
            diag = win.engine.diagnoses.get(a)
            if diag is None:
                dot.set_color(C["dim"], False)
                state.setText("não verificado nesta sessão")
            else:
                from ..cli.discovery import READY, STATE_LABELS
                dot.set_color(C["success"] if diag.state == READY else C["warning"], False)
                state.setText(STATE_LABELS.get(diag.state, diag.state) + (f" · {diag.version}" if diag.version else ""))
            remaining = None
            if a == "claude":
                snap = claude_snapshot(store.latest_usage("claude"))
                if snap.available and snap.windows:
                    remaining = 100 - snap.windows[0].used_percent
            else:
                stored = store.latest_usage("codex")
                if stored and stored["payload"].get("available") and stored["payload"].get("windows"):
                    remaining = 100 - stored["payload"]["windows"][0]["used_percent"]
            limit.set(f"{remaining:.0f}% restante (oficial)" if remaining is not None else "limite: indisponível",
                      C["success"] if remaining is not None else C["dim"])
        # queue across projects
        counts = {"running": 0, "queued": 0, "parked": 0, "review": 0}
        last = None
        projects = store.projects()
        for proj in projects:
            for t in store.tasks(proj["id"], 200):
                if t["status"] == "running":
                    counts["running"] += 1
                elif t["status"] == "queued":
                    counts["queued"] += 1
                elif t["status"] == "parked":
                    counts["parked"] += 1
                elif t["status"] == "pending_review":
                    counts["review"] += 1
                if t.get("finished_at") and (last is None or t["finished_at"] > last[0]):
                    last = (t["finished_at"], t, proj)
        for k2, w in self.q_stats.items():
            w.value_label.setText(str(counts[k2]))
        self.q_last.setText(f"Última concluída: #{last[1]['id']} em {last[2]['name']} — {last[1]['title'][:90]} "
                            f"({last[1]['status']})" if last else "Nenhuma tarefa concluída ainda.")
        # projects
        while self.p_list.count():
            w = self.p_list.takeAt(0).widget()
            if w:
                w.deleteLater()
        pc_id = store.get_setting("pc.project_id")
        shown = [x for x in projects if x["id"] != pc_id][:6]
        for proj in shown:
            b = button(proj["name"] + ("   ●" if win.engine.is_running(proj["id"]) else ""),
                       "sakura" if proj["id"] == win.pid else "folder", "ghost", proj["directory"])
            b.clicked.connect(lambda _=False, i=proj["id"]: (win.select_project(i), win.go("chat")))
            self.p_list.addWidget(b)
        if not shown:
            self.p_list.addWidget(label("Nenhum projeto vinculado ainda.", "dim"))
        # second brain
        vault = store.effective_vault(win.pid) if win.pid is not None else store.global_vault()
        idx = win.engine.vault_index(vault) if vault else None
        if idx:
            st = idx.stats()
            self.m_stats["notes"].value_label.setText(str(st.get("notes") or 0))
            ob = win.engine.outbox(win.pid) if win.pid is not None else None
            self.m_stats["drafts"].value_label.setText(str(len(ob.drafts())) if ob else "0")
            self.m_vault.setText(f"Vault: {vault}")
        else:
            for w in self.m_stats.values():
                w.value_label.setText("—")
            self.m_vault.setText("Nenhum vault conectado (Segundo Cérebro › conectar).")
        # active modes (real flags)
        while self.mode_box.count():
            w = self.mode_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        modes = []
        if win.pid is not None and store.autonomous(win.pid):
            modes.append(("Modo autônomo neste projeto", C["gold"]))
        if win.pid is not None and store.get_setting(f"project.{win.pid}.desktop", False):
            modes.append(("Usar o PC ligado neste projeto", C["gold"]))
        if win.wake.running:
            modes.append(("Escuta por nome ligada (microfone aberto, transcrição local)", C["violet"]))
        if win.live_window is not None:
            modes.append(("Modo Live em andamento", C["violet"]))
        if store.get_setting("pc.consent", False):
            modes.append(("Meu computador ativado", C["info"]))
        if not modes:
            modes.append(("Nenhum modo especial ligado: as IAs só fazem o que você pede, com confirmação.", C["dim"]))
        for text, color in modes:
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            h.addWidget(Dot(color, 8))
            h.addWidget(label(text, "muted"), 1)
            self.mode_box.addWidget(row)
