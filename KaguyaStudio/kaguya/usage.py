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
from pathlib import Path
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
        self.on_notification = None
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
            elif "method" in msg and "id" not in msg and self.on_notification:
                try:
                    self.on_notification(msg)
                except Exception:
                    pass

    def request(self, method: str, params: dict | None = None) -> dict:
        """``params=None`` omits the field (older Codex versions expect *unit* params)."""
        self._next += 1
        rid = self._next
        payload = {"id": rid, "method": method}
        if params is not None:
            payload["params"] = params
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(payload) + "\n")
        self.proc.stdin.flush()
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            try:
                msg = self.responses.get(timeout=0.25)
            except queue.Empty:
                if self.proc.poll() is not None and not self._reader.is_alive() and self.responses.empty():
                    raise OSError(f"o 'codex app-server' encerrou (código {self.proc.returncode}); "
                                  "esta versão pode não ter o servidor de app")
                continue
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
        for stream in (self.proc.stdout, self.proc.stderr):
            try:
                if stream:
                    stream.close()
            except OSError:
                pass


def _g(d: dict, *keys, default=None):
    """First present key (camelCase in new Codex, snake_case in older versions/rollouts)."""
    for k in keys:
        if isinstance(d, dict) and d.get(k) is not None:
            return d[k]
    return default


def _window_from(w: dict, fallback: str, ref_time: float | None = None) -> Window | None:
    used = _g(w, "usedPercent", "used_percent")
    if used is None:
        return None
    minutes = _g(w, "windowDurationMins", "window_minutes", "windowMinutes")
    resets = _g(w, "resetsAt", "resets_at")
    if resets is None and _g(w, "resets_in_seconds", "resetsInSeconds") is not None:
        resets = (ref_time or time.time()) + float(_g(w, "resets_in_seconds", "resetsInSeconds"))
    return Window(_window_label(minutes, fallback), float(used), float(resets) if resets else None, minutes)


def codex_snapshot_from_response(result: dict, plan: str = "", source: str = "Codex app-server • account/rateLimits/read",
                                 captured_at: float | None = None) -> UsageSnapshot:
    snap = UsageSnapshot("codex", True, source, captured_at=captured_at or time.time(), plan=plan)
    buckets = []
    by_id = _g(result, "rateLimitsByLimitId", "rate_limits_by_limit_id") or {}
    if isinstance(by_id, dict) and by_id:
        buckets = list(by_id.values())
    elif _g(result, "rateLimits", "rate_limits"):
        buckets = [_g(result, "rateLimits", "rate_limits")]
    elif _g(result, "primary"):
        buckets = [result]
    for b in buckets:
        if not isinstance(b, dict):
            continue
        label = _g(b, "limitName", "limit_name", default="") or ""
        for key, fallback in (("primary", "Janela principal"), ("secondary", "Janela secundária")):
            w = b.get(key)
            if isinstance(w, dict):
                win = _window_from(w, fallback, captured_at)
                if win:
                    if label and len(buckets) > 1:
                        win.name = f"{label} • {win.name}"
                    snap.windows.append(win)
        snap.plan = snap.plan or str(_g(b, "planType", "plan_type", default="") or "")
        if _g(b, "rateLimitReachedType", "rate_limit_reached_type"):
            snap.blocked = True
    if result.get("ordinaryUsageAllowed") is False:
        snap.blocked = True
    if not snap.windows:
        snap.available = False
        snap.message = "O Codex respondeu, mas não informou janelas de uso para esta conta."
    return snap


def codex_home(env: dict | None = None) -> Path:
    env = env or os.environ
    return Path(env.get("CODEX_HOME") or (Path.home() / ".codex"))


