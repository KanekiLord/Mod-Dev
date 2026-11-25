"""Studio side of "Meu computador": Yes/No confirmations asked by the assistants and timers/reminders.

The desktop MCP server (another process) writes requests into the control folder; this watcher shows
them with the mascot (bubble + voice + always-on-top dialog) and writes the answer back. Alarms fire even
with the Studio minimized to the tray.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMessageBox

from ..desktop import assistant
from .theme import AGENT


class AssistantWatcher:
    def __init__(self, win):
        self.win = win
        self.base = win.engine.home / "desktop"
        self.shown: dict[str, QMessageBox] = {}
        self.timer = QTimer(win, interval=700)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def stop(self):
        self.timer.stop()
        for box in list(self.shown.values()):
            box.close()
        self.shown.clear()

    def tick(self):
        try:
            reqs = assistant.pending_requests(self.base)
            due = assistant.due_alarms(self.base)
        except OSError:
            return
        live = {r["id"] for r in reqs}
        for rid in [k for k in self.shown if k not in live]:  # timed out / answered elsewhere
            self.shown.pop(rid).close()
        for r in reqs:
            if r["id"] not in self.shown:
                self.ask(r)
        for a in due:
            self.ring(a)

    # ---------------------------------------------------------------- confirm
    def _agent(self, name: str) -> str:
        return name if name in ("codex", "claude") else "codex"

    def ask(self, req: dict):
        agent = self._agent(req.get("agent", ""))
        who = AGENT[agent]["mascot"]
        text = req["action"]
        box = QMessageBox(QMessageBox.Question, f"{who} pede confirmação", f"{who} quer fazer isto:\n\n{text}\n\nPode?",
                          QMessageBox.Yes | QMessageBox.No)
        box.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        box.setWindowModality(Qt.NonModal)
        box.setDefaultButton(QMessageBox.No)
        box.button(QMessageBox.Yes).setText("Sim, pode")
        box.button(QMessageBox.No).setText("Não")
        box.finished.connect(lambda code, rid=req["id"]: self._answer(rid, code == QMessageBox.Yes))
        self.shown[req["id"]] = box
        self._show_mascot(agent, f"Posso? {text}", 60)
        self.win.voice.say(f"Posso fazer isso? {text}", agent)
        if getattr(self.win, "tray", None):
            self.win.tray.showMessage(f"{who} pede confirmação", text[:200], self.win.windowIcon(), 15000)
        box.show()
        box.raise_()

    def _answer(self, rid: str, yes: bool):
        if self.shown.pop(rid, None) is None:
            return
        try:
            assistant.answer_request(self.base, rid, yes)
        except OSError:
            pass

    # ----------------------------------------------------------------- alarms
    def ring(self, alarm: dict):
        agent = self._agent(alarm.get("agent", ""))
        title = "Timer" if alarm.get("kind") == "timer" else "Lembrete"
        text = f"⏰ {title}: {alarm['text']}"
        self._show_mascot(agent, text, 60)
        self.win.voice.say(f"{title}! {alarm['text']}", agent)
        if getattr(self.win, "tray", None):
            self.win.tray.showMessage(title, alarm["text"], self.win.windowIcon(), 20000)
        self.win.toast(text, 10000)

    def _show_mascot(self, agent: str, text: str, seconds: float):
        m = self.win.mascots.get(agent)
        if m:
            m.show_window()
            m.set_state("speaking")
        self.win.wake.current, self.win.wake._user = agent, ""
        self.win.wake.bubble.show_for(agent, m.window if m else None, text, "", seconds)
