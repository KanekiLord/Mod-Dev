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
    is_url = bool(re.match(r"^(https?|mailto|whatsapp|ms-[a-z-]+):", target, re.I))
    if not is_url:
        path = Path(os.path.expandvars(os.path.expanduser(target)))
        if not path.exists():
            raise ValueError(f"Não encontrei: {path}. Use o caminho completo (ex.: {Path.home() / 'Downloads'}).")
        if path.suffix.lower() in EXECUTABLE and not ask_user(control.control_dir(), f"Executar o programa {path.name}?"):
            raise ValueError("O usuário não autorizou executar esse programa.")
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
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


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
    items = load_alarms(base)
    items.append(item)
    save_alarms(base, items)
    return item


def due_alarms(base: Path, now: float | None = None) -> list[dict]:
    """Remove and return the alarms whose time has come."""
    now = now or time.time()
    items = load_alarms(base)
    due = [i for i in items if i["at"] <= now]
    if due:
        save_alarms(base, [i for i in items if i["at"] > now])
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
    """Ask the Studio to show a Yes/No question; wait for the answer (no answer = no)."""
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
