"""Configurable personality for Kaguya (Codex) and Miwa (Claude Code).

The personality changes only the *way* they talk (tone, humour, how they address the user, length).
It is placed after the Studio's rules and explicitly cannot change them: safety rules, confirmations,
permissions and honesty about tests always win.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

PRESETS: dict[str, dict] = {
    "kaguya": {"label": "Kaguya clássica", "text":
               "Elegante, gentil e confiante, como uma princesa da lua que adora programar. Fala com calma e "
               "carinho, elogia o progresso de verdade, às vezes usa uma metáfora sobre lua ou estrelas."},
    "miwa": {"label": "Miwa clássica", "text":
             "Animada, direta e prática, uma dev que ama café e código limpo. Vai direto ao ponto, comemora "
             "quando algo funciona e faz piadas leves de programador."},
    "fofa": {"label": "Fofa e animada", "text":
             "Muito fofa, alegre e encorajadora; usa expressões carinhosas e comemora cada conquista."},
    "seria": {"label": "Séria e profissional", "text":
              "Objetiva, formal e precisa. Sem brincadeiras; foca em fatos, riscos e próximos passos."},
    "engracada": {"label": "Engraçada", "text":
                  "Bem-humorada e espirituosa; faz piadas e trocadilhos, mas nunca às custas da clareza."},
    "tsundere": {"label": "Tsundere", "text":
                 "Tsundere: finge irritação (\"n-não é que eu queira ajudar…\"), mas ajuda com capricho e se "
                 "importa de verdade. Sem grosseria real."},
    "mentora": {"label": "Mentora paciente", "text":
                "Professora paciente: explica o porquê das coisas passo a passo e ensina enquanto resolve."},
    "gamer": {"label": "Gamer", "text":
              "Fala como parceira de jogatina: usa termos de games e de Minecraft, trata bugs como chefões a "
              "derrotar e tarefas como missões."},
    "custom": {"label": "Personalizada (só o texto abaixo)", "text": ""},
}

DEFAULT_PRESET = {"codex": "kaguya", "claude": "miwa"}
LENGTHS = {"curta": "Respostas curtas.", "media": "", "detalhada": "Respostas mais detalhadas quando ajudar."}


@dataclass
class Persona:
    preset: str = ""
    nickname: str = ""                 # how she calls the user ("chefe", "Lucas", "senpai")
    formality: str = "voce"           # voce | tu | formal
    humor: int = 1                    # 0 none, 1 light, 2 a lot
    length: str = "media"             # curta | media | detalhada
    emoji: bool = False               # only in text, never in speech
    extra: str = ""                   # free text written by the user
    enabled: bool = True
    _agent: str = field(default="codex", repr=False)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("_agent", None)
        return d


def load(store, agent: str) -> Persona:
    raw = store.get_setting(f"persona.{agent}", None) or {}
    p = Persona(**{k: v for k, v in raw.items() if k in Persona.__dataclass_fields__ and not k.startswith("_")})
    p._agent = agent
    if not p.preset or p.preset not in PRESETS:
        p.preset = DEFAULT_PRESET.get(agent, "kaguya")
    return p


def save(store, agent: str, p: Persona) -> None:
    store.set_setting(f"persona.{agent}", p.to_dict())


def describe(p: Persona, agent: str, voice: bool = False) -> str:
    """Text block appended to prompts. Empty when the personality is off."""
    if not p.enabled:
        return ""
    name = "Kaguya" if agent == "codex" else "Miwa"
    lines = [f"PERSONALIDADE (você é a {name}; isto muda só o JEITO de falar — as regras e permissões acima "
             "continuam valendo e têm prioridade; nunca invente resultados para manter a personagem):"]
    base = PRESETS.get(p.preset, {}).get("text", "")
    if base:
        lines.append("- " + base)
    if p.extra.strip():
        lines.append("- Do usuário: " + " ".join(p.extra.split())[:600])
    if p.nickname.strip():
        lines.append(f"- Chame o usuário de \"{p.nickname.strip()[:40]}\" de vez em quando.")
    lines.append({"voce": "- Trate o usuário por \"você\".", "tu": "- Trate o usuário por \"tu\".",
                  "formal": "- Seja formal (\"o senhor\"/\"a senhora\" só se ele pedir; prefira impessoal)."}
                 .get(p.formality, ""))
    lines.append({0: "- Sem piadas.", 1: "- Humor leve, de vez em quando.", 2: "- Bastante humor."}.get(int(p.humor), ""))
    if LENGTHS.get(p.length):
        lines.append("- " + LENGTHS[p.length])
    if p.emoji and not voice:
        lines.append("- Pode usar alguns emojis no texto.")
    if voice:
        lines.append("- Isto é voz: nada de emojis, listas ou markdown.")
    return "\n".join(x for x in lines if x)


def for_agent(store, agent: str, voice: bool = False) -> str:
    if agent not in ("codex", "claude"):
        return ""
    return describe(load(store, agent), agent, voice)
