"""Subscription limits from official clients only — never invented numbers.

* Codex: ``codex app-server`` (the JSON-RPC server the official IDE extension uses) answers
  ``account/rateLimits/read`` with used % and reset time of each window. Verified against
  codex-cli 0.172: without login it returns "codex account authentication required".
  Only *read* methods are called (never ``account/rateLimitResetCredit/consume``).
* Claude Code: ``stream-json`` emits ``rate_limit_event`` (utilization 0..1, resetsAt epoch)
  during real runs; the latest event is stored. There is no read-only query, so when none
  was received the panel says "indisponível" and offers ``/usage`` and the official page.

Local measurements (tokens of runs made by the Studio) are reported separately and are
never presented as the account balance.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
import json
import os
import queue
import subprocess
import threading
import time

from . import VERSION
from .env import child_env

OFFICIAL_PAGES = {
    "codex": [("Uso do Codex (ChatGPT)", "https://chatgpt.com/codex/settings/usage"),
              ("Ajuda: Codex com plano ChatGPT", "https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan")],
    "claude": [("Uso do Claude (Configurações › Uso)", "https://claude.ai/settings/usage"),
               ("Boas práticas de limites", "https://support.claude.com/en/articles/9797557-usage-limit-best-practices")],
}
INTERACTIVE_HINT = {"codex": "/status (no Codex interativo)", "claude": "/usage (no Claude Code interativo)"}

WINDOW_NAMES = {"five_hour": "Janela de 5 horas", "seven_day": "Semanal (7 dias)", "seven_day_opus": "Semanal • Opus",
                "seven_day_sonnet": "Semanal • Sonnet", "seven_day_overage_included": "Semanal (incluído)",
                "overage": "Uso extra"}


@dataclass
class Window:
    name: str
    used_percent: float
    resets_at: float | None = None
    window_minutes: int | None = None

    @property
    def remaining_percent(self) -> float:
        return max(0.0, 100.0 - self.used_percent)

    def reset_text(self) -> str:
        if not self.resets_at:
            return "renovação não informada"
        dt = datetime.fromtimestamp(self.resets_at)
        delta = dt - datetime.now()
        if delta.total_seconds() <= 0:
            return "já renovou (dado antigo)"
        hours = delta.total_seconds() / 3600
        rel = f"em {int(delta.total_seconds() // 60)} min" if hours < 1 else f"em {hours:.1f} h" if hours < 48 else f"em {hours / 24:.1f} dias"
        return f"renova {dt.strftime('%d/%m %H:%M')} ({rel})"


@dataclass
class UsageSnapshot:
    agent: str
    available: bool
    source: str
    windows: list[Window] = field(default_factory=list)
    plan: str = ""
    captured_at: float | None = None
    message: str = ""
    blocked: bool = False

    def age_text(self) -> str:
        if not self.captured_at:
            return ""
        mins = int((time.time() - self.captured_at) // 60)
        return "agora" if mins < 1 else f"há {mins} min" if mins < 120 else f"há {mins // 60} h"

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def _window_label(minutes: int | None, fallback: str) -> str:
    if not minutes:
        return fallback
    if minutes == 300:
        return "Janela de 5 horas"
    if minutes == 10080:
        return "Semanal (7 dias)"
    if minutes % 1440 == 0:
        return f"Janela de {minutes // 1440} dia(s)"
    if minutes % 60 == 0:
        return f"Janela de {minutes // 60} h"
    return f"Janela de {minutes} min"


class AppServerClient:
    """Minimal JSON-RPC (newline-delimited) client for ``codex app-server`` over stdio."""

    def __init__(self, executable: str, env: dict | None = None, timeout: float = 25):
        self.exe, self.timeout = executable, timeout
        run_env, _ = child_env(env)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        self.proc = subprocess.Popen([executable, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                                     bufsize=1, env=run_env, creationflags=flags)
        self.responses: "queue.Queue[dict]" = queue.Queue()
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()
        self._next = 0

    def _read(self):
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if "id" in msg and ("result" in msg or "error" in msg):
                self.responses.put(msg)

    def request(self, method: str, params: dict | None = None) -> dict:
        self._next += 1
        rid = self._next
        payload = {"id": rid, "method": method, "params": params or {}}
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(payload) + "\n")
        self.proc.stdin.flush()
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            try:
                msg = self.responses.get(timeout=max(0.05, deadline - time.monotonic()))
            except queue.Empty:
                break
            if msg.get("id") == rid:
                return msg
        raise TimeoutError(f"codex app-server não respondeu a {method}")

    def notify(self, method: str) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps({"method": method}) + "\n")
        self.proc.stdin.flush()

    def close(self):
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.terminate()
            self.proc.wait(5)
        except (OSError, subprocess.TimeoutExpired):
            try:
                self.proc.kill()
            except OSError:
                pass


def codex_snapshot_from_response(result: dict, plan: str = "") -> UsageSnapshot:
    snap = UsageSnapshot("codex", True, "Codex app-server • account/rateLimits/read", captured_at=time.time(), plan=plan)
    buckets = []
    by_id = result.get("rateLimitsByLimitId") or {}
    if isinstance(by_id, dict) and by_id:
        buckets = list(by_id.values())
    elif result.get("rateLimits"):
        buckets = [result["rateLimits"]]
    for b in buckets:
        if not isinstance(b, dict):
            continue
        label = b.get("limitName") or ""
        for key, fallback in (("primary", "Janela principal"), ("secondary", "Janela secundária")):
            w = b.get(key)
            if isinstance(w, dict) and w.get("usedPercent") is not None:
                name = _window_label(w.get("windowDurationMins"), fallback)
                if label and len(buckets) > 1:
                    name = f"{label} • {name}"
                snap.windows.append(Window(name, float(w["usedPercent"]), w.get("resetsAt"), w.get("windowDurationMins")))
        snap.plan = snap.plan or str(b.get("planType") or "")
        if b.get("rateLimitReachedType"):
            snap.blocked = True
    if result.get("ordinaryUsageAllowed") is False:
        snap.blocked = True
    if not snap.windows:
        snap.available = False
        snap.message = "O Codex respondeu, mas não informou janelas de uso para esta conta."
    return snap


def read_codex_limits(executable: str, env: dict | None = None, timeout: float = 25) -> UsageSnapshot:
    try:
        client = AppServerClient(executable, env, timeout)
    except OSError as exc:
        return UsageSnapshot("codex", False, "Codex app-server", message=f"Não foi possível iniciar o Codex: {exc}")
    try:
        init = client.request("initialize", {"clientInfo": {"name": "kaguya_studio", "title": "Kaguya Studio",
                                                            "version": VERSION}})
        if "error" in init:
            return UsageSnapshot("codex", False, "Codex app-server", message="initialize: " + str(init["error"].get("message")))
        client.notify("initialized")
        plan = ""
        acct = client.request("account/read", {"refreshToken": False})
        account = (acct.get("result") or {}).get("account") if "result" in acct else None
        if isinstance(account, dict):
            plan = str(account.get("planType") or "")
            if account.get("type") == "apiKey":
                return UsageSnapshot("codex", False, "Codex app-server • account/read",
                                     message="O Codex está usando API key (cobrança por uso); não há cota de assinatura.")
        if "result" in acct and account is None:
            return UsageSnapshot("codex", False, "Codex app-server • account/read",
                                 message="Codex sem login de conta ChatGPT: faça 'codex login'.")
        res = client.request("account/rateLimits/read", {"excludeResetCreditDetails": True})
        if "error" in res:
            return UsageSnapshot("codex", False, "Codex app-server • account/rateLimits/read",
                                 message=str(res["error"].get("message", "erro")))
        return codex_snapshot_from_response(res.get("result") or {}, plan)
    except (TimeoutError, OSError, ValueError) as exc:
        return UsageSnapshot("codex", False, "Codex app-server",
                             message=f"Indisponível nesta versão do Codex ou sem resposta ({exc}). Use /status.")
    finally:
        client.close()


def claude_snapshot(stored: dict | None) -> UsageSnapshot:
    if not stored:
        return UsageSnapshot("claude", False, "Claude Code (stream-json rate_limit_event)",
                             message="Ainda não há dado oficial: o Claude Code envia a utilização durante as tarefas. "
                                     "Execute uma tarefa ou consulte /usage.")
    p = stored["payload"]
    try:
        captured = datetime.fromisoformat(stored["captured_at"]).timestamp()
    except (KeyError, ValueError):
        captured = None
    snap = UsageSnapshot("claude", True, stored.get("source", "Claude Code"), captured_at=captured,
                         blocked=bool(p.get("blocked")))
    for key, w in (p.get("windows") or {}).items():
        snap.windows.append(Window(WINDOW_NAMES.get(key, key), float(w.get("used_percent", 0)), w.get("resets_at")))
    if not snap.windows:
        snap.available = False
        status = p.get("status")
        snap.message = ("O cliente oficial informou o estado '" + str(status) + "', sem percentuais.") if status else \
            "O evento recebido não trazia percentuais."
    return snap


def local_summary(store, agent: str, hours: int = 5) -> dict:
    since = (datetime.now().astimezone() - timedelta(hours=hours)).isoformat(timespec="seconds")
    return store.local_usage_since(agent, since)
