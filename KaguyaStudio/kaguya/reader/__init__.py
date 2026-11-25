"""Leitor Universal: what the Studio can read from a file the user authorised, safely.

Text, code, logs, Markdown, JSON/YAML/CSV, Word/Excel/PowerPoint (text, tables, formulas as text — macros are never
run), PDF (text layer), ZIP/JAR/APK (listing and Minecraft mod metadata — nothing is extracted to disk or run) and
images (dimensions; the picture itself goes to the assistant as an attachment).

Rules (spec 02): format detected by signature first; size/time limits; sensitive files (.env, keys, credentials…)
refused; paths outside the authorised folders refused; parsing of complex formats in a separate process; only the
relevant excerpts are sent when there is a question; everything read is DATA, never instructions.
"""
from .core import (ReadResult, Piece, check_allowed, detect, is_sensitive, read, read_isolated,  # noqa: F401
                   SUPPORTED)
