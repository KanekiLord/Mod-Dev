"""Music commands in Portuguese, handled locally (no AI call, no tokens).

Returns (action, argument) or None. Examples: "pausa a música", "próxima", "volume 30%",
"abaixa a música", "toca minhas músicas", "toca a playlist Foco", "toca Naruto opening".
"""
from __future__ import annotations

import re

from .library import norm

_MUSIC = r"(?:a |as )?(?:musica|musicas|som|playlist|faixa)"


def parse(text: str) -> tuple[str, str] | None:
    n = norm(text).strip(" .!?,")
    n = re.sub(r"^(?:por favor[, ]*|kaguya[, ]*|miwa[, ]*)+", "", n).strip()
    if not n:
        return None
    if re.fullmatch(rf"(?:pausa|pause|pausar|para|pare|parar)(?: {_MUSIC})?(?: enquanto .*)?", n):
        return ("pause", "")
    if re.fullmatch(rf"(?:continua|continuar|retoma|retomar|despausa|volta a tocar|play)(?: {_MUSIC})?", n):
        return ("resume", "")
    if re.fullmatch(rf"(?:proxima|pula|pular|avanca|passa)(?: {_MUSIC})?", n):
        return ("next", "")
    if re.fullmatch(rf"(?:anterior|volta|voltar)(?: {_MUSIC})?(?: anterior)?", n) and "volume" not in n:
        return ("previous", "")
    m = re.fullmatch(r"(?:coloca |deixa |poe |muda )?(?:o )?volume(?: da musica)?(?: para| pra| em| no)? (\d{1,3}) ?(?:%|por cento)?", n)
    if not m:
        m = re.fullmatch(rf"(?:abaixa|diminui|reduz|aumenta|sobe)(?: {_MUSIC})?(?: o volume)?(?: para| pra) (\d{{1,3}}) ?(?:%|por cento)?", n)
    if m:
        return ("volume", str(max(0, min(100, int(m.group(1))))))
    if re.fullmatch(rf"(?:abaixa|diminui|reduz)(?: o volume)?(?: d?a? ?{_MUSIC})?(?: um pouco)?", n):
        return ("volume_down", "")
    if re.fullmatch(rf"(?:aumenta|sobe)(?: o volume)?(?: d?a? ?{_MUSIC})?(?: um pouco)?", n):
        return ("volume_up", "")
    if re.fullmatch(r"(?:desliga|desligar|tira|tirar|desativa|sai do)(?: o)?(?: modo)? (?:aleatorio|embaralhar|shuffle)", n):
        return ("shuffle", "off")
    if re.fullmatch(rf"(?:liga|ligar|ativa|ativar|coloca|poe|bota|deixa|modo|toca)?(?: (?:o|no|em))?(?: modo)? "
                    rf"?(?:aleatorio|embaralha|embaralhar|shuffle)(?: (?:as )?musicas?)?", n):
        return ("shuffle", "on")
    if re.fullmatch(r"(?:que|qual) (?:musica|som) (?:e essa|esta tocando|ta tocando)", n):
        return ("status", "")
    m = re.fullmatch(r"(?:coloca|adiciona|bota|poe) (.+?) na fila(?: de musica| da musica)?(?: para depois| pra depois)?", n)
    if m and not re.search(r"\b(tarefa|task|codigo|bug)\b", m.group(1)):
        return ("queue", m.group(1).strip())
    words = r"(?: (musica|musicas|trilha|trilhas|som|sons|playlist|cancao|cancoes|abertura|album))"
    # "toca/tocar/play" are always about music; "coloca/põe/bota" only with a music word (avoid "coloca o botão…")
    m = re.fullmatch(r"(?:toca|tocar|play)(?: (?:uma|umas|a|as|o|os|minha|minhas|meu|meus))?"
                     r"(?: (?:musica|musicas|trilha|trilhas|som|sons))?(?: locais| local| de novo)?(?: (.+))?", n)
    kind = ""
    if not m:
        m = re.fullmatch(r"(?:coloca|poe|bota)(?: (?:uma|umas|a|as|o|os|minha|minhas|meu|meus))?"
                         + words + r"(?: locais| local)?(?: (.+))?", n)
        if m:
            kind = m.group(1)
            arg = (m.group(2) or "").strip()
            if kind == "playlist" and arg:
                return ("playlist", arg)
            if kind == "abertura" and arg:
                arg = f"abertura {arg}"
            if re.search(r"\b(youtube|spotify|amazon)\b", arg):
                return ("external", arg)
            return ("play", arg)
    if m:
        arg = (m.group(1) or "").strip()
        p = re.match(r"(?:a |uma )?playlist (.+)", arg)
        if p:
            return ("playlist", p.group(1).strip())
        if re.search(r"\b(youtube|spotify|amazon)\b", arg):
            return ("external", arg)
        return ("play", arg)
    m = re.fullmatch(r"(?:coloca|poe|bota) (.+) no (youtube|spotify|amazon(?: music)?)", n)
    if m:
        return ("external", f"{m.group(1)} no {m.group(2)}")
    return None
