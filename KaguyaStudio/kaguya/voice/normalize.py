"""Prepare text for Brazilian-Portuguese speech without changing what the chat shows.

Numbers, dates, times, percentages, money, versions, units, abbreviations, file names and code identifiers are
written the way a person would say them. Long URLs and code blocks are summarised ("link", "trecho de código").
Pure functions, no dependencies — the same text goes to every TTS engine.
"""
from __future__ import annotations

import re

_UNITS = ["zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez", "onze", "doze",
          "treze", "quatorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove"]
_TENS = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
_HUNDREDS = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos", "setecentos",
             "oitocentos", "novecentos"]
_MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
           "novembro", "dezembro"]
_FEM = {"um": "uma", "dois": "duas"}


def _below_1000(n: int) -> str:
    if n < 20:
        return _UNITS[n]
    if n < 100:
        t, u = divmod(n, 10)
        return _TENS[t] + (f" e {_UNITS[u]}" if u else "")
    if n == 100:
        return "cem"
    h, rest = divmod(n, 100)
    return _HUNDREDS[h] + (f" e {_below_1000(rest)}" if rest else "")


def number(n: int, feminine: bool = False) -> str:
    """Cardinal number in pt-BR words (up to the trillions)."""
    if n < 0:
        return "menos " + number(-n, feminine)
    if n < 1000:
        words = _below_1000(n)
    else:
        groups = []  # (group value, words)
        for value, sing, plur in ((10 ** 12, "trilhão", "trilhões"), (10 ** 9, "bilhão", "bilhões"),
                                  (10 ** 6, "milhão", "milhões"), (1000, "mil", "mil"), (1, "", "")):
            q, n = divmod(n, value)
            if q:
                if value == 1:
                    groups.append((q, _below_1000(q)))
                elif value == 1000:
                    groups.append((q, "mil" if q == 1 else f"{_below_1000(q)} mil"))
                else:
                    groups.append((q, f"{number(q)} {sing if q == 1 else plur}"))
        # "e" before the last group when it is below 100 or a round hundred: "dois mil e cinco",
        # "dois milhões e quinhentos mil", "mil e cem"
        words = groups[0][1]
        for i, (q, w) in enumerate(groups[1:], 1):
            last = i == len(groups) - 1
            words += (" e " if last and (q < 100 or q % 100 == 0) else " ") + w
    if feminine:
        words = re.sub(r"\b(um|dois)$", lambda m: _FEM[m.group(1)], words)
        words = re.sub(r"\b(um|dois)( mil)", lambda m: _FEM[m.group(1)] + m.group(2), words)
    return words


def _decimal(intpart: str, frac: str) -> str:
    frac = frac.rstrip("0") or "0"
    head = number(int(intpart.replace(".", "")))
    if len(frac) <= 2 and not frac.startswith("0"):
        return f"{head} vírgula {number(int(frac))}"
    return f"{head} vírgula " + " ".join(_UNITS[int(d)] for d in frac)


ABBREV = {
    r"\bSr\.": "senhor", r"\bSra\.": "senhora", r"\bDr\.": "doutor", r"\bDra\.": "doutora", r"\bProf\.": "professor",
    r"\bex\.": "por exemplo", r"\betc\.": "etcétera", r"\bp\.\s?ex\.": "por exemplo", r"\bvs\.?\b": "versus",
    r"\bobs\.": "observação", r"\bpág\.": "página", r"\bnº": "número", r"\bn\.º": "número",
}
# technical words that TTS engines tend to spell badly
WORDS = {
    r"\bGPU\b": "gê pê u", r"\bCPU\b": "cê pê u", r"\bVRAM\b": "vê ram", r"\bRAM\b": "ram", r"\bUI\b": "u i",
    r"\bAPI\b": "a pê i", r"\bCLI\b": "cê éle i", r"\bIA\b": "i a", r"\bIAs\b": "i as", r"\bPDF\b": "pê dê éfe",
    r"\bURL\b": "u érre éle", r"\bJSON\b": "jêison", r"\bHUD\b": "rudi", r"\bMCP\b": "eme cê pê",
    r"\bPyTorch\b": "pai tórtchi", r"\bCUDA\b": "cuda", r"\bGitHub\b": "guít rãb", r"\bGit\b": "guít",
    r"\bWindows\b": "uíndous", r"\bMinecraft\b": "máinquréfti", r"\bForge\b": "fórdj", r"\bGradle\b": "grêidou",
    r"\bCodex\b": "códex", r"\bClaude\b": "clóud", r"\bPython\b": "páiton", r"\bJava\b": "java",
    r"\bOK\b": "o quêi", r"\bok\b": "o quêi",
}
UNITS = {"GB": ("gigabyte", "gigabytes"), "MB": ("megabyte", "megabytes"), "KB": ("kilobyte", "kilobytes"),
         "TB": ("terabyte", "terabytes"), "km": ("quilômetro", "quilômetros"), "ms": ("milissegundo", "milissegundos"),
         "min": ("minuto", "minutos"), "h": ("hora", "horas"), "s": ("segundo", "segundos"), "kg": ("quilo", "quilos"),
         "MHz": ("mega-hertz", "mega-hertz"), "GHz": ("giga-hertz", "giga-hertz"), "fps": ("quadro por segundo", "quadros por segundo")}