def read_codex_rollout_limits(home: Path | None = None, max_files: int = 12) -> UsageSnapshot:
    """Latest rate-limit snapshot the official Codex wrote in its own session logs
    (``~/.codex/sessions/AAAA/MM/DD/rollout-*.jsonl``). Local file, no credentials involved."""
    base = Path(home or codex_home()) / "sessions"
    files = sorted(base.glob("*/*/*/rollout-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:max_files] \
        if base.is_dir() else []
    for f in files:
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            if "rate_limits" not in line and "rateLimits" not in line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            payload = obj.get("payload") or obj.get("msg") or obj
            limits = _g(payload, "rate_limits", "rateLimits")
            if not isinstance(limits, dict):
                continue
            ts = obj.get("timestamp")
            when = None
            if isinstance(ts, str):
                try:
                    when = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                except ValueError:
                    when = None
            snap = codex_snapshot_from_response({"rateLimits": limits}, source="Codex • registro da última sessão oficial",
                                                captured_at=when or f.stat().st_mtime)
            if snap.windows:
                return snap
    return UsageSnapshot("codex", False, "Codex • registro local",
                         message="Nenhuma sessão do Codex com dados de uso encontrada neste computador.")


def _request_compat(client: "AppServerClient", method: str, params: dict | None) -> dict:
    res = client.request(method, params)
    err = str((res.get("error") or {}).get("message", ""))
    if "invalid type" in err or "missing field `params`" in err:
        res = client.request(method, None if params is not None else {})
    return res


def read_codex_limits(executable: str, env: dict | None = None, timeout: float = 25) -> UsageSnapshot:
    live = _read_codex_app_server(executable, env, timeout)
    if live.available or "sem login" in live.message or "API key" in live.message:
        return live
    local = read_codex_rollout_limits(codex_home(env))
    if local.available:
        local.message = f"Consulta direta indisponível ({live.message[:120]}); usando o registro oficial local."
        return local
    return live


def _read_codex_app_server(executable: str, env: dict | None, timeout: float) -> UsageSnapshot:
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
        acct = _request_compat(client, "account/read", {"refreshToken": False})
        account = (acct.get("result") or {}).get("account") if "result" in acct else None
        if isinstance(account, dict):
            plan = str(account.get("planType") or "")
            if account.get("type") == "apiKey":
                return UsageSnapshot("codex", False, "Codex app-server • account/read",
                                     message="O Codex está usando API key (cobrança por uso); não há cota de assinatura.")
        if "result" in acct and account is None:
            return UsageSnapshot("codex", False, "Codex app-server • account/read",
                                 message="Codex sem login de conta ChatGPT: faça 'codex login'.")
        # No params: accepted by older versions (unit) and by newer ones (nullable params).
        res = _request_compat(client, "account/rateLimits/read", None)
        if "error" in res:
            return UsageSnapshot("codex", False, "Codex app-server • account/rateLimits/read",
                                 message=str(res["error"].get("message", "erro")))
        return codex_snapshot_from_response(res.get("result") or {}, plan)
    except (TimeoutError, OSError, ValueError) as exc:
        return UsageSnapshot("codex", False, "Codex app-server",
                             message=f"Sem resposta do Codex ({exc}).")
    finally:
        client.close()


def claude_payload(info: dict) -> dict:
    """Normalise a Claude Code ``rate_limit_event`` (utilization 0..1) for storage."""
    payload = {"raw": info, "status": info.get("status"), "windows": {}}
    for name, win in (info.get("unifiedWindows") or {}).items():
        if isinstance(win, dict) and win.get("utilization") is not None:
            payload["windows"][name] = {"used_percent": round(float(win["utilization"]) * 100, 1),
                                        "resets_at": win.get("resetsAt")}
    if info.get("rateLimitType") and info.get("utilization") is not None:
        payload["windows"].setdefault(info["rateLimitType"], {"used_percent": round(float(info["utilization"]) * 100, 1),
                                                              "resets_at": info.get("resetsAt")})
    if info.get("status") == "rejected":
        payload["blocked"] = True
        payload["blocked_until"] = info.get("resetsAt")
    return payload


def probe_claude_limits(executable: str, caps, cwd: Path, env: dict | None = None, timeout_s: float = 120) -> dict | None:
    """One minimal message (cheapest model, no tools) so Claude Code returns its official
    ``rate_limit_event``. Spends a tiny part of the subscription: the UI asks first."""
    from .cli.runner import run_command
    cmd = [executable, "-p", "--output-format", "stream-json", "--verbose", "--model", "haiku",
           "--permission-mode", "dontAsk" if (not caps.flags or caps.mentions("dontAsk")) else "default"]
    if not caps.flags or caps.has("--tools"):
        cmd += ["--tools", ""]
    if not caps.flags or caps.has("--no-session-persistence"):
        cmd.append("--no-session-persistence")
    res = run_command("claude", cmd, Path(cwd), "Responda apenas: ok", lambda e: None, env=env, timeout_s=timeout_s)
    if res.rate_limits:
        return claude_payload(res.rate_limits[-1])
    if not res.ok:
        raise RuntimeError(res.failure_reason() or "O Claude Code não respondeu.")
    return None


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
