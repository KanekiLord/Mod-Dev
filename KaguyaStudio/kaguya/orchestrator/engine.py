"""Task engine: queue worker per project, single-agent turns, Team (implement → verify →
review → fix … → verdict) and Parallel (Git worktrees) modes.

Qt-independent: the UI subscribes through ``listener(event: dict)``; callbacks may arrive
from worker threads.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import threading
import time
import traceback
from typing import Callable

from ..appdirs import CATALOG, data_dir
from ..cli import discovery
from .. import checkpoint
from ..desktop import control as desktop_control
from ..desktop.server import server_command
from ..cli.commands import RunOptions, claude_desktop_config
from ..cli.discovery import Capabilities, Diagnosis
from ..cli.events import AgentEvent, RunResult
from ..cli.runner import run_agent
from ..inventory import Inventory, scan, suggest_agents
from ..messages import Intent
from ..paths import check_project_folder
from ..prompts import attached_context, fix_prompt, parse_verdict, review_prompt, task_prompt
from ..quality import Check, run_checks, summarize, tests_passed
from ..store import Store
from ..vault.index import VaultIndex, context_block
from ..vault.knowledge import detect_version
from ..vault.outbox import Outbox, extract_learnings
from . import worktree

Listener = Callable[[dict], None]

DEFAULTS = {
    "economy.max_subagents": 2,
    "desktop.window": "Minecraft",   # computer use limited to this window by default ("" = whole screen)
    "desktop.max_actions": 400,
    "run.cancel_grace_s": 20,        # Cancelar frees the queue after this even if a program does not answer
    "hub.enabled": True,             # Extension Hub: capability list in prompts, real-session evidence, delegation, locks
    "team.max_cycles": 2,
    "team.implementer": "codex",
    "team.reviewer": "claude",
    "session.continue": True,
    "parallel.max_workers": 2,
    "agents.suggest": True,
    "memory.hits": 4,
    "run.timeout_min": 60,
    "models.codex": "",
    "models.claude": "",
    "models.review": "",
}


class TaskFailed(RuntimeError):
    def __init__(self, message: str, status: str = "error"):
        super().__init__(message)
        self.status = status


@dataclass
class ProjectRuntime:
    thread: threading.Thread | None = None
    cancel: threading.Event | None = None
    task_id: int | None = None
    finished: bool = False      # the loop decided to stop (the thread may still be returning)


class Engine:
    def __init__(self, store: Store, listener: Listener | None = None, home: Path | None = None,
                 env: dict[str, str] | None = None):
        self.store = store
        self.home = Path(home or data_dir())
        self.desktop_command = server_command()
        from ..browser.mcp import server_command as browser_server_command
        self.browser_command = browser_server_command()
        # set by the UI: (agent, task_id) -> {"port", "token"} or None, and the matching release(token)
        self._hub = None
        self.locks = None
        self.browser_bridge = None
        self.confirm_bridge = None        # Studio window that answers "confirm" (set by the UI)
        self.confirm_release = None
        self._confirm_tokens: dict[int, str] = {}
        self.browser_release = None
        self._browser_tokens: dict[int, str] = {}
        self.env = env
        self.listeners: list[Listener] = [listener] if listener else []
        self.diagnoses: dict[str, Diagnosis] = {}
        self.capabilities: dict[str, Capabilities] = {}
        self.runtimes: dict[int, ProjectRuntime] = {}
        self._lock = threading.RLock()
        self._indexes: dict[str, VaultIndex] = {}
        self._inventory: dict[int, Inventory] = {}
        cached = store.get_setting("cli.capabilities", {}) or {}
        for k, v in cached.items():
            self.capabilities[k] = Capabilities.from_dict(v)

    # ---------------------------------------------------------------- events
    def subscribe(self, listener: Listener) -> None:
        self.listeners.append(listener)

    def emit(self, event_type: str, /, **data) -> None:
        data["type"] = event_type
        for fn in list(self.listeners):
            try:
                fn(data)
            except Exception:  # a broken listener must never kill a worker
                traceback.print_exc()

    def setting(self, key: str):
        return self.store.get_setting(key, DEFAULTS.get(key))

    @property
    def packs(self) -> Path:
        """Folder of heavy downloads (models, voices) — the user's choice, see kaguya/packs.py."""
        from .. import packs
        return packs.current(self.store, self.home)

    # ------------------------------------------------------------ diagnostics
    def diagnose(self, target: str, cwd: str | None = None, cancel: threading.Event | None = None) -> Diagnosis:
        override = self.store.get_setting(f"cli.{target}.path") or None
        runner = None
        if cancel is not None:
            import functools
            from .. import procutil
            runner = functools.partial(procutil.run, cancel=cancel)   # Cancelar also stops the checks
        diag, caps = discovery.diagnose(target, cwd, override, env=self.env, runner=runner)
        with self._lock:
            self.diagnoses[target] = diag
            if caps.flags:
                self.capabilities[target] = caps
                self.store.set_setting("cli.capabilities", {k: v.to_dict() for k, v in self.capabilities.items()})
        self.store.set_setting(f"cli.{target}.last", diag.to_dict())
        self.emit("diagnosis", target=target, diagnosis=diag.to_dict())
        return diag

    def ensure_ready(self, target: str, cwd: str | None, cancel: threading.Event | None = None
                     ) -> tuple[str, Capabilities]:
        diag = self.diagnoses.get(target)
        if diag is None or not diag.usable:
            diag = self.diagnose(target, cwd, cancel)
        if cancel is not None and cancel.is_set():
            raise TaskFailed("Interrompido pelo usuário.", "cancelled")
        if not diag.usable:
            fixes = (" Como resolver: " + " ".join(diag.fixes)) if diag.fixes else ""
            raise TaskFailed(f"{target.capitalize()} não está pronto ({diag.label}). " + " ".join(diag.details) + fixes)
        return diag.executable or target, self.capabilities.get(target, Capabilities())

    def limit_block(self, target: str) -> str | None:
        """Refuse to start work when the official client already reported the limit as reached."""
        snap = self.store.latest_usage(target)
        if not snap:
            return None
        p = snap["payload"]
        resets = p.get("blocked_until")
        if p.get("blocked") and resets and float(resets) > time.time():
            when = datetime.fromtimestamp(float(resets)).strftime("%d/%m %H:%M")
            return f"Limite de uso de {target} atingido segundo o cliente oficial; renova por volta de {when}."
        return None

    # ---------------------------------------------------------------- memory
    def vault_index(self, vault: str | None) -> VaultIndex | None:
        if not vault or not Path(vault).is_dir():
            return None
        with self._lock:
            idx = self._indexes.get(vault)
            if idx is None:
                idx = VaultIndex(Path(vault), self.home)
                self._indexes[vault] = idx
        return idx

    @property
    def hub(self):
        """Extension Hub (catalogue of what Codex/Claude Code really have). Created on first use."""
        if self._hub is None:
            from ..hub.router import ResourceLocks
            from ..hub.service import HubService

            import shutil as _sh
            from ..hub.adapters import ClaudeAdapter, CodexAdapter

            def exes():
                """The same CLIs the Studio runs (official on the PC; test doubles in tests)."""
                path = (self.env or os.environ).get("PATH")
                out = {a: self.store.get_setting(f"cli.{a}.path") or _sh.which(a, path=path) for a in ("codex", "claude")}
                return {k: v for k, v in out.items() if v}
            base = os.environ.get("KAGUYA_HUB_HOME")      # tests: an isolated "user folder" for the clients' configs
            home = Path(base) if base else None
            found = exes()
            adapters = {"claude": ClaudeAdapter(home, exe=found.get("claude")),
                        "codex": CodexAdapter(home, exe=found.get("codex"))}
            self._hub = HubService(self.home, projects=lambda: [p["directory"] for p in self.store.projects()
                                                                 if not p.get("removed")], exes=exes, adapters=adapters)
            self.locks = ResourceLocks()
        return self._hub

    def outbox(self, pid: int) -> Outbox:
        """Review queue. Without a connected vault it still queues proposals (approved once the vault is linked)."""
        vault = self.store.effective_vault(pid)
        if not vault or not Path(vault).is_dir():
            return Outbox(None, self.home / "outbox", None, self.home / "backups" / "notas")
        return Outbox(Path(vault), self.home / "outbox", self.vault_index(vault), self.home / "backups" / "notas")

    def memory_for(self, pid: int, text: str) -> str:
        idx = self.vault_index(self.store.effective_vault(pid))
        if idx is None:
            return ""
        try:
            if idx.stats()["notes"] == 0:
                idx.update()
            hits = idx.search(text, limit=int(self.setting("memory.hits")))
            lessons = [h for h in idx.search("lições erros aprendizado " + text, limit=3)
                       if any(k in h.path.lower() for k in ("lesson", "licao", "lição", "erro", "aprendiz"))]
            seen = {h.path for h in hits}
            hits += [h for h in lessons if h.path not in seen]
            from ..vault.knowledge import context_meta
            for h in hits:   # tell the assistant how much to trust each note (status, confidence, version, source)
                h.meta = context_meta(idx.note(h.path) or "")
        except Exception as exc:  # index problems must not block the task
            self.emit("log", message=f"Busca no Segundo Cérebro falhou: {exc}")
            return ""
        return context_block(hits)

    def inventory(self, pid: int, refresh: bool = False) -> Inventory:
        if refresh or pid not in self._inventory:
            proj = self.store.project(pid)
            vault = self.store.effective_vault(pid)
            self._inventory[pid] = scan(Path(proj["directory"]), Path(vault) if vault else None, CATALOG)
        return self._inventory[pid]

    # ----------------------------------------------------------------- queue
    def submit(self, pid: int, intent: Intent, *, write: bool = False, web: bool = True, commands: bool = False,
               mcp: bool = False, run_tests: bool = False, autonomous: bool = False, desktop: bool = False,
               context: str = "", attachments: list[str] | None = None, browser: bool = False) -> int:
        if autonomous:
            # autonomous = everything needed to finish the task without asking (Git restore point first)
            write = commands = run_tests = True
        if self.store.is_pc(pid) and intent.kind == "execute":
            # personal assistant: files anywhere in the user's folder, commands, screen/mouse/keyboard;
            # irreversible actions go through the confirm tool (enforced by the prompt + denied shell patterns)
            write, commands, desktop, autonomous, run_tests = True, True, True, False, False
        tid = self.store.enqueue(pid, intent.target, intent.text, intent.kind, allow_write=write, allow_web=web,
                                 allow_commands=commands, allow_mcp=mcp, run_tests=run_tests, autonomous=autonomous,
                                 desktop=desktop and intent.target != "paralelo", context=context,
                                 attachments=attachments, browser=browser and intent.target in ("codex", "claude"))
        self.store.append_event(tid, "user", intent.text, "user")
        if intent.kind == "idea":
            ob = self.outbox(pid)
            if ob:
                note = ob.stage("ideia", intent.text[:80], intent.text, project=self.store.project(pid)["name"],
                                source=f"Kaguya Studio tarefa #{tid}")
                self.store.append_event(tid, "system", f"Ideia guardada como rascunho: {note.name}")
        if intent.subtasks:
            self.store.append_event(tid, "plan", json.dumps(intent.subtasks, ensure_ascii=False))
        self.emit("queued", pid=pid, task_id=tid, kind=intent.kind, target=intent.target)
        if intent.kind == "execute":
            self.start_worker(pid)
        return tid

    def is_running(self, pid: int) -> bool:
        rt = self.runtimes.get(pid)
        return bool(rt and rt.thread and rt.thread.is_alive() and not rt.finished)

    def current_task(self, pid: int) -> int | None:
        rt = self.runtimes.get(pid)
        return rt.task_id if rt and rt.thread and rt.thread.is_alive() else None

    def start_worker(self, pid: int) -> None:
        with self._lock:
            if self.is_running(pid):
                return
            rt = ProjectRuntime(cancel=threading.Event())
            rt.thread = threading.Thread(target=self._worker, args=(pid, rt), daemon=True, name=f"kaguya-p{pid}")
            self.runtimes[pid] = rt
            rt.thread.start()

    def cancel(self, pid: int, grace: float | None = None) -> bool:
        """Stop the running task. If it does not stop by itself within ``grace`` seconds (something outside
        the Studio not answering), the queue is released anyway: the task is marked cancelled and the next
        one can start — Cancelar always works."""
        rt = self.runtimes.get(pid)
        if rt and rt.cancel and rt.thread and rt.thread.is_alive():
            desktop_control.request_stop(self.home / "desktop", "tarefa interrompida")
            rt.cancel.set()
            wait = float(self.setting("run.cancel_grace_s") if grace is None else grace)
            threading.Thread(target=self._force_release, args=(pid, rt, wait), daemon=True,
                             name=f"kaguya-cancel-p{pid}").start()
            return True
        return False

    def _force_release(self, pid: int, rt: ProjectRuntime, wait: float) -> None:
        rt.thread.join(wait)
        if not rt.thread.is_alive():
            return
        with self._lock:
            if self.runtimes.get(pid) is not rt:
                return
            self.runtimes.pop(pid, None)     # the stuck thread is abandoned: its later results are discarded
        tid = rt.task_id
        if tid is not None:
            # free what it held so the next task does not wait on it: 3D-file lock, browser access, desktop
            if self.locks is not None:
                self.locks.release(f"tarefa #{tid}")
            tok = self._browser_tokens.pop(tid, None)
            if tok and self.browser_release:
                self.browser_release(tok)
            ctok = self._confirm_tokens.pop(tid, None)
            if ctok and self.confirm_release:
                self.confirm_release(ctok)
            self.emit("desktop", pid=pid, task_id=tid, active=False)
            self.store.append_event(tid, "warning", f"A tarefa não respondeu ao Cancelar em {int(wait)} s; a fila foi "
                                    "liberada mesmo assim (o processo travado foi abandonado).")
            self.store.complete(tid, "cancelled", "Interrompido pelo usuário (liberado à força).")
            self.emit("task_done", pid=pid, task_id=tid, status="cancelled", summary="Interrompido pelo usuário.")
        self.emit("worker_idle", pid=pid)

    def wait(self, pid: int, timeout: float = 60) -> None:
        rt = self.runtimes.get(pid)
        if rt and rt.thread:
            rt.thread.join(timeout)

    def _worker(self, pid: int, rt: ProjectRuntime) -> None:
        try:
            self._work_loop(pid, rt)
        finally:
            with self._lock:
                rt.finished = True       # from here on start_worker() starts a new worker
                mine = self.runtimes.get(pid) is rt
        if mine:                         # an abandoned (force-released) worker says nothing
            self.emit("worker_idle", pid=pid)

    def _work_loop(self, pid: int, rt: ProjectRuntime) -> None:
        while not rt.cancel.is_set():
            with self._lock:   # same lock as start_worker: a task queued now is either claimed here or gets a worker
                task = self.store.claim(pid)
                if task is None:
                    rt.finished = True
                    break
            rt.task_id = task["id"]
            self.emit("task_started", pid=pid, task_id=task["id"], target=task["target"], title=task["title"])
            status, summary = "error", ""
            held = False
            try:
                held = self._take_resources(pid, task, rt.cancel)
                if task.get("autonomous") and task["allow_write"] and task["target"] != "paralelo":
                    self._restore_point(pid, task)
                if task.get("desktop"):
                    desktop_control.reset(self.home / "desktop")
                    self.emit("desktop", pid=pid, task_id=task["id"], active=True, window=self._desktop_window(pid))
                if task["target"] == "equipe":
                    status, summary = self._run_team(pid, task, rt.cancel)
                elif task["target"] == "paralelo":
                    status, summary = self._run_parallel(pid, task, rt.cancel)
                else:
                    status, summary = self._run_single(pid, task, rt.cancel)
            except TaskFailed as exc:
                status, summary = exc.status, str(exc)
                self.store.append_event(task["id"], "error", summary, task["target"])
            except Exception as exc:
                status, summary = "error", f"Erro interno: {exc}"
                self.store.append_event(task["id"], "error", summary + "\n" + traceback.format_exc()[-3000:])
            if task.get("desktop"):
                self._finish_desktop(pid, task["id"])
            if held and self.locks is not None:
                self.locks.release(f"tarefa #{task['id']}")
            if status in ("executed", "approved", "pending_review"):
                self._delegate(pid, task, summary)
            tok = self._browser_tokens.pop(task["id"], None)
            if tok and self.browser_release:
                self.browser_release(tok)   # the assistant loses browser access the moment the task ends
            ctok = self._confirm_tokens.pop(task["id"], None)
            if ctok and self.confirm_release:
                self.confirm_release(ctok)
            if rt.cancel.is_set() and status not in ("approved",):
                status = "cancelled"
                summary = summary or "Interrompido pelo usuário."
            if self.runtimes.get(pid) is not rt:
                return                       # released by Cancelar while stuck: the task was already closed
            self.store.complete(task["id"], status, summary)
            self.emit("task_done", pid=pid, task_id=task["id"], status=status, summary=summary[-3000:])
            rt.task_id = None
            if status in ("error", "blocked_limit"):
                # don't burn limits on the rest of the queue after a failure
                self.emit("log", pid=pid, message="Fila pausada após falha; reative quando resolver o problema.")
                break

    # ------------------------------------------------------------ desktop
    def _desktop_window(self, pid: int | None = None) -> str:
        if self.store.is_pc(pid):
            return ""  # personal-assistant tasks use the whole screen (other apps, WhatsApp, calendar…)
        return str(self.setting("desktop.window") or "").strip()

    def _take_resources(self, pid: int, task: dict, cancel: threading.Event) -> bool:
        """One writer per 3D file/app (Blender, Blockbench): wait for the other task, back up the files first."""
        if not self.setting("hub.enabled"):
            return False
        from ..hub.router import backup, resources_for
        proj = self.store.project(pid)
        keys, files = resources_for(f"{task['title']}\n{task.get('context') or ''}", proj["directory"], self.hub.registry)
        if not keys:
            return False
        owner = f"tarefa #{task['id']}"
        waited = False
        while not cancel.is_set():
            busy = self.locks.acquire(keys, owner)
            if busy is None:
                break
            if not waited:
                self.store.append_event(task["id"], "system", f"Aguardando recurso em uso: {busy}")
                self.store.set_stage(task["id"], "aguardando recurso")
                waited = True
            cancel.wait(2)
        if cancel.is_set():
            raise TaskFailed("Interrompido enquanto esperava o recurso.", "cancelled")
        if files:
            saved = backup(files, self.home / "backups" / "3d")
            self.store.append_event(task["id"], "system", "Backup antes de mexer nos arquivos 3D: "
                                    + ", ".join(str(p) for p in saved))
        return True

    def _delegate(self, pid: int, task: dict, text: str) -> None:
        """[[DELEGAR:kaguya|miwa: pedido]] in an answer → a task for the other assistant (with its MCPs allowed)."""
        if not self.setting("hub.enabled") or task.get("target") not in ("codex", "claude"):
            return
        from ..hub.router import AGENTS, delegations
        from ..messages import Intent
        for target, request in delegations(text)[:3]:
            if target == task["target"]:
                continue
            if task["title"].startswith("[Pedido da"):
                self.store.append_event(task["id"], "warning", "Delegação em cadeia bloqueada (pedido já veio da outra IA).")
                continue
            who = AGENTS[task["target"]]
            title = f"[Pedido da {who}] {request}\n\n(Tarefa original #{task['id']}: {task['title'][:300]})"
            new = self.submit(pid, Intent("execute", target, title), write=False, web=True, commands=False, mcp=True)
            self.store.append_event(task["id"], "system", f"{who} pediu à {AGENTS[target]}: {request[:200]} (tarefa #{new})")
            self.emit("delegated", pid=pid, task_id=task["id"], new_task=new, target=target)

    def _hub_context(self, task: dict) -> str:
        if not self.setting("hub.enabled") or task.get("target") not in ("codex", "claude"):
            return ""
        try:
            from ..hub.router import context
            return context(self.hub.registry, task["target"])
        except Exception:
            return ""

    @staticmethod
    def _images(task: dict) -> list[str]:
        try:
            items = json.loads(task.get("attachments") or "[]")
        except ValueError:
            return []
        return [p for p in items if isinstance(p, str) and Path(p).is_file()]

    def _pc_dirs(self, pid: int) -> list[str]:
        if not self.store.is_pc(pid):
            return []
        extra = self.store.get_setting("pc.extra_dirs", []) or []
        return [d for d in extra if Path(d).is_dir()]

    def _desktop_opts(self, pid: int, task: dict) -> dict | None:
        if not task.get("desktop"):
            return None
        from ..appdirs import APP_ROOT
        env = {"KAGUYA_DESKTOP_DIR": str(desktop_control.control_dir(self.home / "desktop")),
               "KAGUYA_DESKTOP_WINDOW": self._desktop_window(pid),
               "KAGUYA_DESKTOP_AGENT": task["target"] if task["target"] in ("codex", "claude") else "codex",
               "KAGUYA_DESKTOP_MAX": str(int(self.setting("desktop.max_actions") or 400))}
        if self.store.is_pc(pid):
            env["KAGUYA_DESKTOP_PC"] = "1"
        if self.confirm_bridge is not None:      # confirmations travel on a connection only the Studio answers
            info = self.confirm_bridge(env["KAGUYA_DESKTOP_AGENT"], task["id"])
            if info:
                self._confirm_tokens[task["id"]] = info["token"]
                env["KAGUYA_CONFIRM_PORT"], env["KAGUYA_CONFIRM_TOKEN"] = str(info["port"]), info["token"]
        if not getattr(sys, "frozen", False):
            env["PYTHONPATH"] = str(APP_ROOT)
        for k in ("KAGUYA_DESKTOP_BACKEND", "KAGUYA_DESKTOP_FAKE_LOG"):  # test doubles
            if (self.env or {}).get(k):
                env[k] = self.env[k]
        desk = {"command": list(self.desktop_command), "env": env}
        return self._write_mcp_config(pid, task, desk=desk)

    def _write_mcp_config(self, pid: int, task: dict, desk: dict | None = None, browser: dict | None = None) -> dict:
        """One config file listing the Studio's own MCP servers for this task (Claude reads it with --mcp-config)."""
        cfg = self._logs(pid, task["id"]) / "mcp-studio.json"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        old = {}
        try:
            old = json.loads(cfg.read_text(encoding="utf-8")).get("mcpServers", {})
        except (OSError, ValueError):
            pass
        new = claude_desktop_config(desk, browser)["mcpServers"]
        cfg.write_text(json.dumps({"mcpServers": {**old, **new}}, ensure_ascii=False, indent=1), encoding="utf-8")
        spec = desk or browser
        spec["config_file"] = str(cfg)
        return spec

    def _browser_opts(self, pid: int, task: dict) -> dict | None:
        """Kaguya Browser tools for this task: a token valid only while it runs, bound to this assistant."""
        agent = task["target"]
        if not task.get("browser") or agent not in ("codex", "claude") or self.browser_bridge is None:
            return None
        info = self.browser_bridge(agent, task["id"])
        if not info:
            return None
        self._browser_tokens[task["id"]] = info["token"]
        env = {"KAGUYA_BROWSER_PORT": str(info["port"]), "KAGUYA_BROWSER_TOKEN": info["token"],
               "KAGUYA_BROWSER_AGENT": agent}
        if not getattr(sys, "frozen", False):
            from ..appdirs import APP_ROOT
            env["PYTHONPATH"] = str(APP_ROOT)
        return self._write_mcp_config(pid, task, browser={"command": list(self.browser_command), "env": env})

    def _finish_desktop(self, pid: int, tid: int) -> None:
        base = self.home / "desktop"
        entries, _ = desktop_control.read_activity(base)
        if entries:
            lines = [f"[{e.get('t')}] {e.get('action')} {e.get('detail', '')}".rstrip() for e in entries]
            self.store.append_event(tid, "desktop", f"Uso do computador: {len(entries)} ação(ões).\n" + "\n".join(lines[-200:]))
        reason = desktop_control.stop_reason(base)
        if reason and "interrompida" not in reason:
            self.store.append_event(tid, "system", f"Controle do computador parado: {reason}.")
        self.emit("desktop", pid=pid, task_id=tid, active=False)

    # ------------------------------------------------------------ autonomy
    def _restore_point(self, pid: int, task: dict) -> None:
        _proj, cwd, in_git, root = self._project(pid)
        if not in_git:
            raise TaskFailed("Modo autônomo exige repositório Git (é o que permite desfazer). Crie o repositório no menu GitHub.")
        cp = checkpoint.create(Path(root), f"tarefa-{task['id']}")
        self.store.set_checkpoint(task["id"], checkpoint.to_text(cp))
        self.store.append_event(task["id"], "system", "Modo autônomo: ponto de restauração criado "
                                f"({cp.commit[:10]}). Use \"Desfazer\" na fila para voltar tudo como estava.")

    def task_changes(self, tid: int) -> list[str]:
        task = self.store.get_task(tid)
        cp = checkpoint.from_text(task.get("checkpoint") or "")
        if cp is None:
            return []
        _p, _cwd, _git, root = self._project(task["project_id"])
        return checkpoint.changes_since(Path(root), cp)

    def undo_task(self, tid: int) -> list[str]:
        """Return the project to the state before an autonomous task. Refuses while it runs."""
        task = self.store.get_task(tid)
        cp = checkpoint.from_text(task.get("checkpoint") or "")
        if cp is None:
            raise ValueError("Esta tarefa não tem ponto de restauração (só tarefas no modo autônomo têm).")
        if self.current_task(task["project_id"]) == tid:
            raise ValueError("A tarefa ainda está em execução; interrompa antes de desfazer.")
        _p, _cwd, _git, root = self._project(task["project_id"])
        changed = checkpoint.restore(Path(root), cp)
        checkpoint.drop(Path(root), cp)
        self.store.set_checkpoint(tid, "")
        self.store.append_event(tid, "system", f"Desfeito: {len(changed)} arquivo(s) voltaram ao estado anterior à tarefa."
                                + ("\n" + "\n".join(changed[:40]) if changed else ""))
        self.emit("task_undone", pid=task["project_id"], task_id=tid, files=changed)
        return changed

    # ---------------------------------------------------------------- helpers
    def _project(self, pid: int) -> tuple[dict, Path, bool, str | None]:
        proj = self.store.project(pid)
        folder = check_project_folder(proj["directory"])
        if not folder.ok:
            raise TaskFailed("Pasta do projeto indisponível: " + folder.summary())
        return proj, Path(folder.path), bool(folder.git_root), folder.git_root

    def _logs(self, pid: int, tid: int) -> Path:
        p = self.home / "logs" / f"projeto-{pid}" / f"tarefa-{tid}"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _with_persona(self, prompt: str, agent: str, pid: int | None = None) -> str:
        """The user's personality for Kaguya/Miwa goes after the rules, right before the task."""
        from .. import persona
        block = persona.for_agent(self.store, agent, pid=pid)
        if not block:
            return prompt
        if "\n\nTAREFA:\n" in prompt:
            return prompt.replace("\n\nTAREFA:\n", f"\n\n{block}\n\nTAREFA:\n", 1)
        return prompt + "\n\n" + block

    def _turn(self, pid: int, tid: int, agent: str, cwd: Path, prompt: str, opts: RunOptions,
              cancel: threading.Event, log_name: str, stage: str) -> RunResult:
        block = self.limit_block(agent)
        if block:
            raise TaskFailed(block, "blocked_limit")
        self.store.set_stage(tid, f"verificando {agent}")
        exe, caps = self.ensure_ready(agent, str(cwd), cancel)
        self.store.set_stage(tid, stage)
        prompt = self._with_persona(prompt, agent, pid)
        self.emit("agent_state", pid=pid, task_id=tid, agent=agent, state="running", stage=stage)
        self.store.append_event(tid, "stage", f"{stage}: {agent}", agent)

        def on_event(ev: AgentEvent):
            if ev.kind in ("text", "error", "warning", "command", "file_change", "web", "tool", "todo", "final"):
                if ev.kind != "final":
                    self.store.append_event(tid, ev.kind, ev.text, agent)
            if ev.kind == "rate_limit":
                self._record_claude_limit(ev.data)
            if agent == "claude" and isinstance(ev.data, dict) and "mcp_servers" in ev.data and self.setting("hub.enabled"):
                try:   # the real session says what loaded and connected: strongest evidence for the Hub
                    self.hub.registry.record_session("claude", ev.data, project=str(cwd))
                except Exception:
                    pass
            self.emit("agent_event", pid=pid, task_id=tid, agent=agent, kind=ev.kind, text=ev.text, data=ev.data,
                      stage=stage)

        timeout = float(self.setting("run.timeout_min") or 60) * 60
        result = run_agent(agent, exe, caps, cwd, prompt, opts, on_event, log_file=self._logs(pid, tid) / log_name,
                           cancel=cancel, env=self.env, timeout_s=timeout)
        if result.usage:
            self.store.add_local_usage(agent, tid, result.usage.get("input_tokens", 0),
                                       result.usage.get("output_tokens", 0), result.usage.get("cached_tokens", 0),
                                       result.duration_ms)
        if result.limit_reached:
            self.emit("agent_state", pid=pid, task_id=tid, agent=agent, state="limit", stage=stage)
            raise TaskFailed(f"{agent.capitalize()}: {result.failure_reason()}", "blocked_limit")
        if result.cancelled:
            self.emit("agent_state", pid=pid, task_id=tid, agent=agent, state="cancelled", stage=stage)
            raise TaskFailed("Interrompido pelo usuário.", "cancelled")
        if not result.ok:
            self.emit("agent_state", pid=pid, task_id=tid, agent=agent, state="error", stage=stage)
            raise TaskFailed(f"{agent.capitalize()} falhou: {result.failure_reason()}")
        self.emit("agent_state", pid=pid, task_id=tid, agent=agent, state="success", stage=stage)
        for w in result.warnings:
            self.store.append_event(tid, "warning", w, agent)
        if result.final_text:
            self.store.append_event(tid, "message", result.final_text, agent)
        self._capture_learnings(pid, tid, agent, result.final_text)
        return result

    def _record_claude_limit(self, info: dict) -> None:
        from ..usage import claude_payload
        self.store.save_usage("claude", "Claude Code (stream-json rate_limit_event)", claude_payload(info))
        self.emit("usage", agent="claude")

    def _capture_learnings(self, pid: int, tid: int, agent: str, text: str) -> None:
        items = [(k, t) for k, t in extract_learnings(text) if not t.lower().startswith(("nenhum", "nenhuma"))]
        if not items:
            return
        ob = self.outbox(pid)
        proj = self.store.project(pid)["name"]
        counts: dict[str, int] = {}
        who = {"codex": "Kaguya (Codex)", "claude": "Miwa (Claude Code)"}.get(agent, agent)
        for kind, item in items:
            ob.stage(kind, item[:90], item, project=proj, source=f"{agent} • tarefa #{tid}", found_by=who,
                     version=detect_version(item), evidence=f"Extraído da resposta do {agent} na tarefa #{tid}.")
            counts[ob.last_status] = counts.get(ob.last_status, 0) + 1
        parts = [f"{n} {w}" for w, n in (("nova(s)", counts.get("novo", 0)),
                                          ("atualização(ões) de nota existente", counts.get("atualizacao", 0)),
                                          ("divergência(s)", counts.get("divergencia", 0)),
                                          ("já registrada(s)", counts.get("duplicado", 0))) if n]
        where = "para revisão no Segundo Cérebro" if ob.root else "na fila (vault não conectado; aprove depois de conectar)"
        self.store.append_event(tid, "system", f"Aprendizados {where}: " + ", ".join(parts) + ".")
        self.emit("learning", pid=pid, task_id=tid, count=len(items))

    def _common(self, pid: int, task: dict) -> dict:
        proj = self.store.project(pid)
        roles = ["explorar"] if task["target"] != "equipe" else ["explorar", "revisar"]
        agents = []
        if self.setting("agents.suggest"):
            try:
                agents = suggest_agents(self.inventory(pid), roles, proj["name"], limit=3)
            except Exception:
                agents = []
        return {"project": f"{proj['name']} ({proj['directory']})", "memory": self.memory_for(pid, task["title"]),
                "extra": "\n\n".join(x for x in (attached_context(task.get("context") or "", self._images(task)),
                                                   self._hub_context(task)) if x),
                "autonomous": bool(task.get("autonomous")),
                "desktop": self._desktop_window(pid) if task.get("desktop") else None,
                "pc": self.store.is_pc(pid), "browser": bool(task.get("browser")),
                "agents": agents, "web": bool(task["allow_web"]), "max_subagents": int(self.setting("economy.max_subagents"))}

    # ----------------------------------------------------------------- modes
    def _run_single(self, pid: int, task: dict, cancel: threading.Event) -> tuple[str, str]:
        agent = task["target"]
        proj, cwd, in_git, _root = self._project(pid)
        write = bool(task["allow_write"])
        if write and not in_git and not self.store.is_pc(pid):
            raise TaskFailed("Edição bloqueada: a pasta não está em um repositório Git. Rode 'git init' ou desmarque "
                             "'Permitir alterações'.")
        common = self._common(pid, task)
        prompt = task_prompt(task["title"], write=write, commands=bool(task["allow_commands"]), **common)
        resume = self.store.session(pid, agent) if self.setting("session.continue") else None
        opts = RunOptions(write=write, commands=bool(task["allow_commands"]), web=bool(task["allow_web"]),
                          autonomous=bool(task.get("autonomous")), desktop=self._desktop_opts(pid, task),
                          pc=self.store.is_pc(pid), extra_dirs=self._pc_dirs(pid), images=self._images(task),
                          browser=self._browser_opts(pid, task),
                          mcp=bool(task["allow_mcp"]), resume=resume, in_git=in_git, workdir=str(cwd),
                          model=self.setting(f"models.{agent}") or None)
        self.store.set_stage(task["id"], "execucao")
        result = self._turn(pid, task["id"], agent, cwd, prompt, opts, cancel, f"{agent}.log", "execucao")
        if result.session_id:
            self.store.set_session(pid, agent, result.session_id)
        checks = run_checks(cwd, run_tests=bool(task["run_tests"]), test_command=proj.get("test_command"))
        self._report_checks(pid, task["id"], checks)
        status = "executed"
        tp = tests_passed(checks)
        if tp is False:
            status = "pending_review"
        summary = (result.final_text or "")[-6000:] + "\n\nVERIFICAÇÕES DO STUDIO:\n" + summarize(checks)
        return status, summary

    def _report_checks(self, pid: int, tid: int, checks: list[Check]) -> None:
        text = summarize(checks)
        self.store.append_event(tid, "quality", text, "studio")
        self.emit("quality", pid=pid, task_id=tid, checks=[c.__dict__ for c in checks])

    def _run_team(self, pid: int, task: dict, cancel: threading.Event) -> tuple[str, str]:
        tid = task["id"]
        proj, cwd, in_git, _ = self._project(pid)
        impl, rev = self.setting("team.implementer"), self.setting("team.reviewer")
        if impl == rev or {impl, rev} != {"codex", "claude"}:
            impl, rev = "codex", "claude"
        write = bool(task["allow_write"])
        if write and not in_git and not self.store.is_pc(pid):
            raise TaskFailed("Edição bloqueada: a pasta não está em um repositório Git.")
        commands = bool(task["allow_commands"])
        common = self._common(pid, task)
        max_cycles = max(1, min(5, int(self.setting("team.max_cycles"))))
        impl_opts = RunOptions(write=write, commands=commands, web=bool(task["allow_web"]), mcp=bool(task["allow_mcp"]),
                               autonomous=bool(task.get("autonomous")), desktop=self._desktop_opts(pid, task),
                               pc=self.store.is_pc(pid), extra_dirs=self._pc_dirs(pid), images=self._images(task),
                               in_git=in_git, workdir=str(cwd), model=self.setting(f"models.{impl}") or None)
        rev_opts = RunOptions(write=False, commands=False, web=bool(task["allow_web"]), mcp=bool(task["allow_mcp"]),
                              in_git=in_git, workdir=str(cwd), model=self.setting("models.review") or None)
        self._stage(pid, tid, "implementacao", 1, max_cycles)
        role = "IMPLEMENTADOR. " + ("Implemente a tarefa." if write else "Edição não permitida: analise e proponha a "
                                    "implementação com trechos de código prontos e onde aplicá-los.")
        result = self._turn(pid, tid, impl, cwd, task_prompt(task["title"], write=write, commands=commands, role=role,
                                                             **common), impl_opts, cancel, f"{impl}_c1.log",
                            "implementacao")
        impl_opts.resume = result.session_id
        verdict: dict = {"veredito": "pendente", "problemas": []}
        checks: list[Check] = []
        for cycle in range(1, max_cycles + 1):
            self._stage(pid, tid, "verificacao", cycle, max_cycles)
            checks = run_checks(cwd, run_tests=bool(task["run_tests"]), test_command=proj.get("test_command"))
            self._report_checks(pid, tid, checks)
            self._stage(pid, tid, "revisao", cycle, max_cycles)
            review = self._turn(pid, tid, rev, cwd, review_prompt(task["title"], impl, result.final_text, summarize(checks),
                                                                  cycle, write=False, commands=False, **{**common, "desktop": None}),
                                rev_opts, cancel, f"{rev}_revisao_c{cycle}.log", "revisao")
            rev_opts.resume = review.session_id
            verdict = parse_verdict(review.final_text)
            self.store.append_event(tid, "verdict", json.dumps(verdict, ensure_ascii=False), rev)
            self.emit("verdict", pid=pid, task_id=tid, cycle=cycle, verdict=verdict)
            if verdict["veredito"] != "reprovado":
                break
            if cycle == max_cycles:
                break
            self._stage(pid, tid, "correcao", cycle + 1, max_cycles)
            result = self._turn(pid, tid, impl, cwd, fix_prompt(task["title"], rev, verdict["problemas"], summarize(checks),
                                                               cycle + 1, write=write, commands=commands, **common),
                                impl_opts, cancel, f"{impl}_correcao_c{cycle + 1}.log", "correcao")
            impl_opts.resume = result.session_id or impl_opts.resume
        tp = tests_passed(checks)
        v = verdict["veredito"]
        if v == "aprovado":
            status = "approved"
            label = "APROVADA pela revisão" + (" com testes passando" if tp else " (testes não executados)" if tp is None else
                                               " — mas os testes FALHARAM")
            if tp is False:
                status = "pending_review"
        elif v == "reprovado":
            status, label = "rejected", f"REPROVADA após {max_cycles} ciclo(s); veja os problemas"
        else:
            status, label = "pending_review", "PENDENTE: o revisor não conseguiu confirmar"
        self._stage(pid, tid, "final", max_cycles, max_cycles)
        problems = "\n".join("- " + p for p in verdict.get("problemas", []))
        summary = (f"{label}.\n\nProblemas apontados:\n{problems or '- nenhum'}\n\nVERIFICAÇÕES DO STUDIO:\n{summarize(checks)}"
                   f"\n\nÚLTIMA RESPOSTA DO {impl.upper()}:\n{(result.final_text or '')[-3000:]}")
        return status, summary

    def _stage(self, pid: int, tid: int, stage: str, cycle: int, max_cycles: int) -> None:
        self.store.set_stage(tid, f"{stage}:{cycle}/{max_cycles}")
        self.emit("stage", pid=pid, task_id=tid, stage=stage, cycle=cycle, max_cycles=max_cycles)

    def _run_parallel(self, pid: int, task: dict, cancel: threading.Event) -> tuple[str, str]:
        tid = task["id"]
        proj, cwd, in_git, root = self._project(pid)
        if not in_git or not root:
            raise TaskFailed("Modo paralelo exige repositório Git (cada IA trabalha em um worktree isolado).")
        plan_ev = [e for e in self.store.events(tid) if e["kind"] == "plan"]
        subtasks = json.loads(plan_ev[-1]["message"]) if plan_ev else []
        if len(subtasks) < 2:
            raise TaskFailed("Nenhuma subtarefa paralela encontrada.")
        rel = Path(cwd).relative_to(Path(root)) if Path(cwd) != Path(root) else Path(".")
        common = self._common(pid, task)
        results: dict[int, dict] = {}
        lock = threading.Lock()
        sem = threading.Semaphore(max(1, int(self.setting("parallel.max_workers"))))

        def work(i: int, agent: str, text: str):
            with sem:
                if cancel.is_set():
                    return
                info = {"agent": agent, "task": text}
                wt = branch = None
                try:
                    wt, branch = worktree.create(Path(root), tid, i, agent)
                    info.update(path=str(wt), branch=branch)
                    wcwd = wt / rel
                    # Writing is confined to the isolated worktree; the user's tree changes only on integration.
                    opts = RunOptions(write=True, commands=bool(task["allow_commands"]),
                                      autonomous=bool(task.get("autonomous")),
                                      web=bool(task["allow_web"]), in_git=True, workdir=str(wcwd))
                    prompt = task_prompt(text, write=True, commands=bool(task["allow_commands"]),
                                         role=f"Trabalhador paralelo {i}. Você está num worktree Git isolado; altere só o "
                                              f"necessário para ESTA subtarefa.", **common)
                    res = self._turn(pid, tid, agent, wcwd, prompt, opts, cancel, f"paralelo_{i}_{agent}.log",
                                     f"paralelo {i}")
                    committed = worktree.commit_all(wt, f"Kaguya #{tid}.{i} ({agent}): {text[:60]}")
                    info.update(ok=True, committed=committed, files=worktree.changed_files(Path(root), branch),
                                summary=res.final_text[-1500:])
                except TaskFailed as exc:
                    info.update(ok=False, error=str(exc))
                except Exception as exc:
                    info.update(ok=False, error=f"Erro interno: {exc}")
                finally:
                    if wt is not None:
                        # the work lives in the branch (diff/integrate use it): the folder is no longer needed;
                        # a branch with nothing committed is removed too (they used to pile up forever)
                        try:
                            worktree.remove(Path(root), wt, None if info.get("committed") else branch)
                        except Exception:
                            pass
                with lock:
                    results[i] = info
                self.store.append_event(tid, "worktree", json.dumps(info, ensure_ascii=False), agent)

        threads = [threading.Thread(target=work, args=(i, a, t), daemon=True) for i, (a, t) in enumerate(subtasks, 1)]
        self._stage(pid, tid, "paralelo", 1, 1)
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        branches = [r["branch"] for r in results.values() if r.get("branch") and r.get("committed")]
        clash = worktree.overlap(Path(root), branches) if len(branches) > 1 else {}
        lines = []
        for i in sorted(results):
            r = results[i]
            state = "ok" if r.get("ok") else "falhou"
            lines.append(f"[{i}] {r['agent']} — {state} — ramo {r.get('branch', '-')} — {len(r.get('files', []))} arquivo(s)"
                         + (f"\n    erro: {r['error']}" if r.get("error") else ""))
        if clash:
            lines.append("ATENÇÃO: arquivos alterados por mais de um trabalhador (integração manual): " + ", ".join(clash))
        self.store.append_event(tid, "parallel", json.dumps({"results": results, "overlap": clash}, ensure_ascii=False))
        ok = all(r.get("ok") for r in results.values()) and len(results) == len(subtasks)
        summary = ("Trabalho paralelo concluído. Revise os diffs e integre cada ramo pela Fila (integração supervisionada).\n"
                   if ok else "Trabalho paralelo com falhas.\n") + "\n".join(lines)
        return ("pending_review" if ok else "error"), summary
