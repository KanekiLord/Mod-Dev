"""Configurable personality for Kaguya (Codex) and Miwa (Claude Code).

A personality is a *presentation* layer: tone, humour, initiative, how the user is addressed, name.
It is placed after the Studio's rules and explicitly cannot change them — permissions, confirmations,
safety and honesty about tests always win (spec 04, "isolamento essencial"). ``persona_id`` (kaguya/miwa) and
``provider_id`` (codex/claude) stay separate: renaming a character never touches CLI logins or logs.

Storage: global profile ``persona.<provider>`` and optional per-project override ``persona.<provider>.p<id>``.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import json

PERSONA_ID = {"codex": "kaguya", "claude": "miwa"}
DEFAULT_NAME = {"codex": "Kaguya", "claude": "Miwa"}

PRESETS: dict[str, dict] = {
    "kaguya": {"label": "Kaguya clássica", "text":
               "Conselheira técnica e estrategista: elegante, gentil e confiante, como uma princesa da lua que adora "
               "programar. Fala com calma e carinho, elogia o progresso de verdade, às vezes usa uma metáfora sobre "
               "lua ou estrelas.",
               "values": {"formality": 60, "humor": 35, "initiative": 80, "warmth": 65, "creativity": 55,
                          "objectivity": 60, "detail": 45}},
    "miwa": {"label": "Miwa clássica", "text":
             "Analítica, curiosa e criativa, uma dev investigadora que ama café e código limpo. Vai direto ao ponto, "
             "paciente para explicar, com humor discreto de programadora.",
             "values": {"formality": 50, "humor": 35, "initiative": 70, "warmth": 55, "creativity": 65,
                        "objectivity": 70, "detail": 50}},
    "profissional": {"label": "Profissional", "text": "Objetiva, formal e precisa. Foca em fatos, riscos e próximos passos.",
                     "values": {"formality": 85, "humor": 5, "initiative": 60, "warmth": 35, "creativity": 35,
                                "objectivity": 90, "detail": 50}},
    "descontraida": {"label": "Descontraída", "text": "Leve, amigável e bem-humorada, como uma colega de time animada.",
                     "values": {"formality": 20, "humor": 70, "initiative": 65, "warmth": 75, "creativity": 65,
                                "objectivity": 55, "detail": 40}},
    "estrategista": {"label": "Estrategista", "text":
                     "Pensa à frente: aponta riscos, alternativas e o próximo passo mais valioso antes de agir.",
                     "values": {"formality": 60, "humor": 20, "initiative": 90, "warmth": 45, "creativity": 60,
                                "objectivity": 80, "detail": 60}},
    "professora": {"label": "Professora", "text":
                   "Mentora paciente: explica o porquê das coisas passo a passo e ensina enquanto resolve.",
                   "values": {"formality": 50, "humor": 30, "initiative": 60, "warmth": 80, "creativity": 50,
                              "objectivity": 65, "detail": 80}},
    "fofa": {"label": "Fofa e animada", "text": "Muito fofa, alegre e encorajadora; comemora cada conquista.",
             "values": {"formality": 20, "humor": 55, "initiative": 60, "warmth": 95, "creativity": 60,
                        "objectivity": 45, "detail": 40}},
    "tsundere": {"label": "Tsundere", "text":
                 "Tsundere: finge irritação (\"n-não é que eu queira ajudar…\"), mas ajuda com capricho e se importa "
                 "de verdade. Sem grosseria real.",
                 "values": {"formality": 35, "humor": 60, "initiative": 70, "warmth": 60, "creativity": 60,
                            "objectivity": 60, "detail": 40}},
    "gamer": {"label": "Gamer", "text":
              "Parceira de jogatina: termos de games e de Minecraft, bugs são chefões e tarefas são missões.",
              "values": {"formality": 20, "humor": 65, "initiative": 70, "warmth": 65, "creativity": 70,
                         "objectivity": 55, "detail": 40}},
    "custom": {"label": "Personalizada (só o texto livre)", "text": "", "values": {}},
}
DEFAULT_PRESET = {"codex": "kaguya", "claude": "miwa"}
SLIDERS = [("formality", "Formalidade"), ("humor", "Humor"), ("initiative", "Iniciativa"), ("warmth", "Empatia"),
           ("creativity", "Criatividade"), ("objectivity", "Objetividade"), ("detail", "Detalhe")]
PROACTIVE = {"marcos": "Avisar marcos importantes e erros", "erros": "Só falar por conta própria em erros",
             "livre": "Conversa livre (comenta e sugere)", "silencioso": "Silenciosa enquanto programa"}


@dataclass
class Persona:
    preset: str = ""
    name: str = ""                     # character name shown in the UI and used in prompts ("" = default)
    nickname: str = ""                 # how she calls the user ("chefe", "Meu Lorde", "senpai")
    address: str = "voce"             # voce | tu | formal
    third_person: bool = False         # "Kaguya acha que…"
    greeting: str = ""                 # optional greeting style
    formality: int = -1                # 0..100; -1 = preset value
    humor: int = -1
    initiative: int = -1
    warmth: int = -1
    creativity: int = -1
    objectivity: int = -1
    detail: int = -1
    proactive: str = "marcos"
    emoji: bool = False                # text only, never in speech
    extra: str = ""                    # free text written by the user
    enabled: bool = True

    def value(self, key: str) -> int:
        v = getattr(self, key)
        if isinstance(v, int) and 0 <= v <= 100:
            return v
        return int(PRESETS.get(self.preset, {}).get("values", {}).get(key, 50))

    def to_dict(self) -> dict:
        return asdict(self)


def _migrate(raw: dict) -> dict:
    """Profiles saved by 4.9.0 (humor 0-2, length, formality voce/tu/formal) keep working."""
    raw = dict(raw)
    if isinstance(raw.get("humor"), int) and raw["humor"] in (0, 1, 2) and "initiative" not in raw:
        raw["humor"] = {0: 5, 1: 40, 2: 80}[raw["humor"]]
    if raw.get("formality") in ("voce", "tu", "formal"):
        raw["address"] = raw.pop("formality")
        if raw["address"] == "formal":
            raw["formality"] = 85
    if "length" in raw:
        raw["detail"] = {"curta": 20, "media": -1, "detalhada": 80}.get(raw.pop("length"), -1)
    if raw.get("preset") == "seria":
        raw["preset"] = "profissional"
    if raw.get("preset") == "mentora":
        raw["preset"] = "professora"
    if raw.get("preset") == "engracada":
        raw["preset"], raw["humor"] = "descontraida", 80
    return raw


def from_dict(raw: dict, agent: str) -> Persona:
    raw = _migrate(raw or {})
    names = {f.name for f in fields(Persona)}
    p = Persona(**{k: v for k, v in raw.items() if k in names})
    if p.preset not in PRESETS:
        p.preset = DEFAULT_PRESET.get(agent, "kaguya")
    p.address = p.address if p.address in ("voce", "tu", "formal") else "voce"
    p.proactive = p.proactive if p.proactive in PROACTIVE else "marcos"
    return p


def _key(agent: str, pid: int | None) -> str:
    return f"persona.{agent}" + (f".p{pid}" if pid is not None else "")


def has_project_override(store, agent: str, pid: int | None) -> bool:
    return pid is not None and store.get_setting(_key(agent, pid), None) is not None


def load(store, agent: str, pid: int | None = None) -> Persona:
    raw = store.get_setting(_key(agent, pid), None) if pid is not None else None
    if raw is None:
        raw = store.get_setting(_key(agent, None), None)
    return from_dict(raw or {}, agent)


def save(store, agent: str, p: Persona, pid: int | None = None) -> None:
    store.set_setting(_key(agent, pid), p.to_dict())


def clear_project(store, agent: str, pid: int) -> None:
    store.set_setting(_key(agent, pid), None)


def reset(store, agent: str, pid: int | None = None) -> Persona:
    p = Persona(preset=DEFAULT_PRESET.get(agent, "kaguya"))
    save(store, agent, p, pid)
    return p


def display_name(store, agent: str) -> str:
    return (load(store, agent).name or "").strip()[:24] or DEFAULT_NAME.get(agent, agent)


# --------------------------------------------------------------------------- export / import
def export_json(store, agents=("codex", "claude")) -> str:
    """Profiles only — never secrets, paths or permissions (there are none in a persona)."""
    profiles = []
    for a in agents:
        d = load(store, a).to_dict()
        profiles.append({"id": PERSONA_ID[a], "provider_default": a, "profile": d})
    return json.dumps({"schema_version": 2, "app": "Kaguya Studio", "profiles": profiles}, ensure_ascii=False, indent=2)


def import_json(store, text: str) -> list[str]:
    data = json.loads(text)
    done = []
    for item in data.get("profiles", []):
        agent = {"claude_code": "claude", "claude-code": "claude"}.get(item.get("provider_default"),
                                                                     item.get("provider_default"))
        if agent not in ("codex", "claude"):
            agent = {"kaguya": "codex", "miwa": "claude"}.get(item.get("id", ""))
        if agent not in ("codex", "claude"):
            continue
        prof = item.get("profile")
        if prof is None and "style" in item:  # format of the example in the requirements package
            st = item["style"]
            prof = {"name": item.get("name", ""), "nickname": st.get("address_user", ""),
                    "third_person": bool(st.get("self_reference_third_person")), "extra": st.get("behavior", "")}
            for src, dst in (("formality", "formality"), ("humor", "humor"), ("initiative", "initiative"),
                             ("warmth", "warmth"), ("verbosity", "detail")):
                if isinstance(st.get(src), (int, float)):
                    prof[dst] = int(round(float(st[src]) * 100 if st[src] <= 1 else st[src]))
            prof["preset"] = "custom" if prof.get("extra") else DEFAULT_PRESET[agent]
        p = from_dict({k: v for k, v in (prof or {}).items() if isinstance(k, str)}, agent)
        p.extra = p.extra[:800]
        save(store, agent, p)
        done.append(agent)
    return done


# --------------------------------------------------------------------------- prompt text
def _level(v: int, low: str, mid: str, high: str) -> str:
    return low if v < 34 else (mid if v < 67 else high)


def describe(p: Persona, agent: str, voice: bool = False, context: str = "task") -> str:
    """Text block appended to prompts. Empty when the personality is off. ``context``: task | chat."""
    if not p.enabled:
        return ""
    name = (p.name or "").strip()[:24] or DEFAULT_NAME.get(agent, "Kaguya")
    lines = [f"PERSONALIDADE (você é a {name}; isto muda só o JEITO de falar — as regras e permissões acima "
             "continuam valendo e têm prioridade; nunca invente resultados para manter a personagem):"]
    base = PRESETS.get(p.preset, {}).get("text", "")
    if base:
        lines.append("- " + base)
    if p.extra.strip():
        lines.append("- Do usuário: " + " ".join(p.extra.split())[:800])
    if p.nickname.strip():
        lines.append(f"- Chame o usuário de \"{p.nickname.strip()[:40]}\" de vez em quando.")
    lines.append({"voce": "- Trate o usuário por \"você\".", "tu": "- Trate o usuário por \"tu\".",
                  "formal": "- Trate o usuário com formalidade."}[p.address])
    if p.third_person:
        lines.append(f"- Às vezes fale de si mesma na terceira pessoa (\"a {name} acha que…\").")
    if p.greeting.strip():
        lines.append("- Saudação preferida: " + p.greeting.strip()[:120])
    lines.append("- " + "; ".join([
        _level(p.value("formality"), "linguagem informal", "formalidade moderada", "linguagem formal"),
        _level(p.value("humor"), "sem piadas", "humor leve de vez em quando", "bastante humor"),
        _level(p.value("initiative"), "faça só o que foi pedido", "sugira melhorias quando forem úteis",
               "tome iniciativa: proponha próximos passos e procure problemas relacionados"),
        _level(p.value("warmth"), "tom neutro", "tom gentil", "tom muito acolhedor"),
        _level(p.value("creativity"), "soluções convencionais", "criatividade equilibrada", "ideias criativas"),
        _level(p.value("objectivity"), "pode conversar mais", "equilíbrio entre conversa e objetividade",
               "muito objetiva"),
        _level(p.value("detail"), "respostas curtas", "respostas de tamanho normal", "respostas detalhadas"),
    ]) + ".")
    lines.append("- Por conta própria: " + PROACTIVE[p.proactive] + ".")
    if context == "task":
        lines.append("- Em execução técnica, segurança ou erro: precisão e concisão primeiro; a personagem aparece só "
                     "em frases curtas no começo ou no fim, nunca dentro de comandos, código, relatórios ou EVIDÊNCIAS.")
    if p.emoji and not voice:
        lines.append("- Pode usar alguns emojis no texto (nunca em código nem relatórios).")
    if voice:
        lines.append("- Isto é voz: nada de emojis, listas ou markdown.")
    return "\n".join(x for x in lines if x)


def for_agent(store, agent: str, voice: bool = False, pid: int | None = None, context: str | None = None) -> str:
    if agent not in ("codex", "claude"):
        return ""
    return describe(load(store, agent, pid), agent, voice, context or ("chat" if voice else "task"))
