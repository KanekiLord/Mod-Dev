"""Launcher used by the Windows build (PyInstaller) and by INICIAR_KAGUYA_STUDIO.bat."""
import sys

if __name__ == "__main__":
    if "--mcp-browser" in sys.argv[1:]:
        # Kaguya Browser tools for Claude Code / Codex (stdio; forwards to the running Studio)
        from kaguya.browser.mcp import serve as serve_browser
        raise SystemExit(serve_browser())
    if "--mcp-desktop" in sys.argv[1:]:
        # desktop-control MCP server for Claude Code / Codex (stdio; no window, no Qt)
        from kaguya.desktop.server import serve
        raise SystemExit(serve())
    from kaguya.ui.app import main
    raise SystemExit(main())
