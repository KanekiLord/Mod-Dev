#!/usr/bin/env python3
"""Build the Windows executable folder + ZIP with PyInstaller (run on Windows, e.g. in CI).

Output: dist/KaguyaStudio/ (KaguyaStudio.exe) and dist/KaguyaStudio-<versão>-windows.zip
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kaguya import VERSION  # noqa: E402

SEP = ";" if os.name == "nt" else ":"


def main() -> int:
    os.chdir(ROOT)
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", "KaguyaStudio",
           "--icon", str(ROOT / "assets" / "branding" / "kaguya.ico"),
           "--add-data", f"assets{SEP}assets", "--add-data", f"catalogo{SEP}catalogo",
           "--collect-submodules", "kaguya",
           "--exclude-module", "tkinter", "--exclude-module", "PySide6.QtWebEngineCore",
           "--exclude-module", "PySide6.Qt3DCore", "--exclude-module", "PySide6.QtQuick",
           "run_kaguya.py"]
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)
    out = ROOT / "dist" / "KaguyaStudio"
    for f in ("README.md", "CHANGELOG.md", "INICIAR_KAGUYA_STUDIO.bat", "INICIAR_SOMENTE_MASCOTES.bat"):
        if (ROOT / f).exists():
            shutil.copy2(ROOT / f, out / f)
    docs = out / "docs"
    docs.mkdir(exist_ok=True)
    for f in (ROOT / "docs").glob("*.md"):
        shutil.copy2(f, docs / f.name)
    zpath = ROOT / "dist" / f"KaguyaStudio-{VERSION}-windows.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in out.rglob("*"):
            z.write(p, Path("KaguyaStudio") / p.relative_to(out))
    print(f"ZIP: {zpath} ({zpath.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
