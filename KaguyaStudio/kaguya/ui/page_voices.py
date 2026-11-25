"""Vozes: engines with their real status, per-character voice profiles, benchmark (TTFA/RTF) and blind A/B test."""
from __future__ import annotations

import json
import random
import threading

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QFormLayout, QGridLayout, QHBoxLayout, QSlider, QTextBrowser, QVBoxLayout,
                               QWidget)

from ..appdirs import ASSETS
from ..voice.engines import HEAVY, STYLES, VoiceProfile, benchmark, load_profile, save_profile
from .common import run_bg
from .page_work import item, page_title, scroll, table
from .theme import AGENT, C
from .widgets import Card, button, label


def phrases() -> list[dict]:
    try:
        return json.loads((ASSETS / "voice" / "frases_ptbr_benchmark.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return [{"id": "saudacao", "text": "Olá. Eu sou Kaguya, e estou pronta para ajudar com o seu projeto."}]


class ProfileEditor(Card):
    def __init__(self, page, agent: str):
        super().__init__(accent=AGENT[agent]["color"])
        self.page, self.win, self.agent = page, page.win, agent
        self._loading = False
        title = label(f"Voz da {AGENT[agent]['mascot']}", "h2")
        title.setStyleSheet(f"color: {AGENT[agent]['color']};")
        self.lay.addWidget(title)
        form = QFormLayout()
        self.engine = QComboBox()
        self.voice = QComboBox()
        self.style = QComboBox()
        for key, (text, _f) in STYLES.items():
            self.style.addItem(text, key)
        self.speed = QSlider(Qt.Horizontal)
        self.speed.setRange(70, 140)
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.speed_lbl, self.volume_lbl = label("", "dim"), label("", "dim")
        srow, vrow = QHBoxLayout(), QHBoxLayout()
        srow.addWidget(self.speed, 1)
        srow.addWidget(self.speed_lbl)
        vrow.addWidget(self.volume, 1)
        vrow.addWidget(self.volume_lbl)
        form.addRow("Motor", self.engine)
        form.addRow("Voz", self.voice)
        form.addRow("Estilo", self.style)
        form.addRow("Velocidade", srow)
        form.addRow("Volume", vrow)
        self.lay.addLayout(form)
        self.used = label("", "dim", wrap=True)
        self.lay.addWidget(self.used)
        row = QHBoxLayout()
        hear = button(f"Ouvir {AGENT[agent]['mascot']}", "volume", "primary")
        hear.clicked.connect(self.hear)
        stop = button("Parar", "stop", "ghost")
        stop.clicked.connect(lambda: self.win.voice.stop_speaking())
        row.addWidget(hear)
        row.addWidget(stop)
        row.addStretch(1)
        self.lay.addLayout(row)
        self.engine.currentIndexChanged.connect(self._engine_changed)
        for w in (self.voice, self.style):
            w.currentIndexChanged.connect(self.save)
        self.speed.valueChanged.connect(lambda v: (self.speed_lbl.setText(f"{v / 100:.2f}×"), self.save()))
        self.volume.valueChanged.connect(lambda v: (self.volume_lbl.setText(f"{v}%"), self.save()))

    def load(self, caps):
        self._loading = True
        self.caps = {c.id: c for c in caps}
        p = load_profile(self.win.store, self.agent)
        self.engine.clear()
        self.engine.addItem("Automático (melhor voz local disponível)", "auto")
        for c in caps:
            self.engine.addItem(c.name + ("" if c.installed else " — não instalado"), c.id)
            if not c.installed:
                self.engine.model().item(self.engine.count() - 1).setEnabled(False)
        self.engine.setCurrentIndex(max(0, self.engine.findData(p.engine)))
        self._fill_voices(p.voice)
        self.style.setCurrentIndex(max(0, self.style.findData(p.style)))
        self.speed.setValue(int(round(p.speed * 100)))
        self.speed_lbl.setText(f"{p.speed:.2f}×")
        self.volume.setValue(p.volume)
        self.volume_lbl.setText(f"{p.volume}%")
        self._loading = False
        self._show_used()

    def _fill_voices(self, current: str = ""):
        self.voice.blockSignals(True)
        self.voice.clear()
        eid = self.engine.currentData()
        engine = self.win.voice.engines.resolve(VoiceProfile(engine=eid or "auto"))
        cap = self.caps.get(engine.id) if engine else None
        self.voice.addItem("Padrão da personagem", "")
        for vid, text in (cap.voices if cap else []):
            self.voice.addItem(text, vid)
        self.voice.setCurrentIndex(max(0, self.voice.findData(current)))
        self.voice.blockSignals(False)

    def _engine_changed(self, *_):
        if not self._loading:
            self._fill_voices()
            self.save()

    def current(self) -> VoiceProfile:
        return VoiceProfile(engine=self.engine.currentData() or "auto", voice=self.voice.currentData() or "",
                            style=self.style.currentData() or "natural", speed=self.speed.value() / 100,
                            volume=self.volume.value())

    def save(self, *_):
        if self._loading:
            return
        save_profile(self.win.store, self.agent, self.current())
        self._show_used()

    def _show_used(self):
        engine = self.win.voice.engines.resolve(self.current())
        self.used.setText(f"Em uso agora: {self.caps[engine.id].name}" if engine and engine.id in self.caps else
                          "Nenhum motor de voz disponível nesta cópia.")

    def hear(self):
        name = AGENT[self.agent]["mascot"]
        text = (f"Olá! Eu sou a {name}. Hoje é 25/11/2026 e a GPU tem 8 GB de VRAM. "
                "Na verdade, podemos tentar de outra maneira: talvez fique mais simples e rápido.")
        if not self.win.voice.say(text, self.agent):
            self.win.toast("Sem saída de áudio disponível nesta cópia.")


class VoicesPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(12)
        # engines
        ec = Card()
        ec.lay.addWidget(label("MOTORES DE VOZ (STATUS REAL NESTE PC)", "section"))
        self.engines_table = table(["Motor", "Situação", "Licença", "Tamanho", "Clonagem", "Fala"], stretch=1)
        self.engines_table.setMinimumHeight(150)
        ec.lay.addWidget(self.engines_table)
        ec.lay.addWidget(label("Qwen3-TTS e Chatterbox precisam de PyTorch e vários GB num ambiente isolado: nada é "
                               "baixado sem a sua autorização. Clonagem de voz só com gravação sua ou de quem autorizou.",
                               "dim", wrap=True))
        lay.addWidget(ec)
        # profiles
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        self.editors = {a: ProfileEditor(self, a) for a in ("codex", "claude")}
        grid.addWidget(self.editors["codex"], 0, 0, Qt.AlignTop)
        grid.addWidget(self.editors["claude"], 0, 1, Qt.AlignTop)
        lay.addLayout(grid)
        # benchmark
        bc = Card()
        bc.lay.addWidget(label("BENCHMARK (MEDIDO NESTE PC)", "section"))
        brow = QHBoxLayout()
        self.bench_agent = QComboBox()
        for a in ("codex", "claude"):
            self.bench_agent.addItem(AGENT[a]["mascot"], a)
        self.bench_btn = button("Medir agora", "gauge", "primary", "Sintetiza as frases de teste em pt-BR (sem tocar) e mede")
        self.bench_btn.clicked.connect(self.run_benchmark)
        brow.addWidget(self.bench_agent)
        brow.addWidget(self.bench_btn)
        brow.addStretch(1)
        bc.lay.addLayout(brow)
        self.bench_out = QTextBrowser()
        self.bench_out.setFixedHeight(170)
        bc.lay.addWidget(self.bench_out)
        bc.lay.addWidget(label("TTFA = tempo até o primeiro áudio da primeira frase (sem a latência da placa de som); "
                               "RTF = tempo de síntese ÷ duração do áudio (abaixo de 1 = mais rápido que o tempo real).",
                               "dim", wrap=True))
        lay.addWidget(bc)
        # blind A/B
        ac = Card()
        ac.lay.addWidget(label("TESTE CEGO A/B", "section"))
        ac.lay.addWidget(label("Escolha duas vozes; o Studio sorteia a ordem e você vota sem saber qual é qual.", "muted",
                               wrap=True))
        arow = QHBoxLayout()
        self.ab_agent = QComboBox()
        for a in ("codex", "claude"):
            self.ab_agent.addItem(AGENT[a]["mascot"], a)
        self.ab_a, self.ab_b = QComboBox(), QComboBox()
        arow.addWidget(self.ab_agent)
        arow.addWidget(label("A", "dim"))
        arow.addWidget(self.ab_a, 1)
        arow.addWidget(label("B", "dim"))
        arow.addWidget(self.ab_b, 1)
        ac.lay.addLayout(arow)
        prow = QHBoxLayout()
        self.play1 = button("Tocar 1", "play", "ghost")
        self.play2 = button("Tocar 2", "play", "ghost")
        self.vote1 = button("Prefiro 1", "check")
        self.vote2 = button("Prefiro 2", "check")
        self.new_round = button("Nova rodada", "refresh", "ghost")
        self.play1.clicked.connect(lambda: self._play_ab(0))
        self.play2.clicked.connect(lambda: self._play_ab(1))
        self.vote1.clicked.connect(lambda: self._vote(0))
        self.vote2.clicked.connect(lambda: self._vote(1))
        self.new_round.clicked.connect(self._new_round)
        for b in (self.play1, self.play2, self.vote1, self.vote2, self.new_round):
            prow.addWidget(b)
        prow.addStretch(1)
        ac.lay.addLayout(prow)
        self.ab_result = label("", "muted", wrap=True)
        ac.lay.addWidget(self.ab_result)
        lay.addWidget(ac)
        lay.addStretch(1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page_title("volume", "Vozes", "Vozes locais da Kaguya e da Miwa: motor, voz, estilo, velocidade e "
                                   "volume de cada uma, medições reais e teste cego. Nada de API paga."))
        outer.addWidget(scroll(content), 1)
        self._ab_order: list[int] = [0, 1]
        self._phrase = None

    def refresh(self):
        caps = self.win.voice.engines.capabilities()
        self.engines_table.setRowCount(0)
        for c in caps:
            r = self.engines_table.rowCount()
            self.engines_table.insertRow(r)
            self.engines_table.setItem(r, 0, item(c.name))
            self.engines_table.setItem(r, 1, item(c.status, C["success"] if c.installed else C["muted"]))
            self.engines_table.setItem(r, 2, item(c.license, C["dim"]))
            self.engines_table.setItem(r, 3, item(c.size, C["dim"]))
            self.engines_table.setItem(r, 4, item("sim (com consentimento)" if c.cloning else "não", C["dim"]))
            self.engines_table.setItem(r, 5, item(c.streaming, C["dim"]))
            self.engines_table.item(r, 0).setToolTip(c.notes)
        for e in self.editors.values():
            e.load(caps)
        options = [("kokoro|" + v, f"Kokoro · {t}") for c in caps if c.id == "kokoro" and c.installed for v, t in c.voices]
        options += [("windows|" + v, f"Windows · {t}") for c in caps if c.id == "windows" and c.installed for v, t in c.voices]
        for box, pick in ((self.ab_a, 0), (self.ab_b, 1)):
            box.clear()
            for key, text in options:
                box.addItem(text, key)
            box.setCurrentIndex(min(pick, max(0, box.count() - 1)))
        for w in (self.play1, self.play2, self.vote1, self.vote2):
            w.setEnabled(len(options) >= 2)
        self.ab_result.setText(self._tally_text() if len(options) >= 2 else
                               "São precisas pelo menos duas vozes instaladas para o teste cego.")
        last = self.win.store.get_setting("voice.benchmark.last", None)
        if last:
            self._show_bench(last)

    # ------------------------------------------------------------- benchmark
    def run_benchmark(self):
        agent = self.bench_agent.currentData()
        prof = self.win.voice.profile(agent)
        self.bench_btn.setEnabled(False)
        self.bench_out.setPlainText("Medindo… (as frases são sintetizadas, não tocadas)")
        engines = self.win.voice.engines

        def done(res):
            self.bench_btn.setEnabled(True)
            self.win.store.set_setting("voice.benchmark.last", res)
            self._show_bench(res)
        run_bg(lambda: benchmark(engines, prof, agent, phrases()), done,
               lambda exc, tb: (self.bench_btn.setEnabled(True), self.bench_out.setPlainText(f"Falhou: {exc}")))

    def _show_bench(self, res: dict):
        if not res.get("engine"):
            self.bench_out.setPlainText("Nenhum motor de voz disponível para medir.")
            return
        lines = [f"{res['when']} • motor {res['engine']} • {AGENT[res['agent']]['mascot']} • "
                 f"TTFA p50 {res['ttfa_p50']} s / p95 {res['ttfa_p95']} s • RTF p50 {res['rtf_p50']}", ""]
        lines += [f"{r['id']:<16} TTFA {r['ttfa_s']:.2f} s   síntese {r['gen_s']:.2f} s   áudio {r['audio_s']:.2f} s   "
                  f"RTF {r['rtf']}" for r in res["rows"]]
        if res.get("errors"):
            lines += ["", "Erros:"] + res["errors"]
        self.bench_out.setPlainText("\n".join(lines))

    # ---------------------------------------------------------------- A/B
    def _new_round(self):
        self._ab_order = random.sample([0, 1], 2)
        self._phrase = random.choice(phrases())["text"]
        self.ab_result.setText("Nova rodada: ouça 1 e 2 e vote." + "\n" + self._tally_text())

    def _config(self, which: int) -> tuple[str, str]:
        box = (self.ab_a, self.ab_b)[self._ab_order[which]]
        engine, voice = (box.currentData() or "kokoro|").split("|", 1)
        return engine, voice

    def _play_ab(self, which: int):
        if self._phrase is None:
            self._new_round()
        engine, voice = self._config(which)
        agent = self.ab_agent.currentData()
        prof = VoiceProfile(engine=engine, voice=voice)
        v = self.win.voice
        q = v._ensure_queue()
        if q is None:
            self.win.toast("Sem saída de áudio nesta cópia.")
            return
        v.stop_speaking()

        def work():
            from ..voice.normalize import normalize
            audio, sr, _ = v.engines.synth(normalize(self._phrase), prof, agent)
            q._audio.put((q._gen, audio, sr, agent))
        threading.Thread(target=work, daemon=True).start()

    def _vote(self, which: int):
        winner_box = self._ab_order[which]
        votes = self.win.store.get_setting("voice.ab_votes", {}) or {}
        key = (self.ab_a, self.ab_b)[winner_box].currentText()
        votes[key] = votes.get(key, 0) + 1
        self.win.store.set_setting("voice.ab_votes", votes)
        self.ab_result.setText(f"Você preferiu a {which + 1}: era “{key}”.\n" + self._tally_text())
        self._new_round()

    def _tally_text(self) -> str:
        votes = self.win.store.get_setting("voice.ab_votes", {}) or {}
        if not votes:
            return "Nenhum voto ainda."
        return "Placar: " + " • ".join(f"{k}: {v}" for k, v in sorted(votes.items(), key=lambda x: -x[1]))
