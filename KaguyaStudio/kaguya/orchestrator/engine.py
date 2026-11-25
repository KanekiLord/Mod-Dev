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
import threading
import time
import traceback
from typing import Callable

from ..appdirs import CATALOG, data_dir
from ..cli import discovery
from ..cli.commands import RunOptions
from ..cli.discovery import Capabilities, Diagnosis
from ..cli.events import AgentEvent, RunResult
from ..cli.runner import run_agent
from ..inventory import Inventory, scan, suggest_agents
from ..messages import Intent
from ..paths import check_project_folder
from ..prompts import fix_prompt, parse_verdict, review_prompt, task_prompt
from ..quality import Check, run_checks, summarize, tests_passed
from ..store import Store
from ..vault.index import VaultIndex, context_block
from ..vault.outbox import Outbox, extract_learnings
from . import worktree

Listener = Callable[[dict], None]

DEFAULTS = {
    "economy.max_subagents": 2,
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


class Engine:
    def __init__(self, store: Store, listener: Listener | None = None, home: Path | None = None,
                 env: dict[str, str] | None = None):
        self.store = store
        self.home = Path(home or data_dir())
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

    # ------------------------------------------------------------ diagnostics
    def diagnose(self, target: str, cwd: str | None = None) -> Diagnosis:
        override = self.store.get_setting(f"cli.{target}.path") or None
        diag, caps = discovery.diagnose(target, cwd, override, env=self.env)
        with self._lock:
            self.diagnoses[target] = diag
            if caps.flags:
                self.capabilities[target] = caps
                self.store.set_setting("cli.capabilities", {k: v.to_dict() for k, v in self.capabilities.items()})
        self.store.set_setting(f"cli.{target}.last", diag.to_dict())
        self.emit("diagnosis", target=target, diagnosis=diag.to_dict())
        return diag

    def ensure_ready(self, target: str, cwd: str | None) -> tuple[str, Capabilities]:
        diag = self.diagnoses.get(target)
        if diag is None or not diag.usable:
            diag = self.diagnose(target, cwd)
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

    def outbox(self, pid: int) -> Outbox | None:
        vault = self.store.effective_vault(pid)
        if not vault or not Path(vault).is_dir():
            return None
        return Outbox(Path(vault), self.home / "outbox", self.vault_index(vault))

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
               mcp: bool = False, run_tests: bool = False) -> int:
        tid = self.store.enqueue(pid, intent.target, intent.text, intent.kind, allow_write=write, allow_web=web,
                                 allow_commands=commands, allow_mcp=mcp, run_tests=run_tests)
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
        return bool(rt and rt.thread and rt.thread.is_alive())

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

    def cancel(self, pid: int) -> bool:
        rt = self.runtimes.get(pid)
        if rt and rt.cancel and rt.thread and rt.thread.is_alive():
            rt.cancel.set()
            return True
        return False

    def wait(self, pid: int, timeout: float = 60) -> None:
        rt = self.runtimes.get(pid)
        if rt and rt.thread:
            rt.thread.join(timeout)

    def _worker(self, pid: int, rt: ProjectRuntime) -> None:
        while not rt.cancel.is_set():
            task = self.store.claim(pid)
            if task is None:
                break
            rt.task_id = task["id"]
            self.emit("task_started", pid=pid, task_id=task["id"], target=task["target"], title=task["title"])
            status, summary = "error", ""
            try:
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
            if rt.cancel.is_set() and status not in ("approved",):
                status = "cancelled"
                summary = summary or "Interrompido pelo usuário."
            self.store.complete(task["id"], status, summary)
            self.emit("task_done", pid=pid, task_id=task["id"], status=status, summary=summary[-3000:])
            rt.task_id = None
            if status in ("error", "blocked_limit"):
                # don't burn limits on the rest of the queue after a failure
                self.emit("log", pid=pid, message="Fila pausada após falha; reative quando resolver o problema.")
                break
        self.emit("worker_idle", pid=pid)

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

    def _turn(self, pid: int, tid: int, agent: str, cwd: Path, prompt: str, opts: RunOptions,
              cancel: threading.Event, log_name: str, stage: str) -> RunResult:
        block = self.limit_block(agent)
        if block:
            raise TaskFailed(block, "blocked_limit")
        exe, caps = self.ensure_ready(agent, str(cwd))
        self.emit("agent_state", pid=pid, task_id=tid, agent=agent, state="running", stage=stage)
        self.store.append_event(tid, "stage", f"{stage}: {agent}", agent)

        def on_event(ev: AgentEvent):
            if ev.kind in ("text", "error", "warning", "command", "file_change", "web", "tool", "todo", "final"):
                if ev.kind != "final":
                    self.store.append_event(tid, ev.kind, ev.text, agent)
            if ev.kind == "rate_limit":
                self._record_claude_limit(ev.data)
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
        if ob is None:
            self.store.append_event(tid, "system", f"{len(items)} aprendizado(s) não registrados: vault não vinculado.")
            return
        proj = self.store.project(pid)["name"]
        for kind, item in items:
            ob.stage(kind, item[:90], item, project=proj, source=f"{agent} • tarefa #{tid}",
                     evidence=f"Extraído da resposta do {agent} na tarefa #{tid}.")
        self.store.append_event(tid, "system", f"{len(items)} aprendizado(s)/erro(s) enviados para revisão no Segundo Cérebro.")
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
                "agents": agents, "web": bool(task["allow_web"]), "max_subagents": int(self.setting("economy.max_subagents"))}

    # ----------------------------------------------------------------- modes
    def _run_single(self, pid: int, task: dict, cancel: threading.Event) -> tuple[str, str]:
        agent = task["target"]
        proj, cwd, in_git, _root = self._project(pid)
        write = bool(task["allow_write"])
        if write and not in_git:
            raise TaskFailed("Edição bloqueada: a pasta não está em um repositório Git. Rode 'git init' ou desmarque "
                             "'Permitir alterações'.")
        common = self._common(pid, task)
        prompt = task_prompt(task["title"], write=write, commands=bool(task["allow_commands"]), **common)
        resume = self.store.session(pid, agent) if self.setting("session.continue") else None
        opts = RunOptions(write=write, commands=bool(task["allow_commands"]), web=bool(task["allow_web"]),
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
        if write and not in_git:
            raise TaskFailed("Edição bloqueada: a pasta não está em um repositório Git.")
        commands = bool(task["allow_commands"])
        common = self._common(pid, task)
        max_cycles = max(1, min(5, int(self.setting("team.max_cycles"))))
        impl_opts = RunOptions(write=write, commands=commands, web=bool(task["allow_web"]), mcp=bool(task["allow_mcp"]),
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
                                                                  cycle, write=False, commands=False, **common),
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
                try:
                    wt, branch = worktree.create(Path(root), tid, i, agent)
                    info.update(path=str(wt), branch=branch)
                    wcwd = wt / rel
                    # Writing is confined to the isolated worktree; the user's tree changes only on integration.
                    opts = RunOptions(write=True, commands=bool(task["allow_commands"]),
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
