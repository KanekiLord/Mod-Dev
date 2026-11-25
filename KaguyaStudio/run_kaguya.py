"""Launcher used by the Windows build (PyInstaller) and by INICIAR_KAGUYA_STUDIO.bat."""
import sys

if __name__ == "__main__":
    if "--ler-arquivo" in sys.argv[1:]:
        # Leitor Universal in its own process (called by the Studio itself)
        from kaguya.reader.__main__ import main as read_main
        i = sys.argv.index("--ler-arquivo")
        raise SystemExit(read_main(sys.argv[i + 1:]))
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
