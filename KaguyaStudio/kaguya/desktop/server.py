"""MCP server (stdio, JSON-RPC 2.0) that lets the assistant see the screen and use mouse/keyboard.

Started by Claude Code / Codex only for tasks where the user enabled "Usar o PC":
    KaguyaStudio.exe --mcp-desktop          (Windows build)
    python -m kaguya.desktop.server         (from source)

Safety, enforced here (not left to the model):
* optional **allowed window** (``KAGUYA_DESKTOP_WINDOW``, e.g. "Minecraft"): screenshots show only that
  window and clicks outside it are refused; input goes to it (it is brought to the front first);
* **stop**: the Studio's "Parar" button / Ctrl+Alt+End create the stop flag → every action is refused;
* **failsafe**: pushing the mouse into the top-left corner of the screen stops the control;
* action budget per task (``KAGUYA_DESKTOP_MAX``) and a log of every action for the Studio.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import sys
import time

from . import control
from .backend import Rect, get_backend, parse_keys

PROTOCOL = "2025-06-18"
SERVER_NAME = "kaguya_desktop"

_XY = {"x": {"type": "integer", "description": "coordenada X na última captura de tela"},
       "y": {"type": "integer", "description": "coordenada Y na última captura de tela"}}
TOOLS = [
    {"name": "screenshot", "description": "Captura a tela (ou só a janela permitida). Use sempre antes de agir e "
     "depois para conferir. As coordenadas das outras ferramentas são as desta imagem.",
     "inputSchema": {"type": "object", "properties": {}}, "annotations": {"readOnlyHint": True}},
    {"name": "click", "description": "Clica na posição (x, y) da última captura.",
     "inputSchema": {"type": "object", "properties": {**_XY, "button": {"type": "string", "enum": ["left", "right", "middle"]},
                                                      "double": {"type": "boolean"}}, "required": ["x", "y"]}},
    {"name": "move_mouse", "description": "Move o mouse até (x, y) sem clicar.",
     "inputSchema": {"type": "object", "properties": _XY, "required": ["x", "y"]}},
    {"name": "drag", "description": "Arrasta com o botão esquerdo de (x1, y1) até (x2, y2).",
     "inputSchema": {"type": "object", "properties": {k: {"type": "integer"} for k in ("x1", "y1", "x2", "y2")},
                     "required": ["x1", "y1", "x2", "y2"]}},
    {"name": "scroll", "description": "Rola a roda do mouse em (x, y); amount positivo sobe, negativo desce.",
     "inputSchema": {"type": "object", "properties": {**_XY, "amount": {"type": "integer"}}, "required": ["x", "y", "amount"]}},
    {"name": "type_text", "description": "Digita um texto na janela em foco (aceita acentos). Nunca digite senhas.",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "press_keys", "description": "Pressiona teclas ou atalhos, ex.: \"enter\", \"esc\", \"ctrl+s\", \"f3\", \"w\".",
     "inputSchema": {"type": "object", "properties": {"keys": {"type": "string"},
                                                      "hold_seconds": {"type": "number", "description": "segurar (máx. 5 s), ex.: andar no jogo"}},
                     "required": ["keys"]}},
    {"name": "list_windows", "description": "Lista as janelas abertas (título).",
     "inputSchema": {"type": "object", "properties": {}}, "annotations": {"readOnlyHint": True}},
    {"name": "focus_window", "description": "Traz para a frente a janela cujo título contém o texto.",
     "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}},
    {"name": "wait", "description": "Espera alguns segundos (máx. 30), ex.: o jogo carregar.",
     "inputSchema": {"type": "object", "properties": {"seconds": {"type": "number"}}, "required": ["seconds"]},
     "annotations": {"readOnlyHint": True}},
]

# Personal-assistant tools ("Meu computador" mode only: KAGUYA_DESKTOP_PC=1)
PC_TOOLS = [
    {"name": "open_path", "description": "Abre um arquivo, pasta ou site com o programa padrão do Windows "
     "(ex.: C:\\Users\\voce\\Downloads, um .txt, https://youtube.com).",
     "inputSchema": {"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"]}},
    {"name": "open_app", "description": "Abre um aplicativo pelo nome, como no menu Iniciar (ex.: WhatsApp, Relógio, "
     "Calendário, Spotify, Microsoft Edge). Depois tire um screenshot.",
     "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "set_timer", "description": "Cria um timer do Kaguya Studio: a mascote avisa com voz e notificação.",
     "inputSchema": {"type": "object", "properties": {"minutes": {"type": "number"}, "label": {"type": "string"}},
                     "required": ["minutes"]}},
    {"name": "set_reminder", "description": "Cria um lembrete/alarme do Kaguya Studio para um horário "
     "(\"HH:MM\" de hoje/amanhã ou \"AAAA-MM-DD HH:MM\").",
     "inputSchema": {"type": "object", "properties": {"when": {"type": "string"}, "text": {"type": "string"}},
                     "required": ["when", "text"]}},
    {"name": "create_event", "description": "Cria um evento de agenda (.ics) e abre no app de calendário do usuário "
     "para ele salvar. Datas \"AAAA-MM-DD HH:MM\".",
     "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}, "start": {"type": "string"},
                                                      "end": {"type": "string"}, "location": {"type": "string"}},
                     "required": ["title", "start"]}},
    {"name": "confirm", "description": "OBRIGATÓRIO antes de ações sem volta: enviar mensagem/e-mail, apagar ou "
     "sobrescrever arquivos do usuário, instalar programas. Mostra ao usuário exatamente o que será feito e espera "
     "Sim/Não. Só prossiga se a resposta for sim.",
     "inputSchema": {"type": "object", "properties": {"action": {"type": "string", "description": "ex.: Enviar no WhatsApp para Mamãe: \"...\""}},
                     "required": ["action"]}},
]


class Refused(Exception):
    pass


class Desktop:
    def __init__(self, backend=None, base: Path | None = None, window: str | None = None, max_actions: int | None = None):
        self.b = backend or get_backend()
        self.base = control.control_dir(base)
        self.window_filter = (window if window is not None else os.environ.get("KAGUYA_DESKTOP_WINDOW", "")).strip()
        self.max_actions = max_actions or int(os.environ.get("KAGUYA_DESKTOP_MAX", "400") or 400)
        self.max_width = int(os.environ.get("KAGUYA_DESKTOP_WIDTH", "1280") or 1280)
        self.pc = os.environ.get("KAGUYA_DESKTOP_PC") == "1"
        self.actions = 0
        self.region: Rect | None = None
        self.step = 1

    # ---------------------------------------------------------------- checks
    def _target(self):
        if not self.window_filter:
            return None
        key = self.window_filter.lower()
        for w in self.b.windows():
            if key in w.title.lower():
                return w
        raise Refused(f"A janela permitida (\"{self.window_filter}\") não está aberta. Abra-a primeiro (ex.: rode o "
                      "jogo pelo terminal) e tente de novo.")

    def _area(self) -> Rect:
        scr = self.b.screen()
        w = self._target()
        if w is None:
            return scr
        r = w.rect
        return Rect(max(r.left, scr.left), max(r.top, scr.top), min(r.right, scr.right), min(r.bottom, scr.bottom))

    def _guard(self, action: str, input_action: bool = True):
        reason = control.stop_reason(self.base)
        if reason:
            raise Refused(f"O usuário parou o controle do computador ({reason}). Não tente de novo nesta tarefa; "
                          "relate o que fez até aqui.")
        scr = self.b.screen()
        cx, cy = self.b.cursor()
        if abs(cx - scr.left) <= 2 and abs(cy - scr.top) <= 2 and self.actions > 0:
            control.request_stop(self.base, "mouse levado ao canto superior esquerdo (failsafe)")
            control.log_action(self.base, "stopped", "failsafe do canto da tela")
            raise Refused("Controle parado pelo usuário (failsafe: mouse no canto da tela).")
        if input_action:
            self.actions += 1
            if self.actions > self.max_actions:
                raise Refused(f"Limite de {self.max_actions} ações nesta tarefa atingido.")
            w = self._target()
            if w is not None and self.b.foreground() != w.handle:
                self.b.focus(w)

    def _to_screen(self, x, y) -> tuple[int, int]:
        area = self._area()
        if self.region is None:
            step = 1
            while area.width // step > self.max_width:
                step += 1
            self.region, self.step = area, step
        sx = self.region.left + int(round(float(x) * self.step))
        sy = self.region.top + int(round(float(y) * self.step))
        if not area.contains(sx, sy):
            raise Refused("Posição fora da área permitida" + (f" (janela \"{self.window_filter}\")" if self.window_filter else "")
                          + ". Tire um novo screenshot e use as coordenadas dele.")
        return sx, sy

    # ----------------------------------------------------------------- tools
    def call(self, name: str, a: dict) -> list[dict]:
        if name == "screenshot":
            self._guard(name, input_action=False)
            area = self._area()
            png, w, h, step = self.b.capture(area, self.max_width)
            self.region, self.step = area, step
            control.log_action(self.base, "screenshot", f"{w}x{h}")
            where = f"janela \"{self.window_filter}\"" if self.window_filter else "tela inteira"
            return [{"type": "image", "data": base64.b64encode(png).decode("ascii"), "mimeType": "image/png"},
                    {"type": "text", "text": f"Captura de {where}: {w}x{h} pixels. Use estas coordenadas."}]
        if name == "list_windows":
            self._guard(name, input_action=False)
            titles = [w.title for w in self.b.windows()]
            control.log_action(self.base, "windows", f"{len(titles)} janelas")
            return [{"type": "text", "text": "\n".join(titles) or "(nenhuma janela visível)"}]
        if name == "wait":
            secs = max(0.0, min(30.0, float(a.get("seconds", 1))))
            self._guard(name, input_action=False)
            control.log_action(self.base, "wait", f"{secs:.0f} s")
            end = time.monotonic() + secs
            while time.monotonic() < end:
                if control.stop_reason(self.base):
                    break
                time.sleep(0.2)
            return [{"type": "text", "text": f"Esperei {secs:.1f} s."}]
        if name == "focus_window":
            title = str(a.get("title", "")).strip()
            if self.window_filter and self.window_filter.lower() not in title.lower():
                raise Refused(f"Só a janela \"{self.window_filter}\" pode ser usada nesta tarefa.")
            self._guard(name)
            for w in self.b.windows():
                if title.lower() in w.title.lower():
                    ok = self.b.focus(w)
                    control.log_action(self.base, "focus", w.title)
                    self.region = None
                    return [{"type": "text", "text": f"Janela em foco: {w.title}" + ("" if ok else " (o Windows pode ter só piscado a janela)")}]
            raise Refused(f"Nenhuma janela com \"{title}\" no título.")
        if name in ("click", "move_mouse", "scroll"):
            self._guard(name)
            x, y = self._to_screen(a["x"], a["y"])
            if name == "click":
                count = 2 if a.get("double") else 1
                self.b.click(x, y, a.get("button") or "left", count)
                control.log_action(self.base, "double_click" if count == 2 else "click", f"({a['x']}, {a['y']})")
                return [{"type": "text", "text": "Clique feito. Tire um screenshot para conferir o resultado."}]
            if name == "move_mouse":
                self.b.move(x, y)
                control.log_action(self.base, "move", f"({a['x']}, {a['y']})")
                return [{"type": "text", "text": "Mouse movido."}]
            amount = max(-20, min(20, int(a.get("amount", 0))))
            self.b.scroll(x, y, amount)
            control.log_action(self.base, "scroll", str(amount))
            return [{"type": "text", "text": "Rolagem feita."}]
        if name == "drag":
            self._guard(name)
            x1, y1 = self._to_screen(a["x1"], a["y1"])
            x2, y2 = self._to_screen(a["x2"], a["y2"])
            self.b.drag(x1, y1, x2, y2)
            control.log_action(self.base, "drag", f"({a['x1']},{a['y1']}) → ({a['x2']},{a['y2']})")
            return [{"type": "text", "text": "Arrastado."}]
        if name == "type_text":
            text = str(a.get("text", ""))
            if len(text) > 2000:
                raise Refused("Texto longo demais para digitar (máx. 2000 caracteres).")
            self._guard(name)
            self.b.type_text(text)
            control.log_action(self.base, "type", text[:60] + ("…" if len(text) > 60 else ""))
            return [{"type": "text", "text": f"Digitei {len(text)} caractere(s)."}]
        if name == "press_keys":
            keys = parse_keys(str(a.get("keys", "")))
            if set(keys) >= {"ctrl", "alt", "delete"} or keys == ["win", "l"]:
                raise Refused("Esse atalho do sistema não é permitido.")
            hold = max(0.0, min(5.0, float(a.get("hold_seconds") or 0)))
            self._guard(name)
            if hold and hasattr(self.b, "hold"):
                self.b.hold(keys, hold)
            else:
                self.b.keys(keys)
            control.log_action(self.base, "keys", "+".join(keys) + (f" ({hold:.1f} s)" if hold else ""))
            return [{"type": "text", "text": "Teclas enviadas."}]
        if name in {t["name"] for t in PC_TOOLS}:
            if not self.pc:
                raise Refused("Esta ferramenta só existe no modo Meu computador.")
            return self.pc_call(name, a)
        raise Refused(f"Ferramenta desconhecida: {name}")

    # --------------------------------------------------------------- personal assistant
    def pc_call(self, name: str, a: dict) -> list[dict]:
        from . import assistant
        self._guard(name, input_action=name in ("open_app",))
        if name == "open_path":
            target = assistant.open_target(str(a.get("target", "")))
            control.log_action(self.base, "open", target)
            return [{"type": "text", "text": f"Aberto: {target}. Tire um screenshot para ver."}]
        if name == "open_app":
            app = str(a.get("name", "")).strip()
            assistant.check_app(app)
            self.b.keys(["win"])
            time.sleep(0.8)
            self.b.type_text(app)
            time.sleep(1.2)
            self.b.keys(["enter"])
            control.log_action(self.base, "app", app)
            time.sleep(1.5)
            return [{"type": "text", "text": f"Pedi ao Windows para abrir \"{app}\". Tire um screenshot para conferir."}]
        if name == "set_timer":
            item = assistant.add_alarm(self.base, minutes=float(a.get("minutes", 0)), text=str(a.get("label") or "Timer"))
            control.log_action(self.base, "timer", item["text"])
            return [{"type": "text", "text": f"Timer criado para {item['at_text']}."}]
        if name == "set_reminder":
            item = assistant.add_alarm(self.base, when=str(a.get("when", "")), text=str(a.get("text", "Lembrete")))
            control.log_action(self.base, "reminder", item["text"])
            return [{"type": "text", "text": f"Lembrete criado para {item['at_text']}."}]
        if name == "create_event":
            path = assistant.create_event(self.base, str(a.get("title", "")), str(a.get("start", "")),
                                          str(a.get("end") or ""), str(a.get("location") or ""))
            assistant.open_target(str(path))
            control.log_action(self.base, "event", str(a.get("title", "")))
            return [{"type": "text", "text": f"Evento criado ({path.name}) e aberto no calendário do usuário; "
                                             "se aparecer um botão Salvar/Adicionar, clique nele."}]
        if name == "confirm":
            action = str(a.get("action", "")).strip()
            ok = assistant.ask_user(self.base, action)
            control.log_action(self.base, "confirm", ("SIM: " if ok else "NÃO: ") + action)
            return [{"type": "text", "text": "O usuário CONFIRMOU. Pode fazer exatamente isso." if ok else
                     "O usuário NÃO confirmou (ou não respondeu). Não faça a ação; pergunte o que ele prefere."}]
        raise Refused(name)


# --------------------------------------------------------------------------- JSON-RPC over stdio
def _stdio():
    """Binary stdin/stdout, also in the windowed (no console) Windows build where sys.stdin may be None."""
    if sys.stdin is not None and sys.stdout is not None:
        return sys.stdin.buffer, sys.stdout.buffer
    import msvcrt  # noqa: F401  (Windows only)
    import ctypes
    k = ctypes.windll.kernel32
    fin = msvcrt.open_osfhandle(k.GetStdHandle(-10), os.O_RDONLY)
    fout = msvcrt.open_osfhandle(k.GetStdHandle(-11), 0)
    return os.fdopen(fin, "rb", buffering=0), os.fdopen(fout, "wb", buffering=0)


def handle(desk_factory, msg: dict, state: dict) -> dict | None:
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": params.get("protocolVersion") or PROTOCOL,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "title": "Kaguya Studio — controle do computador", "version": "1"},
            "instructions": "Ferramentas para ver a tela e usar mouse/teclado no Windows do usuário. Sempre faça "
                            "screenshot antes e depois de agir. Nunca digite senhas nem dados pessoais."}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        tools = TOOLS + (PC_TOOLS if os.environ.get("KAGUYA_DESKTOP_PC") == "1" else [])
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": tools}}
    if method == "tools/call":
        try:
            if state.get("desk") is None:
                state["desk"] = desk_factory()
            content = state["desk"].call(params.get("name", ""), params.get("arguments") or {})
            return {"jsonrpc": "2.0", "id": mid, "result": {"content": content, "isError": False}}
        except (Refused, ValueError, OSError, RuntimeError, KeyError) as exc:
            text = str(exc) if not isinstance(exc, KeyError) else f"Parâmetro faltando: {exc}"
            try:
                control.log_action(control.control_dir(), "refused", text)
            except OSError:
                pass
            return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": text}], "isError": True}}
    if mid is None:  # notification (e.g. notifications/initialized)
        return None
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Método não suportado: {method}"}}


def serve(desk_factory=Desktop) -> int:
    fin, fout = _stdio()
    state: dict = {}
    while True:
        line = fin.readline()
        if not line:
            return 0
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line.decode("utf-8"))
        except ValueError:
            continue
        reply = handle(desk_factory, msg, state)
        if reply is not None:
            fout.write((json.dumps(reply, ensure_ascii=False) + "\n").encode("utf-8"))
            fout.flush()


def server_command() -> list[str]:
    """How the CLIs start this server (the frozen .exe re-enters itself with --mcp-desktop)."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--mcp-desktop"]
    return [sys.executable, "-m", "kaguya.desktop.server"]


if __name__ == "__main__":
    raise SystemExit(serve())
