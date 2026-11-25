"""Isolated reader process: ``python -m kaguya.reader <file>`` → one JSON line on stdout."""
import json
import sys

from .core import read


def main(argv: list[str]) -> int:
    if not argv:
        print("uso: python -m kaguya.reader <arquivo>", file=sys.stderr)
        return 2
    res = read(argv[0])
    data = (json.dumps(res.to_dict(), ensure_ascii=False) + "\n").encode("utf-8")
    from ..desktop.server import _stdio   # binary stdout, also in the windowed .exe (no console)
    _fin, out = _stdio()
    out.write(data)
    out.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
