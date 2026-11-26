import sys

if "--ler-arquivo" in sys.argv[1:]:
    from kaguya.reader.__main__ import main as read_main
    raise SystemExit(read_main(sys.argv[sys.argv.index("--ler-arquivo") + 1:]))

if "--baixar-modelo" in sys.argv[1:]:
    from kaguya.voice.stt import main as model_main
    raise SystemExit(model_main(sys.argv[sys.argv.index("--baixar-modelo") + 1:]))

if "--mcp-browser" in sys.argv[1:]:
    from kaguya.browser.mcp import serve as serve_browser
    raise SystemExit(serve_browser())

if "--mcp-desktop" in sys.argv[1:]:
    from kaguya.desktop.server import serve
    raise SystemExit(serve())

from kaguya.ui.app import main

raise SystemExit(main())