EXT = {"py": "pai", "js": "jota ésse", "ts": "tê ésse", "md": "eme dê", "json": "jêison", "java": "java", "txt": "tê xis tê",
       "exe": "exe", "zip": "zip", "png": "pê ene gê", "jpg": "jota pê gê", "csv": "cê ésse vê", "toml": "tômou",
       "yml": "iâmou", "yaml": "iâmou", "html": "agá tê eme éle", "css": "cê ésse ésse", "bat": "bat", "jar": "jar"}


def normalize(text: str, limit: int = 1800) -> str:
    t = text or ""
    t = re.sub(r"```.*?```", " (trecho de código omitido) ", t, flags=re.S)
    t = re.sub(r"https?://\S+", " link ", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"[#*_>|~]{1,}(?=\s|\w)", " ", t)
    t = re.sub(r"^\s*[-•]\s*", "", t, flags=re.M)
    for pat, rep in ABBREV.items():
        t = re.sub(pat, rep, t, flags=re.I)
    # dates 25/11/2026 → 25 de novembro de 2026
    t = re.sub(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b",
               lambda m: (f"{'primeiro' if int(m.group(1)) == 1 else number(int(m.group(1)))} de "
                          f"{_MONTHS[int(m.group(2)) - 1]} de {number(int(m.group(3)))}")
               if 1 <= int(m.group(2)) <= 12 else m.group(0), t)
    # times 14:35 / 14h35 / 14h
    t = re.sub(r"\b([01]?\d|2[0-3])(?::|h)([0-5]\d)\b",
               lambda m: f"{number(int(m.group(1)), True)} {'hora' if int(m.group(1)) == 1 else 'horas'}"
                         + (f" e {number(int(m.group(2)))} {'minuto' if int(m.group(2)) == 1 else 'minutos'}"
                            if int(m.group(2)) else ""), t)
    # versions 1.7.10 / v2.1.331
    t = re.sub(r"\bv?(\d+)\.(\d+)\.(\d+)\b", lambda m: " ponto ".join(number(int(g)) for g in m.groups()), t)
    # money R$ 1.234,50
    t = re.sub(r"R\$\s?(\d{1,3}(?:\.\d{3})*|\d+)(?:,(\d{2}))?",
               lambda m: number(int(m.group(1).replace(".", ""))) + (" real" if m.group(1) == "1" else " reais")
                         + (f" e {number(int(m.group(2)))} centavos" if m.group(2) and int(m.group(2)) else ""), t)
    # percentages 30% / 2,5%
    t = re.sub(r"(\d+)(?:,(\d+))?\s?%", lambda m: (_decimal(m.group(1), m.group(2)) if m.group(2) else
                                                   number(int(m.group(1)))) + " por cento", t)
    # ordinals 1º 2ª
    t = re.sub(r"\b(\d+)([ºª])", lambda m: {1: "primeir", 2: "segund", 3: "terceir", 4: "quart", 5: "quint"}.get(
        int(m.group(1)), number(int(m.group(1))) + " ") + ("o" if m.group(2) == "º" and int(m.group(1)) <= 5 else
                                                             "a" if int(m.group(1)) <= 5 else ""), t)
    # number + unit (8 GB, 500 ms)
    def unit(m):
        n = m.group(1)
        val = _decimal(*n.split(",")) if "," in n else number(int(n.replace(".", "")))
        sing, plur = UNITS[m.group(2)]
        return f"{val} {sing if n == '1' else plur}"
    t = re.sub(r"\b(\d+(?:,\d+)?)\s?(" + "|".join(sorted(map(re.escape, UNITS), key=len, reverse=True)) + r")\b", unit, t)
    # file names main.py → main ponto pai
    t = re.sub(r"\b([\w-]+)\.(" + "|".join(EXT) + r")\b", lambda m: f"{m.group(1)} ponto {EXT[m.group(2).lower()]}", t)
    # code identifiers: snake_case / camelCase → words
    t = re.sub(r"\b([a-z]+(?:_[a-z0-9]+)+)\b", lambda m: m.group(1).replace("_", " "), t)
    t = re.sub(r"\b([a-z]+)([A-Z][a-z]+)+\b", lambda m: re.sub(r"(?<!^)(?=[A-Z])", " ", m.group(0)).lower(), t)
    for pat, rep in WORDS.items():
        t = re.sub(pat, rep, t)
    # decimals 2,5 and plain numbers 1.234 / 42
    t = re.sub(r"\b(\d{1,3}(?:\.\d{3})+|\d+),(\d+)\b", lambda m: _decimal(m.group(1), m.group(2)), t)
    t = re.sub(r"\b(\d{1,3}(?:\.\d{3})+)\b", lambda m: number(int(m.group(1).replace(".", ""))), t)
    t = re.sub(r"\b\d{1,15}\b", lambda m: number(int(m.group(0))), t)
    t = t.replace("&", " e ").replace("+", " mais ").replace("=", " igual a ").replace("°C", " graus").replace("°", " graus")
    t = re.sub(r"\s+", " ", t).strip()
    return t[:limit]
