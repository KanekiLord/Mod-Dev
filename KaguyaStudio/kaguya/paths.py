"""Folder linking: normalisation and verification of project folders and Obsidian vaults.

Fixes for the V3.4 linking failures:
* paths typed/pasted by the user are accepted (quotes, ``%VAR%``, ``~``, ``D:\\``, UNC);
* project and vault are verified **separately**, each with a specific diagnosis;
* a project inside a Git repository (sub-folder) is accepted; the Git root is detected
  instead of refusing with "escolha a raiz do repositório";
* nothing is written in the vault; the project write test uses a temporary file that is
  removed immediately.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def normalize_user_path(text: str | os.PathLike | None) -> Path:
    """Turn what the user typed/pasted into an absolute path. Raises ValueError if empty."""
    if text is None:
        raise ValueError("Nenhuma pasta informada.")
    raw = str(text).strip().strip('"').strip("'").strip()
    if not raw:
        raise ValueError("Nenhuma pasta informada.")
    if raw.lower().startswith("file:///"):
        raw = raw[8:] if os.name == "nt" else raw[7:]
    raw = os.path.expandvars(os.path.expanduser(raw))
    if os.name == "nt":
        raw = raw.replace("/", "\\")
        # "D:" alone means the current dir of drive D in Windows; the user means the drive root.
        if len(raw) == 2 and raw[1] == ":":
            raw += "\\"
    path = Path(raw)
    try:
        path = path.resolve(strict=False)
    except (OSError, RuntimeError):
        path = Path(os.path.abspath(raw))
    return path


@dataclass
class FolderCheck:
    path: str
    kind: str  # "projeto" | "vault"
    exists: bool = False
    is_dir: bool = False
    readable: bool = False
    writable: bool | None = None
    git_root: str | None = None
    is_git_root: bool = False
    git_available: bool = True
    is_obsidian: bool = False
    markdown_sample: int = 0
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def to_dict(self) -> dict:
        data = asdict(self)
        data["ok"] = self.ok
        return data

    def summary(self) -> str:
        if self.problems:
            return "; ".join(self.problems)
        parts = []
        if self.kind == "projeto":
            if self.git_root:
                parts.append("Git: raiz" if self.is_git_root else f"Git: subpasta de {self.git_root}")
            else:
                parts.append("sem Git (somente leitura/consulta)")
            parts.append("gravável" if self.writable else "sem permissão de escrita")
        else:
            parts.append("vault Obsidian" if self.is_obsidian else "pasta Markdown (sem .obsidian)")
            parts.append(f"{self.markdown_sample}{'+' if self.markdown_sample >= 400 else ''} notas .md")
        return " • ".join(parts)


def git_root(path: Path, timeout: float = 10) -> str | None:
    git = shutil.which("git")
    if not git:
        return None
    try:
        result = subprocess.run([git, "-C", str(path), "rev-parse", "--show-toplevel"],
                                capture_output=True, text=True, timeout=timeout,
                                encoding="utf-8", errors="replace",
                                creationflags=_no_window())
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    out = result.stdout.strip()
    return str(Path(out).resolve()) if out else None


def _no_window() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _basic(check: FolderCheck, path: Path) -> bool:
    try:
        check.exists = path.exists()
        check.is_dir = path.is_dir()
    except OSError as exc:
        check.problems.append(f"Não foi possível acessar a pasta: {exc}")
        return False
    if not check.exists:
        check.problems.append("A pasta não existe (confira a letra do disco e o nome, inclusive acentos).")
        if os.name == "nt" and len(path.anchor) >= 2 and not Path(path.anchor).exists():
            check.hints.append(f"A unidade {path.anchor} não está disponível. O disco está conectado?")
        return False
    if not check.is_dir:
        check.problems.append("O caminho aponta para um arquivo, não para uma pasta.")
        return False
    try:
        with os.scandir(path) as entries:
            next(iter(entries), None)
        check.readable = True
    except PermissionError:
        check.problems.append("Sem permissão de leitura nesta pasta.")
        return False
    except OSError as exc:
        check.problems.append(f"Erro ao ler a pasta: {exc}")
        return False
    return True


def _write_probe(path: Path) -> bool:
    try:
        fd, name = tempfile.mkstemp(prefix=".kaguya-probe-", dir=str(path))
        os.close(fd)
        os.remove(name)
        return True
    except OSError:
        return False


def check_project_folder(path_text) -> FolderCheck:
    path = normalize_user_path(path_text)
    check = FolderCheck(path=str(path), kind="projeto")
    if not _basic(check, path):
        return check
    check.writable = _write_probe(path)
    if not check.writable:
        check.warnings.append("Sem permissão de escrita: as IAs poderão apenas ler/consultar.")
    check.git_available = shutil.which("git") is not None
    if not check.git_available:
        check.warnings.append("Git não encontrado no PATH. Alterações automáticas ficam bloqueadas.")
        check.hints.append("Instale o Git for Windows (git-scm.com) e reabra o Studio.")
        return check
    root = git_root(path)
    if root:
        check.git_root = root
        check.is_git_root = Path(root) == path
        if not check.is_git_root:
            check.hints.append(f"Projeto em subpasta do repositório {root}; alterações serão rastreadas por esse Git.")
    else:
        check.warnings.append("Pasta sem repositório Git: as IAs podem conversar e analisar, mas não editar.")
        check.hints.append("Para permitir edições seguras (com desfazer), rode 'git init' na pasta do projeto.")
    return check


def check_vault_folder(path_text, sample_limit: int = 400) -> FolderCheck:
    path = normalize_user_path(path_text)
    check = FolderCheck(path=str(path), kind="vault")
    if not _basic(check, path):
        return check
    check.is_obsidian = (path / ".obsidian").is_dir()
    count = 0
    skip = {".obsidian", ".git", ".trash", "node_modules", ".venv"}
    for base, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in skip]
        count += sum(1 for f in files if f.lower().endswith(".md"))
        if count >= sample_limit:
            break
    check.markdown_sample = count
    if not check.is_obsidian:
        check.warnings.append("Não há pasta .obsidian aqui. Pode ser uma subpasta do vault.")
        parent = next((p for p in path.parents if (p / ".obsidian").is_dir()), None)
        if parent:
            check.hints.append(f"O vault parece começar em {parent}.")
    if count == 0:
        check.warnings.append("Nenhuma nota .md encontrada.")
    return check
