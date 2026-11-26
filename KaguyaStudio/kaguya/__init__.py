"""Kaguya Studio 4 — Codex + Claude Code + Segundo Cérebro (Obsidian).

Core packages are UI-independent (standard library only); the PySide6 interface lives in
``kaguya.ui``. Nothing here calls a billed API, extracts tokens or uses private endpoints:
agents run through the official, already-authenticated CLIs.
"""
from __future__ import annotations

VERSION = "5.8.1"
APP_NAME = "Kaguya Studio"
