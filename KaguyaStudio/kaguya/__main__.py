import sys

if "--mcp-desktop" in sys.argv[1:]:
    from kaguya.desktop.server import serve
    raise SystemExit(serve())

from kaguya.ui.app import main

raise SystemExit(main())
