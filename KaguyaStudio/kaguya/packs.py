"""Where heavy downloads live (transcription models, neural voices, Qwen3-TTS): the user's choice.

The Studio's own data (settings, catalogue, logs) stays in ``%LOCALAPPDATA%\\KaguyaStudio`` — it is
small. The packs can be gigabytes, so the first download asks where to put them: the recommended
folder, next to where the Studio was installed (when that folder can be written), or any other.
Changing the folder later moves what was already installed (nothing is downloaded twice).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import sys
import uuid

SUBDIRS = ("modelos", "vozes")
SETTING = "packs.dir"


@dataclass
class Choice:
    key: str
    label: str
    path: Path
    free: int | None
    writable: bool


def current(store, home: Path) -> Path:
    v = store.get_setting(SETTING, "") if store is not None else ""
    return Path(v) if v else Path(home)


def chosen(store) -> bool:
    return bool(store.get_setting(SETTING, ""))


def has_content(root: Path) -> bool:
    for sub in SUBDIRS:
        d = Path(root) / sub
        try:
            if d.is_dir() and any(d.iterdir()):
                return True
        except OSError:
            pass
    return False


def free_bytes(path: Path) -> int | None:
    p = Path(path)
    while not p.exists() and p.parent != p:
        p = p.parent
    try:
        return shutil.disk_usage(p).free
    except OSError:
        return None


def writable(path: Path) -> bool:
    p = Path(path)
    try:
        p.mkdir(parents=True, exist_ok=True)
        probe = p / f".kaguya-teste-{uuid.uuid4().hex[:6]}"
        probe.write_bytes(b"ok")
        probe.unlink()
        return True
    except OSError:
        return False


def install_dir() -> Path | None:
    """Folder the Studio runs from (the installer's choice), when running the installed .exe."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return None


def choices(home: Path, *, install: Path | None = None) -> list[Choice]:
    out = [Choice("recomendada", "Pasta recomendada (dados do Studio)", Path(home), free_bytes(home), True)]
    inst = install if install is not None else install_dir()
    if inst is not None:
        beside = inst / "Pacotes"
        if writable(beside):
            out.append(Choice("instalacao", f"Junto da instalação do Studio ({inst})", beside, free_bytes(beside), True))
        else:
            # e.g. installed in Program Files on another drive: offer the root of that drive instead
            drive = Path(inst.anchor) / "KaguyaStudio Pacotes" if inst.anchor else None
            if drive is not None and drive.anchor.lower() != Path(home).anchor.lower() and writable(drive):
                out.append(Choice("instalacao", f"No mesmo disco da instalação ({inst.anchor})", drive,
                                  free_bytes(drive), True))
    return out


def human(n: int | None) -> str:
    if n is None:
        return "espaço livre desconhecido"
    for unit, size in (("TB", 1 << 40), ("GB", 1 << 30), ("MB", 1 << 20)):
        if n >= size:
            return f"{n / size:.1f} {unit}".replace(".", ",")
    return f"{n} bytes"


def move(src: Path, dst: Path, progress=None) -> list[str]:
    """Move the installed packs to the new folder. Returns what was moved; refuses to overwrite."""
    src, dst = Path(src), Path(dst)
    if src.resolve() == dst.resolve():
        return []
    moved = []
    dst.mkdir(parents=True, exist_ok=True)
    for sub in SUBDIRS:
        a, b = src / sub, dst / sub
        if not a.is_dir():
            continue
        if b.exists() and any(b.iterdir()):
            raise FileExistsError(f"A pasta de destino já tem '{sub}'. Escolha uma pasta vazia ou apague-a antes.")
        if progress:
            progress(f"Movendo {sub}…")
        if b.exists():
            b.rmdir()
        shutil.move(str(a), str(b))
        moved.append(sub)
    return moved


def apply(store, path: Path) -> None:
    store.set_setting(SETTING, str(Path(path)))
