"""Personal-assistant helpers for "Meu computador" mode (used by the desktop MCP server process).

* open files, folders, sites and apps through Windows' own "open" (no shell commands);
* timers, reminders and alarms owned by the Studio (it shows the mascot, speaks and notifies);
* calendar events as standard .ics files opened in the user's calendar app;
* ``ask_user``: a Yes/No question shown by the Studio — required before sending messages, deleting
  files or running programs, because a misheard voice command must never become an irreversible action.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid

from . import control

ALARMS = "lembretes.json"
REQUESTS = "pedidos"
EXECUTABLE = {".exe", ".bat", ".cmd", ".ps1", ".vbs", ".msi", ".scr", ".com", ".js", ".jar", ".reg", ".lnk"}
# opened without asking: documents, media, archives and the calendar files the Studio creates. Anything else
# (.hta, .cpl, .msc, .wsf, .url, .appref-ms, .html…) may run code → asks first, like a program.
SAFE_FILES = {".txt", ".md", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".ico", ".mp3", ".wav",
              ".ogg", ".flac", ".m4a", ".aac", ".mp4", ".mkv", ".webm", ".avi", ".mov", ".docx", ".xlsx", ".pptx",
              ".odt", ".ods", ".odp", ".csv", ".json", ".log", ".ics", ".zip", ".7z", ".rar", ".blend", ".bbmodel",
              ".obj", ".fbx", ".glb", ".gltf", ".psd", ".kra", ".aseprite"}
SAFE_SCHEMES = ("https", "http", "mailto", "whatsapp", "ms-settings")   # ms-msdt:, search-ms:… are refused
BLOCKED_APPS = ("regedit", "editor do registro", "gpedit", "diskpart", "bios", "format")


def _fake() -> bool:
    return os.environ.get("KAGUYA_DESKTOP_BACKEND") == "fake"


def _fake_log(**kw):
    p = os.environ.get("KAGUYA_DESKTOP_FAKE_LOG")
    if p:
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(kw, ensure_ascii=False) + "\n")


def open_target(target: str) -> str:
    target = target.strip().strip('"')
    if not target:
        raise ValueError("Informe o arquivo, pasta ou site.")
    m = re.match(r"^([a-z][a-z0-9+.-]{1,30}):(?!\\)", target, re.I)
    is_url = bool(m) and not re.match(r"^[a-z]:[\\/]", target, re.I)       # "C:\..." is a path, not a scheme
    if is_url:
        if m.group(1).lower() not in SAFE_SCHEMES:
            raise ValueError(f"Endereços \"{m.group(1)}:\" não são abertos (podem executar programas do Windows).")
    else:
        path = Path(os.path.expandvars(os.path.expanduser(target)))
        if not path.exists():
            raise ValueError(f"Não encontrei: {path}. Use o caminho completo (ex.: {Path.home() / 'Downloads'}).")
        suffix = path.suffix.lower()
        if not path.is_dir() and suffix not in SAFE_FILES:
            what = (f"Executar o programa {path.name}?" if suffix in EXECUTABLE else
                    f"Abrir {path.name}? Arquivos {suffix or 'sem extensão'} podem executar programas.")
            if not ask_user(control.control_dir(), what):
                raise ValueError("O usuário não autorizou abrir esse arquivo.")
        target = str(path)
    if _fake():
        _fake_log(action="open", target=target)
    elif sys.platform == "win32":
        os.startfile(target)  # noqa: S606 — Windows' own "open" verb, no shell
    else:
        raise RuntimeError("Abrir arquivos e apps só está disponível no Windows.")
    return target


def check_app(name: str) -> None:
    if not name:
        raise ValueError("Informe o nome do aplicativo.")
    if any(b in name.lower() for b in BLOCKED_APPS):
        raise ValueError("Esse programa do sistema não pode ser aberto pelo assistente.")


# ------------------------------------------------------------------ alarms
def parse_when(when: str, now: datetime | None = None) -> datetime:
    now = now or datetime.now()
    w = when.strip().lower().replace("h", ":").replace("::", ":")
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})[ t](\d{1,2}):(\d{2})$", w)
    if m:
        return datetime(*map(int, m.groups()))
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?$", w.rstrip(":"))
    if m:
        at = now.replace(hour=int(m.group(1)), minute=int(m.group(2) or 0), second=0, microsecond=0)
        return at if at > now else at + timedelta(days=1)
    raise ValueError("Horário não entendido. Use \"HH:MM\" ou \"AAAA-MM-DD HH:MM\".")


def load_alarms(base: Path) -> list[dict]:
    try:
        return json.loads((control.control_dir(base) / ALARMS).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return []


def save_alarms(base: Path, items: list[dict]) -> None:
    p = control.control_dir(base) / ALARMS
    tmp = p.with_name(f"{p.stem}.{os.getpid()}.{uuid.uuid4().hex[:6]}.tmp")   # never shared between processes
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    for attempt in range(10):
        try:
            os.replace(tmp, p)
            return
        except PermissionError:          # Windows: the other process is reading it right now
            time.sleep(0.05 * (attempt + 1))
    os.replace(tmp, p)


class _AlarmsLock:
    """Read-modify-write of the reminders file by two processes (the assistant's tool server adds, the Studio
    removes the due ones) used to lose reminders. One lock file, created atomically; a stale one is broken."""

    def __init__(self, base: Path, timeout: float = 5):
        self.path = control.control_dir(base) / (ALARMS + ".lock")
        self.timeout = timeout

    def __enter__(self):
        end = time.monotonic() + self.timeout
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > 10:   # left by a process that died
                        self.path.unlink()
                        continue
                except OSError:
                    pass
                if time.monotonic() > end:
                    raise TimeoutError("Arquivo de lembretes ocupado; tente de novo.")
                time.sleep(0.02)

    def __exit__(self, *exc):
        try:
            self.path.unlink()
        except OSError:
            pass


def add_alarm(base: Path, *, minutes: float | None = None, when: str | None = None, text: str = "Lembrete",
              agent: str | None = None) -> dict:
    if minutes is not None:
        if not 0 < minutes <= 24 * 60:
            raise ValueError("O timer deve ter entre alguns segundos e 24 horas.")
        at = datetime.now() + timedelta(minutes=minutes)
        kind = "timer"
    else:
        at = parse_when(when or "")
        kind = "lembrete"
    item = {"id": uuid.uuid4().hex[:10], "at": at.timestamp(), "text": text.strip()[:200] or kind.capitalize(),
            "kind": kind, "agent": agent or os.environ.get("KAGUYA_DESKTOP_AGENT") or "codex",
            "at_text": at.strftime("%d/%m %H:%M") if at.date() != datetime.now().date() else at.strftime("%H:%M")}
    with _AlarmsLock(base):
        items = load_alarms(base)
        items.append(item)
        save_alarms(base, items)
    return item


def due_alarms(base: Path, now: float | None = None) -> list[dict]:
    """Remove and return the alarms whose time has come."""
    now = now or time.time()
    if not (control.control_dir(base) / ALARMS).exists():
        return []
    try:
        with _AlarmsLock(base, timeout=1):
            items = load_alarms(base)
            due = [i for i in items if i["at"] <= now]
            if due:
                save_alarms(base, [i for i in items if i["at"] > now])
    except TimeoutError:
        return []                         # busy: the next check (in under a second) gets them
    return due


# ------------------------------------------------------------------ calendar
def _ics_time(text: str) -> str:
    return parse_when(text).strftime("%Y%m%dT%H%M%S")


def create_event(base: Path, title: str, start: str, end: str = "", location: str = "") -> Path:
    if not title.strip():
        raise ValueError("Informe o título do evento.")
    s = parse_when(start)
    e = parse_when(end) if end else s + timedelta(hours=1)

    def esc(v):
        return v.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    ics = "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Kaguya Studio//PT-BR", "BEGIN:VEVENT",
        f"UID:{uuid.uuid4()}@kaguya-studio", f"DTSTAMP:{datetime.now().strftime('%Y%m%dT%H%M%S')}",
        f"DTSTART:{s.strftime('%Y%m%dT%H%M%S')}", f"DTEND:{e.strftime('%Y%m%dT%H%M%S')}",
        f"SUMMARY:{esc(title.strip())}"] + ([f"LOCATION:{esc(location)}"] if location else []) +
        ["END:VEVENT", "END:VCALENDAR", ""])
    folder = control.control_dir(base) / "agenda"
    folder.mkdir(exist_ok=True)
    safe = re.sub(r"[^\w\- ]", "", title)[:40].strip() or "evento"
    path = folder / f"{s.strftime('%Y-%m-%d_%H%M')} {safe}.ics"
    path.write_text(ics, encoding="utf-8")
    return path


# ------------------------------------------------------------------ confirmation
def ask_user(base: Path, action: str, timeout: float = 180) -> bool:
    """Ask the Studio to show a Yes/No question; wait for the answer (no answer = no).

    The answer comes back on the connection this process opened to the Studio (127.0.0.1, token of this task):
    only a click in the Studio's window produces it. It used to be a file in a folder the assistant can write to
    in "Meu computador" mode — the assistant could have answered "sim" to itself."""
    port = int(os.environ.get("KAGUYA_CONFIRM_PORT") or 0)
    token = os.environ.get("KAGUYA_CONFIRM_TOKEN", "")
    if port and token:
        return _ask_studio(port, token, action, timeout)
    if not _fake():
        return False            # no safe channel to the Studio: never assume "yes"
    return _ask_by_files(base, action, timeout)   # test double only (fake desktop backend)


def _ask_studio(port: int, token: str, action: str, timeout: float) -> bool:
    import socket
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=10) as s:
            s.settimeout(timeout)
            s.sendall((json.dumps({"token": token, "tool": "confirmar", "args": {"action": action[:600]}},
                                  ensure_ascii=False) + "\n").encode("utf-8"))
            buf = b""
            while b"\n" not in buf:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
        rep = json.loads(buf.split(b"\n", 1)[0].decode("utf-8"))
        return bool(rep.get("ok")) and rep.get("text") == "sim"
    except (OSError, ValueError):
        return False


def _ask_by_files(base: Path, action: str, timeout: float) -> bool:
    folder = control.control_dir(base) / REQUESTS
    folder.mkdir(exist_ok=True)
    rid = uuid.uuid4().hex[:12]
    req = folder / f"{rid}.json"
    tmp = folder / f"{rid}.tmp"
    tmp.write_text(json.dumps({"id": rid, "action": action[:600], "agent": os.environ.get("KAGUYA_DESKTOP_AGENT", ""),
                               "t": time.time()}, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, req)
    ans = folder / f"{rid}.resposta"
    end = time.monotonic() + timeout
    try:
        while time.monotonic() < end:
            if ans.exists():
                return ans.read_text(encoding="utf-8").strip().lower() == "sim"
            if control.stop_reason(base):
                return False
            time.sleep(0.25)
        return False
    finally:
        for p in (req, ans):
            try:
                p.unlink()
            except OSError:
                pass


def pending_requests(base: Path) -> list[dict]:
    folder = control.control_dir(base) / REQUESTS
    out = []
    for p in sorted(folder.glob("*.json")) if folder.exists() else []:
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    return out


def answer_request(base: Path, rid: str, yes: bool) -> None:
    folder = control.control_dir(base) / REQUESTS
    (folder / f"{rid}.resposta").write_text("sim" if yes else "nao", encoding="utf-8")
