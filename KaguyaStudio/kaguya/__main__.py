import sys

if "--mcp-browser" in sys.argv[1:]:
    from kaguya.browser.mcp import serve as serve_browser
    raise SystemExit(serve_browser())

if "--mcp-desktop" in sys.argv[1:]:
    from kaguya.desktop.server import serve
    raise SystemExit(serve())

from kaguya.ui.app import main

raise SystemExit(main())
