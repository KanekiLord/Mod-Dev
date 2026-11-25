"""One Kaguya Studio per user: opening it again shows the running window (it may be in the tray), and the
installer can ask the running copy to exit before updating files (``KaguyaStudio.exe --sair``)."""
from __future__ import annotations

import hashlib

from PySide6.QtCore import QByteArray
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def server_name() -> str:
    from ..appdirs import data_dir
    digest = hashlib.sha1(str(data_dir()).lower().encode("utf-8")).hexdigest()[:12]
    return f"KaguyaStudio-{digest}"


def send(message: str, timeout_ms: int = 1500) -> bool:
    """Deliver a command to the running copy. False when no copy is running."""
    sock = QLocalSocket()
    sock.connectToServer(server_name())
    if not sock.waitForConnected(timeout_ms):
        return False
    sock.write(QByteArray((message + "\n").encode("utf-8")))
    sock.flush()
    sock.waitForBytesWritten(timeout_ms)
    ok = sock.waitForReadyRead(timeout_ms) and bytes(sock.readAll()).startswith(b"ok")
    sock.disconnectFromServer()
    return ok


class InstanceServer(QLocalServer):
    def __init__(self, handler, parent=None):
        super().__init__(parent)
        self.handler = handler
        QLocalServer.removeServer(server_name())  # stale socket from a crashed run
        self.listen(server_name())
        self.newConnection.connect(self._accept)

    def _accept(self):
        while self.hasPendingConnections():
            sock = self.nextPendingConnection()
            sock.readyRead.connect(lambda s=sock: self._read(s))

    def _read(self, sock):
        if not sock.canReadLine():
            return
        msg = bytes(sock.readLine()).decode("utf-8", "replace").strip()
        sock.write(QByteArray(b"ok\n"))
        sock.flush()
        sock.disconnectFromServer()
        self.handler(msg)
