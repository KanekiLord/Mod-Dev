"""Call an assistant by name in the background: "Kaguya, olha isso pra mim" / "Miwa, vê isso pra mim".

The microphone listens locally (energy VAD + local Whisper). Nothing reaches an AI until a name is
heard. Then the mascot pops up on the desktop with a speech bubble, answers by voice, and anything
that needs real work becomes a task (autonomous projects run it right away).
"""
from __future__ import annotations

import re

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLabel, QMessageBox, QVBoxLayout, QWidget

from .common import run_bg
from .theme import AGENT, C


class SpeechBubble(QWidget):
    """Comic-style bubble next to the floating mascot."""

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.agent = "codex"
        self.setFixedWidth(300)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 22)
        lay.setSpacing(4)
        self.who = QLabel()
        self.who.setStyleSheet(f"color: {C['muted']}; font-size: 8.5pt;")
        self.who.setWordWrap(True)
        self.text = QLabel()
        self.text.setWordWrap(True)
        inner = 300 - 32
        self.who.setFixedWidth(inner)
        self.text.setFixedWidth(inner)
        self.text.setStyleSheet(f"color: {C['text']}; font-size: 10pt;")
        lay.addWidget(self.who)
        lay.addWidget(self.text)
        self._hide = QTimer(self, singleShot=True)
        self._hide.timeout.connect(self.hide)
        self.anchor = None

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(2, 2, -2, -14)
        path = QPainterPath()
        path.addRoundedRect(r, 16, 16)
        tail = QPainterPath()
        x = r.right() - 46
        tail.moveTo(x, r.bottom() - 2)
        tail.lineTo(x + 26, r.bottom() + 12)
        tail.lineTo(x + 18, r.bottom() - 2)
        path = path.united(tail)
        p.setPen(QPen(QColor(AGENT.get(self.agent, AGENT["codex"])["color"]), 2))
        p.setBrush(QColor(C["elevated"]))
        p.drawPath(path)

    def show_for(self, agent: str, window, text: str, who: str = "", seconds: float = 9):
        self.agent, self.anchor = agent, window
        self.who.setText(who)
        self.who.setVisible(bool(who))
        self.text.setText(text[:500])
        inner = self.text.width()
        h = self.text.heightForWidth(inner) + (self.who.heightForWidth(inner) + 4 if who else 0)
        self.setFixedHeight(h + 12 + 22 + 4)
        self._place()
        self.show()
        self.raise_()
        self.update()
        self._hide.start(int(seconds * 1000))

    def _place(self):
        geo = QGuiApplication.primaryScreen().availableGeometry()
        if self.anchor is not None and self.anchor.isVisible():
            a = self.anchor.frameGeometry()
            pos = QPoint(a.left() + a.width() // 2 - self.width() + 40, a.top() - self.height() + 6)
        else:
            pos = QPoint(geo.right() - self.width() - 40, geo.bottom() - self.height() - 220)
        pos.setX(max(geo.left(), min(pos.x(), geo.right() - self.width())))
        pos.setY(max(geo.top(), pos.y()))
        self.move(pos)


def first_sentences(text: str, limit: int = 220) -> str:
    """Short spoken summary of a task result (skips the report headings)."""
    body = re.split(r"\n\s*(?:EVID[ÊE]NCIAS|PEND[ÊE]NCIAS|APRENDIZADOS|ERROS|REFER[ÊE]NCIAS|VERIFICA)", text or "", 1)[0]
    body = re.sub(r"^\s*TRABALHO:\s*", "", body.strip())
    body = re.sub(r"[`*_#>]", "", body)
    body = " ".join(body.split())
    if len(body) <= limit:
        return body
    cut = body[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return (cut[:end + 1] if end > 60 else cut.rstrip() + "…")


class WakeController:
    def __init__(self, win):
        self.win = win
        self.session = None
        self.starting = False
        self.bubble = SpeechBubble()
        self.voice_tasks: dict[int, str] = {}
        self.current = "codex"
        self._answer = ""
        self._user = ""

    @property
    def running(self) -> bool:
        return self.session is not None

    # ---------------------------------------------------------------- control
    def start(self) -> bool:
        win = self.win
        if self.session is not None or self.starting:
            return True
        if win.live_window is not None:
            win.toast("Feche o Modo Live para ligar a escuta por nome.")
            return False
        problems = win.voice_problems()
        if problems:
            QMessageBox.information(win, "Chamar pelo nome", "Para chamar a Kaguya e a Miwa pelo nome:\n\n• "
                                    + "\n• ".join(problems))
            win.go("settings")
            return False
        if not win.store.get_setting("wake.consent", False):
            msg = ("Com a escuta ligada, o microfone fica aberto enquanto o Studio estiver rodando (inclusive "
                   "minimizado na bandeja).\n\n"
                   "• Tudo o que é dito é transcrito NO SEU PC; nada é enviado para a IA até você dizer "
                   "\"Kaguya…\" (Codex) ou \"Miwa…\" (Claude Code).\n"
                   "• Depois que uma delas responde, por alguns segundos você pode continuar sem repetir o nome.\n"
                   "• Para reconhecer os nomes gastando pouco processador, o Studio usa também o modelo de "
                   "transcrição \"base\" (≈145 MB, baixado uma vez).\n"
                   "• Desligue quando quiser pelo ícone da Kaguya perto do relógio.\n\nLigar a escuta?")
            if QMessageBox.question(win, "Chamar pelo nome", msg) != QMessageBox.Yes:
                win.sync_wake_ui()
                return False
            win.store.set_setting("wake.consent", True)
        self.starting = True
        win.sync_wake_ui()
        cwd = win.store.project(win.pid)["directory"] if win.pid is not None else str(win.engine.home)
        from ..voice import stt

        def prepare():
            exes = {}
            for a in ("codex", "claude"):
                try:
                    exes[a] = win.engine.ensure_ready(a, cwd)
                except Exception as exc:
                    exes[a] = exc
            model = win.store.get_setting("voice.model", "small")
            if win.voice.transcriber is None or win.voice.transcriber.model_name != model:
                win.voice.transcriber = stt.Transcriber(win.engine.home / "modelos", model)
            win.voice.transcriber.load()
            quick_name = win.store.get_setting("wake.model", "base")
            quick = None
            if quick_name and quick_name != model:
                quick = stt.Transcriber(win.engine.home / "modelos", quick_name)
                quick.load()
            return exes, quick
        run_bg(prepare, lambda res: self._ready(res[0], res[1], cwd), self._failed)
        return True

    def _failed(self, exc, tb=None):
        self.starting = False
        self.win.toast(f"Não foi possível ligar a escuta: {exc}")
        self.win.sync_wake_ui()

    def _ready(self, exes, quick, cwd):
        from ..live.session import LiveSession, NAMES_PROMPT
        win = self.win
        self.starting = False
        if all(isinstance(v, Exception) for v in exes.values()):
            self._failed(exes.get("codex"))
            return
        q = win.voice._ensure_queue()
        self.session = LiveSession(
            agent="codex", make_conversation=win.conversation_factory(exes, cwd),
            transcribe=lambda audio: win.voice.transcriber.transcribe(audio, NAMES_PROMPT),
            quick_transcribe=(lambda audio: quick.transcribe(audio, NAMES_PROMPT)) if quick else None,
            say=win.voice.say, stop_speech=win.voice.stop_speaking, speech_busy=lambda: bool(q and q.busy),
            on_event=lambda ev: win.bridge.call.emit(lambda ev=ev: self.on_event(ev)),
            on_task=lambda text, a, scope="project": win.bridge.call.emit(lambda: self.on_task(text, a, scope)),
            input_device=win.voice.input_index(), wake=True,
            local_command=lambda text: win.bridge_call(win.music_command, text),
            follow_up_s=float(win.store.get_setting("wake.follow_up_s", 12)))
        try:
            self.session.start()
        except Exception as exc:
            self.session = None
            self._failed(f"microfone: {exc}")
            return
        win.store.set_setting("wake.enabled", True)
        win.toast("Escuta ligada: diga \"Kaguya…\" ou \"Miwa…\".")
        win.sync_wake_ui()

    def stop(self, remember: bool = False):
        s, self.session = self.session, None
        self.starting = False
        if s is not None:
            run_bg(s.stop)
            if not remember:
                self.win.store.set_setting("wake.enabled", False)
        self.bubble.hide()

    # ----------------------------------------------------------------- events
    def _mascot(self, agent):
        return self.win.mascots.get(agent)

    def on_event(self, ev: dict):
        t = ev["type"]
        if t == "called":
            self.current = ev["agent"]
            self._answer, self._user = "", ev.get("text", "")
            m = self._mascot(self.current)
            if m:
                m.show_window()
                m.set_state("listening")
            self._bubble("…", seconds=20)
        elif t == "state":
            m = self._mascot(self.current)
            st = ev["state"]
            if m and st in ("thinking", "speaking", "transcribing"):
                m.set_state("thinking" if st == "transcribing" else st)
            elif m and st == "listening" and m.state in ("thinking", "speaking", "listening"):
                m.set_state("idle")
        elif t == "caption":
            if ev["role"] == "user":
                self._user = ev["text"]
                self._answer = ""
                self._bubble("…", seconds=20)
            else:
                self._answer = ev["text"]
                self._bubble(self._answer, seconds=14 if ev.get("final") else 30)
        elif t == "error":
            self.win.toast(ev["message"][:200])
        elif t == "sleep":
            self.bubble.hide()

    def _bubble(self, text, seconds=10):
        m = self._mascot(self.current)
        who = f"Você: {self._user}" if self._user else ""
        self.bubble.show_for(self.current, m.window if m else None, text, who, seconds)

    def on_task(self, text: str, agent: str, scope: str = "project"):
        tid, note = self.win.spoken_task(text, agent, scope)
        if tid is not None:
            self.voice_tasks[tid] = agent
            self.win.toast(f"Tarefa #{tid}: {text[:80]}")
        if note:
            self.win.voice.say(note, agent)

    def task_done(self, ev: dict):
        agent = self.voice_tasks.pop(ev.get("task_id"), None)
        if agent is None:
            return
        ok = ev.get("status") in ("approved", "executed")
        summary = first_sentences(ev.get("summary", ""))
        text = ("Terminei a tarefa. " if ok else "A tarefa não deu certo. ") + summary
        m = self._mascot(agent)
        if m:
            m.show_window()
            m.set_state("success" if ok else "error")
        self.current, self._user = agent, ""
        self._bubble(text, seconds=20)
        self.win.voice.say(text, agent)
