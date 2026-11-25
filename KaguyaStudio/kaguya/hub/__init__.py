"""Kaguya Extension Hub: discovers, tracks and verifies the MCPs, plugins, skills, agents, commands and hooks that
Codex and Claude Code already have — read-only by default — and lets the Studio route work to the assistant that
REALLY has a capability. Installing/updating/removing only through the official CLIs, after the user approves a plan.

Golden rule (package 00_INICIO): detected ≠ configured ≠ enabled ≠ loaded in a session ≠ connected ≠ verified.
Each state needs its own evidence; nothing is shown as available because a file exists on disk.

* ``model``     — Extension descriptor, states and identity.
* ``redact``    — secrets never leave the config files (env values, headers, tokens in URLs/args).
* ``adapters``  — Claude Code and Codex discovery (files + official read-only CLI listings).
* ``registry``  — SQLite catalogue, reconciliation (added/changed/removed, history kept) and audit trail.
* ``watcher``   — change detection by polling with debounce (partial writes ignored).
* ``probe``     — capability checks through official means (claude mcp get, session init, MCP tools/list).
* ``lifecycle`` — install/update/remove plans → approval → official CLI command → rescan.
* ``router``    — who has which capability; delegation between Kaguya and Miwa; locks for 3D files.
"""
