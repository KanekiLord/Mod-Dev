"""Secrets never leave the original config: env values, headers, tokens in URLs or arguments are masked."""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SECRET_KEY = re.compile(r"(key|token|secret|passw|pwd|auth|bearer|cookie|session|credential|api[_-]?id|private)", re.I)
SECRET_VALUE = re.compile(r"(sk-[A-Za-z0-9_\-]{8,}|sk_[A-Za-z0-9]{8,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
                          r"xox[abp]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_\-]{20,}|eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]+|"
                          r"Bearer\s+[A-Za-z0-9._\-]{8,})")
MASK = "***"


def value(text: str) -> str:
    return SECRET_VALUE.sub(MASK, text or "")


def url(u: str) -> str:
    """Keep scheme/host/path; mask credentials and secret-looking query parameters."""
    try:
        parts = urlsplit(u or "")
    except ValueError:
        return value(u)
    netloc = parts.netloc
    if "@" in netloc:
        netloc = MASK + "@" + netloc.split("@", 1)[1]
    query = urlencode([(k, MASK if SECRET_KEY.search(k) else value(v)) for k, v in parse_qsl(parts.query,
                                                                                            keep_blank_values=True)])
    return value(urlunsplit((parts.scheme, netloc, parts.path, query, "")))


def args(items: list) -> list[str]:
    """Mask the value after a secret-looking flag (``--api-key X``, ``--token=X``) and secret-looking literals."""
    out, hide_next = [], False
    for a in [str(x) for x in (items or [])]:
        if hide_next:
            out.append(MASK)
            hide_next = False
            continue
        if a.startswith("-") and "=" in a and SECRET_KEY.search(a.split("=", 1)[0]):
            out.append(a.split("=", 1)[0] + "=" + MASK)
            continue
        if a.startswith("-") and SECRET_KEY.search(a):
            out.append(a)
            hide_next = True
            continue
        out.append(value(a))
    return out


def command_line(command: str, arguments: list | None) -> str:
    return " ".join([value(command or "")] + args(arguments or [])).strip()
