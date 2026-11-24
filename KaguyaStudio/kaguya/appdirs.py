"""Where Kaguya Studio keeps its own data (never inside the user's vault or projects)."""
from __future__ import annotations

import os
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
ASSETS = APP_ROOT / "assets"
CATALOG = APP_ROOT / "catalogo" / "agentes.json"


def data_dir() -> Path:
    """%LOCALAPPDATA%\\KaguyaStudio on Windows, ~/.kaguya-studio elsewhere.

    ``KAGUYA_HOME`` overrides it (used by tests and portable installs).
    """
    override = os.environ.get("KAGUYA_HOME")
    if override:
        base = Path(override)
    elif os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        base = Path(os.environ["LOCALAPPDATA"]) / "KaguyaStudio"
    else:
        base = Path.home() / ".kaguya-studio"
    base.mkdir(parents=True, exist_ok=True)
    return base


def legacy_v3_database() -> Path | None:
    """Location used by V3.x (``%LOCALAPPDATA%\\KaguyaStudioV3\\studio.sqlite3``)."""
    candidates = []
    if os.environ.get("LOCALAPPDATA"):
        candidates.append(Path(os.environ["LOCALAPPDATA"]) / "KaguyaStudioV3" / "studio.sqlite3")
    candidates.append(Path.home() / ".kaguya-studio" / "KaguyaStudioV3" / "studio.sqlite3")
    for path in candidates:
        if path.is_file():
            return path
    return None
