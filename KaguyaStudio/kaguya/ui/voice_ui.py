"""Push-to-talk and spoken answers inside the Studio (Phase A) with non-interrupting routing
of spoken commands while agents work (Phase B)."""
from __future__ import annotations

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QMessageBox

from ..voice import stt
from ..voice.router import route
from ..voice.tts import Speaker
from .common import run_bg


class VoiceController(QObject):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.speaker = Speaker()
        self.recorder: stt.Recorder | None = None
        self.transcriber: stt.Transcriber | None = None
        self._speaking_agent = None
        from ..voice.neural import NeuralVoices
        self.neural = NeuralVoices(self.win.engine.home / "modelos")
        self.queue = None   # SpeechQueue, created lazily (needs numpy/sounddevice)

    # ------------------------------------------------------------------ devices
    def input_index(self):
        from ..voice.devices import resolve
        d = resolve(self.win.store.get_setting("voice.input_name"), getattr(self.win, "audio_in", []))
        return d.index if d else None

    def output_index(self):
        from ..voice.devices import resolve
        d = resolve(self.win.store.get_setting("voice.output_name"), getattr(self.win, "audio_out", []))
        return d.index if d else None

    @property
    def busy(self) -> bool:
        return self.recorder is not None or self.speaker.speaking or bool(self.queue and self.queue.busy)

    # ------------------------------------------------------------------ TTS
    def engine_name(self) -> str:
        """'neural' (Kokoro) when installed and chosen, otherwise 'windows'."""
        choice = self.win.store.get_setting("voice.engine", "auto")
        if choice in ("auto", "neural") and self.neural.ready:
            return "neural"
        return "windows"

    def voice_for(self, agent: str) -> str:
        from ..voice.neural import DEFAULT_PRESET
        st = self.win.store
        if self.engine_name() == "neural":
            return st.get_setting(f"voice.neural_{agent}", DEFAULT_PRESET.get(agent, "dora"))
        return st.get_setting(f"voice.voice_{agent}", "") or st.get_setting("voice.tts_voice", "") or ""

    def _ensure_queue(self):
        from ..voice import devices as dv
        from ..voice.speech import SpeechQueue, sapi_synth, sounddevice_player
        if self.queue is not None or not dv.available():
            return self.queue

        def synth(text, agent):
            if self.engine_name() == "neural":
                return self.neural.synth(text, self.voice_for(agent))
            return sapi_synth(self.voice_for)(text, agent)

        def on_state(state, agent):
            self.win.bridge.call.emit(lambda: self._on_queue_state(state, agent))
        self.queue = SpeechQueue(synth, sounddevice_player(self.output_index), on_state)
        return self.queue

    def _duck(self, on: bool):
        """Lower Kaguya Music while an assistant talks; restored on every end (done, stopped, error)."""
        music = getattr(self.win, "music", None)
        if music is not None:
            music.duck(on)

    def _on_queue_state(self, state: str, agent: str):
        m = self.win.mascots.get(agent)
        self._duck(state == "speaking")
        if state == "speaking":
            self.win.chat.composer.speak_btn.setText("Parar voz")
            if m:
                m.set_state("speaking")
        else:
            self.win.chat.composer.speak_btn.setText("Ouvir")
            if m and m.state == "speaking":
                m.set_state("idle")

    def say(self, text: str, agent: str) -> bool:
        """Queue speech (used by Live and auto-read). Returns False when no voice output exists."""
        q = self._ensure_queue()
        if q is None:
            return False
        q.say(text, agent)
        return True

    def stop_speaking(self):
        self._duck(False)
        if self.queue:
            self.queue.stop()
        self.speaker.stop()

    def speak(self, text: str, agent: str | None = None):
        if not text:
            self.win.toast("Ainda não há resposta para ouvir.")
            return
        if self.busy and (self.speaker.speaking or (self.queue and self.queue.busy)):
            self.stop_speaking()
            self._done_speaking()
            return
        self._speaking_agent = agent or self._last_agent()
        if self.say(text, self._speaking_agent):
            return
        # Fallback without numpy/sounddevice: direct Windows voice.
        if Speaker.backend() is None:
            self.win.toast("Leitura por voz indisponível neste sistema.")
            return
        self.speaker.voice = self.voice_for(self._speaking_agent) if self.engine_name() == "windows" else ""
        self.speaker.output_device = None
        m = self.win.mascots.get(self._speaking_agent)
        self._duck(True)
        if m:
            m.set_state("speaking")
        self.win.chat.composer.speak_btn.setText("Parar voz")
        self.speaker.speak(text, on_done=lambda: self.win.bridge.call.emit(self._done_speaking))

    def _last_agent(self) -> str:
        lay = self.win.chat.view.lay
        for i in range(lay.count() - 2, -1, -1):
            w = lay.itemAt(i).widget()
            if w is not None and getattr(w, "agent", None) in ("codex", "claude"):
                return w.agent
        return "codex"

    def _done_speaking(self):
        self._duck(False)
        self.win.chat.composer.speak_btn.setText("Ouvir")
        m = self.win.mascots.get(self._speaking_agent or "")
        if m and m.state == "speaking":
            m.set_state("idle")

    # ------------------------------------------------------------------ STT
    def ptt(self, on: bool):
        btn = self.win.chat.composer.mic_btn
        if on:
            st = stt.status(self.win.engine.home / "modelos", self.win.store.get_setting("voice.model", "small"))
            if not st.ready:
                btn.setChecked(False)
                import sys as _sys
                how = ("Esta cópia do executável foi gerada sem a voz local. Baixe a versão mais recente do "
                       "KaguyaStudio (ela já inclui a transcrição)." if getattr(_sys, "frozen", False) else
                       f"Instale com o INSTALAR.bat (opção de voz) ou:\n{stt.INSTALL_CMD}")
                QMessageBox.information(self.win, "Voz", "A transcrição local não está disponível.\n\nFaltam: "
                                        + ", ".join(st.missing) + "\n\n" + how +
                                        "\n\nNada é enviado para APIs pagas: tudo roda no seu computador.")
                return
            if not st.model_cached and not self.win.store.get_setting("voice.model_consent", False):
                btn.setChecked(False)
                QMessageBox.information(self.win, "Voz", "Para transcrever, o modelo escolhido precisa ser baixado uma vez.\n"
                                        "Autorize em Configurações › Voz local.")
                return
            self.speaker.stop()
            try:
                self.recorder = stt.Recorder(self.input_index())
                self.recorder.start()
            except Exception as exc:
                btn.setChecked(False)
                QMessageBox.warning(self.win, "Microfone", f"Não foi possível abrir o microfone: {exc}\n"
                                    "Verifique a permissão de microfone do Windows (Configurações › Privacidade).")
                return
            btn.setText("Gravando… clique para enviar")
            for m in self.win.mascots.values():
                m.set_state("listening")
            return
        if self.recorder is None:
            return
        audio = self.recorder.stop()
        self.recorder = None
        btn.setText("Transcrevendo…")
        btn.setEnabled(False)
        model = self.win.store.get_setting("voice.model", "small")
        if self.transcriber is None or self.transcriber.model_name != model:
            self.transcriber = stt.Transcriber(self.win.engine.home / "modelos", model)
        run_bg(lambda: self.transcriber.transcribe(audio), self._transcribed,
               lambda e, tb: self._transcribed("", str(e)))

    def _transcribed(self, text: str, error: str = ""):
        btn = self.win.chat.composer.mic_btn
        btn.setEnabled(True)
        btn.setText("Falar")
        for m in self.win.mascots.values():
            if m.state == "listening":
                m.set_state("idle")
        if error:
            QMessageBox.warning(self.win, "Transcrição", f"Falha na transcrição local: {error}")
            return
        if not text:
            self.win.toast("Não entendi o áudio (muito curto ou silencioso).")
            return
        action, payload = route(text)
        comp = self.win.chat.composer
        if action == "stop":
            self.speaker.stop()
        elif action == "status":
            self.speak(self.status_sentence())
        elif action in ("later", "idea"):
            self.win.send_message(payload, comp.target, "DEPOIS" if action == "later" else "IDEIA")
            self.win.toast(f"Guardado como {'DEPOIS' if action == 'later' else 'IDEIA'} (não interrompe o trabalho).")
        else:
            # Never sent automatically: the user reviews the transcription first.
            comp.edit.setPlainText(payload)
            comp.edit.setFocus()
            self.win.toast("Transcrição colocada no campo de mensagem. Revise e envie (Ctrl+Enter).")

    def status_sentence(self) -> str:
        win = self.win
        if win.pid is None:
            return "Nenhum projeto selecionado."
        tid = win.engine.current_task(win.pid)
        pend = win.store.pending_count(win.pid)
        if not tid:
            return f"Nenhuma tarefa em execução. Há {pend} pendente{'s' if pend != 1 else ''} na fila."
        t = win.store.get_task(tid)
        stage = (t.get("stage") or "execução").split(":")[0]
        return f"Tarefa {tid} em andamento, etapa {stage}. {pend - 1 if pend else 0} outras na fila."

    def shutdown(self):
        self.stop_speaking()
        if self.recorder:
            try:
                self.recorder.stop()
            except Exception:
                pass
