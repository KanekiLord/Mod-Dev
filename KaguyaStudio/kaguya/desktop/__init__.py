"""Computer use for the assistants: a small local MCP server of the Studio itself.

It is passed to Claude Code / Codex only for tasks where the user turned on "Usar o PC"; nothing is
installed into the user's own CLI configuration. See ``server.py`` (tools), ``backend.py`` (Windows
input/screen through the system API) and ``control.py`` (stop flag, activity log, failsafes).
"""
