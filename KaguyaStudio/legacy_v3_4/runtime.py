"""CLI adapters for authenticated Codex and Claude Code installations.

All calls are explicit foreground jobs initiated from the local application.
No API or token extraction is implemented. No permission bypass flags are used.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from typing import Callable

from core import plan_command, safe_env


class Cancelled(RuntimeError):
    pass


def _resolved(command: list[str]) -> list[str]:
    resolved=shutil.which(command[0])
    if not resolved:
        raise FileNotFoundError(f'Nao foi encontrada a CLI {command[0]!r}. Instale e entre pela conta antes de usar.')
    return [resolved,*command[1:]]


def run_process(command:list[str], directory:Path, stdin_text:str, emit:Callable[[str],None],
                log_file:Path|None=None, cancel:threading.Event|None=None,
                use_environment:dict[str,str]|None=None) -> tuple[int,str]:
    env=safe_env(use_environment)
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
    proc=subprocess.Popen(command,cwd=str(directory),stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          text=True,encoding='utf-8',errors='replace',bufsize=1,
                          env=env,creationflags=flags)
    if proc.stdin:
        try:
            if stdin_text:proc.stdin.write(stdin_text[:100000]);proc.stdin.flush()
        except (BrokenPipeError,OSError):pass
        finally:
            try:proc.stdin.close()
            except OSError:pass
    stopper=None
    if cancel:
        def watch():
            while proc.poll() is None:
                if cancel.wait(0.2):
                    try:
                        if os.name=='nt':
                            subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],
                                           capture_output=True,timeout=8)
                        else:proc.terminate()
                    except (OSError,subprocess.TimeoutExpired):
                        try:proc.kill()
                        except OSError:pass
                    return
        stopper=threading.Thread(target=watch,daemon=True)
        stopper.start()
    lines=[]
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            text=line.rstrip('\n')
            lines.append(text)
            emit(text)
        code=proc.wait()
    finally:
        if proc.stdout:proc.stdout.close()
    if log_file:
        log_file.parent.mkdir(parents=True,exist_ok=True)
        log_file.write_text('\n'.join(lines)[-400000:],encoding='utf-8')
    if cancel and cancel.is_set():
        raise Cancelled('Execucao interrompida pelo usuario')
    return code,'\n'.join(lines)


def check_subscription(target:str, directory:Path) -> str:
    """Fail closed if CLI can't affirm a subscriber login; cannot inspect remote billing."""
    if target=='claude':
        command=_resolved(['claude','auth','status'])
    elif target=='codex':
        command=_resolved(['codex','login','status'])
    else:raise ValueError('CLI nao reconhecida')
    result=subprocess.run(command,cwd=str(directory),env=safe_env(),
                          stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          text=True,encoding='utf-8',errors='replace',timeout=18)
    output=(result.stdout or '').strip()
    if result.returncode:
        raise RuntimeError(f'Nao foi possivel confirmar a assinatura {target}: {output[:500]}')
    if target=='claude':
        try:
            data=json.loads(output)
            method=data.get('authMethod','')
            if method not in ('claude.ai','oauth_token'):
                raise RuntimeError('O Claude nao confirmou login por assinatura Claude. Metodo: '+str(method))
        except json.JSONDecodeError as error:
            raise RuntimeError('Nao foi possivel verificar o metodo de login do Claude; atualize a CLI.') from error
        return f'Claude: autenticacao de assinatura reconhecida ({method})'
    else:
        if 'chatgpt' not in output.lower() or 'api key' in output.lower():
            raise RuntimeError('O Codex nao confirmou login por assinatura ChatGPT: '+output[:250])
        return 'Codex: login ChatGPT reconhecido'


def run_cli(target:str,repo:Path,prompt:str,write:bool,web:bool,
            emit:Callable[[str],None], log_file:Path, cancel:threading.Event|None=None,
            verify_login:bool=True) -> tuple[int,str]:
    if verify_login:
        emit(check_subscription(target,repo))
    command=plan_command(target,write,web)
    if target=='claude':
        command += ['--disallowedTools','mcp__*']
        # Never put untrusted user text in argv: Windows npm .cmd launchers
        # can interpret shell metacharacters. Claude supports piped stdin.
        command.append('Leia e execute a tarefa detalhada recebida na entrada padrão. Responda em português.')
        stdin=prompt[:14500]
    else:stdin=prompt[:14500]
    return run_process(_resolved(command),repo,stdin,emit,log_file,cancel)


def check_project_writable(repo:Path)->str:
    repo=Path(repo).resolve()
    if not shutil.which('git'):
        raise ValueError('Git nao encontrado. Escrita so e permitida em repositorios Git.')
    root=subprocess.run(['git','-C',str(repo),'rev-parse','--show-toplevel'],
                        capture_output=True,text=True,timeout=10)
    if root.returncode:
        raise ValueError('Escrita so e permitida em repositorios Git. Inicie com git init.')
    if Path(root.stdout.strip()).resolve()!=repo:
        raise ValueError('Para escrever, escolha a raiz do repositorio Git.')
    status=subprocess.run(['git','-C',str(repo),'status','--porcelain'],capture_output=True,text=True,timeout=10)
    if status.returncode:raise ValueError('Erro ao conferir Git')
    return status.stdout.strip()


def run_quality(repo:Path,run_tests:bool=False)->list[dict]:
    """Read-only checks by default. Test commands run ONLY with opt-in."""
    repo=Path(repo).resolve()
    result=[]
    git=shutil.which('git')
    if git:
        try:
            p=subprocess.run([git,'-C',str(repo),'diff','--check'],capture_output=True,text=True,timeout=30)
            result.append({'name':'git diff --check','status':'PASS' if p.returncode==0 else 'FAIL',
                           'details':(p.stdout+p.stderr)[-2500:]})
        except (OSError,subprocess.TimeoutExpired) as exc:
            result.append({'name':'git diff --check','status':'ERRO','details':str(exc)})
    else:result.append({'name':'git diff --check','status':'INDISPONIVEL','details':'Git nao encontrado'})
    if not run_tests:
        result.append({'name':'Testes de projeto','status':'NAO EXECUTADOS',
                       'details':'Necessaria confirmacao para executar codigo do repositorio.'})
        return result
    if (repo/'gradlew.bat').is_file() and os.name=='nt':
        cmd=[str(repo/'gradlew.bat'),'--offline','test']
    elif (repo/'gradlew').is_file():cmd=['bash',str(repo/'gradlew'),'--offline','test']
    elif (repo/'tests').is_dir():cmd=[sys.executable,'-m','unittest','discover','-s','tests']
    else:
        result.append({'name':'Testes do projeto','status':'INDISPONIVEL','details':'Nenhum test runner reconhecido; confira manualmente.'})
        return result
    try:
        p=subprocess.run(cmd,cwd=str(repo),capture_output=True,text=True,timeout=240,env=safe_env())
        result.append({'name':' '.join(cmd),'status':'PASS' if p.returncode==0 else 'FAIL',
                       'details':(p.stdout+'\n'+p.stderr)[-10000:]})
    except (OSError,subprocess.TimeoutExpired) as exc:
        result.append({'name':' '.join(cmd),'status':'ERRO','details':str(exc)})
    return result
