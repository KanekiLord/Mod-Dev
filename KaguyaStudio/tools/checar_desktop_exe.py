"""CI check: start ``KaguyaStudio.exe --mcp-desktop`` exactly as Claude Code/Codex do (stdio pipes) and use
the real Windows backend: list windows, capture the screen, move the mouse and read it back.

Usage: python tools/checar_desktop_exe.py <exe> <saida.png>
"""
import base64
import json
import subprocess
import sys


def main(exe: str, out_png: str) -> int:
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "list_windows", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "screenshot", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "move_mouse", "arguments": {"x": 200, "y": 150}}},
            {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "press_keys", "arguments": {"keys": "shift"}}}]
    p = subprocess.run([exe, "--mcp-desktop"], input="\n".join(json.dumps(m) for m in msgs) + "\n",
                       capture_output=True, text=True, timeout=120)
    print("codigo:", p.returncode, "stderr:", p.stderr[-800:])
    replies = {r["id"]: r for r in (json.loads(l) for l in p.stdout.splitlines() if l.strip())}
    assert set(replies) == {1, 2, 3, 4, 5, 6}, f"respostas: {sorted(replies)}\n{p.stdout[:2000]}"
    assert replies[1]["result"]["serverInfo"]["name"] == "kaguya_desktop"
    print("ferramentas:", [t["name"] for t in replies[2]["result"]["tools"]])
    for i in (3, 4, 5, 6):
        res = replies[i]["result"]
        texts = [c.get("text", "") for c in res["content"] if c["type"] == "text"]
        print(f"#{i} erro={res['isError']} {' | '.join(texts)[:300]}")
        assert not res["isError"], res
    img = [c for c in replies[4]["result"]["content"] if c["type"] == "image"][0]
    png = base64.b64decode(img["data"])
    assert png.startswith(b"\x89PNG") and len(png) > 1000, len(png)
    with open(out_png, "wb") as fh:
        fh.write(png)
    print(f"captura real de tela: {len(png)} bytes -> {out_png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
