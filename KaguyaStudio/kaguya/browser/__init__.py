"""Kaguya Browser: a real browser inside the Studio (QtWebEngine) with per-tab, opt-in sharing with the assistants.

* ``data``    — favourites and history (SQLite; private tabs record nothing).
* ``share``   — who may read / control each tab, one controller at a time, and a timeline of every access.
* ``page``    — what is extracted from a shared tab and how it reaches an assistant (as untrusted data).
* ``youtube`` — YouTube Intelligence: metadata (A), captions/transcript (B), frames the user captures (C).
"""
