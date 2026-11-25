"""Per-tab permissions: a tab is personal unless the user shares it with an assistant.

* ``read``    — the assistant may receive the tab's title, URL and visible text (when the user asks something).
* ``control`` — supervised control: the assistant may scroll/click/type in THIS tab only, one controller at a time,
                and the user can take over or stop at any moment.
Every access is recorded in the tab's timeline (shown in the browser). Revoking takes effect immediately.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import threading

AGENTS = ("codex", "claude")
NAMES = {"codex": "Kaguya", "claude": "Miwa", "user": "Você"}


class AccessDenied(PermissionError):
    pass


@dataclass
class TabShare:
    tab_id: int
    readers: set[str] = field(default_factory=set)
    controllers: set[str] = field(default_factory=set)   # allowed to take control
    controller: str = "user"                              # who holds control now
    held: bool = False                                    # the user took over: assistants wait until handed back
    owner: str = ""                                       # research tab opened by an assistant ("" = user's tab)
    since: dict[str, str] = field(default_factory=dict)
    timeline: list[tuple[str, str, str]] = field(default_factory=list)   # (time, who, what)

    @property
    def shared(self) -> bool:
        return bool(self.readers)


class ShareRegistry:
    def __init__(self, on_change=None):
        self._tabs: dict[int, TabShare] = {}
        self._lock = threading.RLock()
        self.on_change = on_change or (lambda tab_id: None)

    def tab(self, tab_id: int) -> TabShare:
        with self._lock:
            return self._tabs.setdefault(tab_id, TabShare(tab_id))

    def log(self, tab_id: int, who: str, what: str) -> None:
        with self._lock:
            self.tab(tab_id).timeline.append((datetime.now().strftime("%H:%M:%S"), who, what))
            del self.tab(tab_id).timeline[:-200]
        self.on_change(tab_id)

    # ----------------------------------------------------------------- reading
    def share(self, tab_id: int, agent: str, on: bool = True) -> None:
        if agent not in AGENTS:
            raise ValueError(agent)
        with self._lock:
            t = self.tab(tab_id)
            if on and agent not in t.readers:
                t.readers.add(agent)
                t.since[agent] = datetime.now().strftime("%H:%M")
                self.log(tab_id, "user", f"compartilhou a aba com {NAMES[agent]}")
            elif not on and agent in t.readers:
                t.readers.discard(agent)
                t.since.pop(agent, None)
                self.allow_control(tab_id, agent, False)
                self.log(tab_id, "user", f"parou de compartilhar com {NAMES[agent]}")

    def can_read(self, tab_id: int, agent: str) -> bool:
        with self._lock:
            return agent in self.tab(tab_id).readers

    def check_read(self, tab_id: int, agent: str, what: str = "leu a página") -> None:
        if not self.can_read(tab_id, agent):
            self.log(tab_id, agent, "tentou ler a aba sem permissão (negado)")
            raise AccessDenied(f"Esta aba não está compartilhada com {NAMES.get(agent, agent)}.")
        self.log(tab_id, agent, what)

    # ----------------------------------------------------------------- control
    def allow_control(self, tab_id: int, agent: str, on: bool = True) -> None:
        with self._lock:
            t = self.tab(tab_id)
            if on:
                if agent not in t.readers:
                    raise AccessDenied("Compartilhe a aba antes de permitir o controle.")
                t.controllers.add(agent)
                t.held = False
                self.log(tab_id, "user", f"permitiu que {NAMES[agent]} controle esta aba (supervisionado)")
            elif agent in t.controllers:
                t.controllers.discard(agent)
                if t.controller == agent:
                    t.controller = "user"
                self.log(tab_id, "user", f"retirou o controle de {NAMES[agent]}")

    def take_control(self, tab_id: int, who: str) -> None:
        """One controller per tab. The user can always take it back."""
        with self._lock:
            t = self.tab(tab_id)
            if who == "user":
                if t.controller != "user":
                    prev = t.controller
                    t.controller = "user"
                    self.log(tab_id, "user", f"assumiu o controle (de {NAMES.get(prev, prev)})")
                t.held = True
                return
            if t.held:
                raise AccessDenied("O usuário assumiu o controle desta aba. Pare e espere ele devolver.")
            if who not in t.controllers:
                self.log(tab_id, who, "tentou controlar a aba sem permissão (negado)")
                raise AccessDenied(f"{NAMES.get(who, who)} não tem permissão para controlar esta aba.")
            if t.controller not in ("user", who):
                raise AccessDenied(f"{NAMES[t.controller]} já está controlando esta aba.")
            if t.controller != who:
                t.controller = who
                self.log(tab_id, who, "assumiu o controle da aba")

    def check_control(self, tab_id: int, agent: str, what: str) -> None:
        """The first action of an allowed assistant takes control (if nobody else holds it)."""
        with self._lock:
            t = self.tab(tab_id)
            if agent not in t.controllers:
                self.log(tab_id, agent, f"tentou '{what}' sem permissão (negado)")
                raise AccessDenied(f"{NAMES.get(agent, agent)} não pode controlar esta aba.")
            if t.controller != agent:
                self.take_control(tab_id, agent)
        self.log(tab_id, agent, what)

    def give_back(self, tab_id: int) -> None:
        with self._lock:
            t = self.tab(tab_id)
            if t.held:
                t.held = False
                self.log(tab_id, "user", "devolveu o controle")

    def stop_control(self, tab_id: int | None = None) -> None:
        """'Parar': every assistant loses control (sharing for reading stays)."""
        with self._lock:
            ids = [tab_id] if tab_id is not None else list(self._tabs)
            for i in ids:
                for a in list(self.tab(i).controllers):
                    self.allow_control(i, a, False)
                self.tab(i).controller = "user"

    def release(self, tab_id: int) -> None:
        with self._lock:
            self.tab(tab_id).controller = "user"

    def revoke_all(self, tab_id: int | None = None) -> None:
        with self._lock:
            ids = [tab_id] if tab_id is not None else list(self._tabs)
            for i in ids:
                for a in list(self.tab(i).readers):
                    self.share(i, a, False)

    def closed(self, tab_id: int) -> None:
        with self._lock:
            self._tabs.pop(tab_id, None)

    def shared_tabs(self, agent: str | None = None) -> list[int]:
        with self._lock:
            return [i for i, t in self._tabs.items() if t.readers and (agent is None or agent in t.readers)]
