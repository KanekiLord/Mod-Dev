"""Launcher used by the Windows build (PyInstaller) and by INICIAR_KAGUYA_STUDIO.bat."""
from kaguya.ui.app import main

if __name__ == "__main__":
    raise SystemExit(main())
