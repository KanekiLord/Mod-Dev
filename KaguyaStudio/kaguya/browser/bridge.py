"""Bridge between the browser tools (MCP server run by Claude Code / Codex) and the Studio's browser.

The Studio listens on 127.0.0.1 only (never the network) on a random port. Each task that may control the browser
gets its own random token bound to one assistant; the token dies when the task ends. Every request is checked by the
Studio itself (ShareRegistry): the assistant cannot read a tab that was not shared with it, nor act on a tab it was
not allowed to control, whatever the tool server or the model try.

Protocol: one JSON line per request ``{"token", "tool", "args"}`` → one JSON line ``{"ok", "text"}``.
"""
from __future__ import annotations

import json
import secrets
import threading


class Tokens:
    def __init__(self):
        self._lock = threading.Lock()
        self._tokens: dict[str, tuple[str, int | None]] = {}

    def issue(self, agent: str, task_id: int | None = None) -> str:
        tok = secrets.token_hex(24)
        with self._lock:
            self._tokens[tok] = (agent, task_id)
        return tok

    def agent(self, token: str) -> str | None:
        with self._lock:
            entry = self._tokens.get(token or "")
        return entry[0] if entry else None

    def revoke(self, token: str) -> None:
        with self._lock:
            self._tokens.pop(token, None)

    def revoke_all(self) -> None:
        with self._lock:
            self._tokens.clear()


def make_bridge(handler, parent=None, closed_msg: str = "Acesso ao navegador do Studio encerrado (a tarefa terminou "
                                                            "ou o usuário parou)."):
    """Qt TCP server on localhost. ``handler(agent, tool, args, reply)`` must eventually call ``reply(ok, text)``
    (it may answer later, e.g. after the user confirms something)."""
    from PySide6.QtCore import QObject
    from PySide6.QtNetwork import QHostAddress, QTcpServer

    class Bridge(QObject):
        def __init__(self):
            super().__init__(parent)
            self.tokens = Tokens()
            self.server = QTcpServer(self)
            self.server.newConnection.connect(self._accept)
            if not self.server.listen(QHostAddress.LocalHost, 0):
                raise RuntimeError("não foi possível abrir a ponte local do Studio")
            self.port = int(self.server.serverPort())

        def _accept(self):
            while self.server.hasPendingConnections():
                sock = self.server.nextPendingConnection()
                sock.setParent(self)
                buf = bytearray()

                def ready(sock=sock, buf=buf):
                    buf.extend(bytes(sock.readAll()))
                    while b"\n" in buf:
                        line, _, rest = bytes(buf).partition(b"\n")
                        buf[:] = rest
                        self._request(sock, line)
                sock.readyRead.connect(ready)
                sock.disconnected.connect(sock.deleteLater)

        def _request(self, sock, line: bytes):
            def reply(ok: bool, text: str):
                try:
                    if sock.state() == sock.SocketState.ConnectedState:
                        sock.write((json.dumps({"ok": bool(ok), "text": text}, ensure_ascii=False) + "\n").encode())
                        sock.flush()
                except RuntimeError:   # socket already deleted (client gave up)
                    pass
            try:
                req = json.loads(line.decode("utf-8"))
            except ValueError:
                reply(False, "pedido inválido")
                return
            agent = self.tokens.agent(req.get("token", ""))
            if agent is None:
                reply(False, closed_msg)
                return
            try:
                handler(agent, str(req.get("tool", "")), dict(req.get("args") or {}), reply)
            except Exception as exc:   # never crash the Studio because of a tool call
                reply(False, f"{type(exc).__name__}: {exc}")

        def close(self):
            self.tokens.revoke_all()
            self.server.close()

    return Bridge()
