from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json

PROVIDERS = {"claude": "Claude Code (Miwa)", "codex": "Codex (Kaguya)", "web": "Só na web"}
KINDS = {"mcp": "MCP", "plugin": "Plugin", "skill": "Skill", "agent": "Agente", "command": "Comando",
         "hook": "Hook", "lsp": "LSP"}
# progressive states (each one needs its own evidence)
STATES = ["descoberto", "configurado", "habilitado", "carregado_na_sessao", "conectado", "capacidade_verificada"]
# complementary conditions
FLAGS = ["requer_login", "requer_aprovacao", "requer_reinicio", "incompativel", "falha", "indisponivel",
         "somente_web", "desatualizado", "removido", "desabilitado"]
LABELS = {"descoberto": "descoberto", "configurado": "configurado", "habilitado": "habilitado",
          "carregado_na_sessao": "carregado na sessão", "conectado": "conectado",
          "capacidade_verificada": "capacidade verificada", "requer_login": "requer login",
          "requer_aprovacao": "requer aprovação", "requer_reinicio": "requer reinício", "incompativel": "incompatível",
          "falha": "falha", "indisponivel": "indisponível", "somente_web": "só na web", "desatualizado": "desatualizado",
          "removido": "removido", "desabilitado": "desabilitado"}


@dataclass
class Extension:
    provider: str                  # claude | codex | web
    kind: str                      # mcp | plugin | skill | agent | command | hook | lsp
    name: str
    scope: str                     # user | project | local | plugin | builtin | web
    source: str = ""               # where it was found (file path or "claude plugin list")
    project: str = ""              # project folder for project/local scope
    version: str = ""
    description: str = ""
    parent: str = ""               # plugin id that brings this component
    transport: str = ""            # stdio | http | sse | ws
    command: str = ""              # redacted launch command / URL
    env_keys: list[str] = field(default_factory=list)   # names only, never values
    tools: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    state: str = "descoberto"
    flags: list[str] = field(default_factory=list)
    evidence: str = ""
    last_verified: str = ""
    details: dict = field(default_factory=dict)          # extra non-secret metadata (hook events, marketplace…)

    @property
    def id(self) -> str:
        """provider + kind + origin + scope + stable name (+ project): same name in two projects ≠ same extension."""
        proj = hashlib.sha1(self.project.lower().encode("utf-8")).hexdigest()[:8] if self.project else "-"
        parent = f"{self.parent}/" if self.parent else ""
        return f"{self.provider}:{self.kind}:{self.scope}:{proj}:{parent}{self.name}"

    def fingerprint(self) -> str:
        """Changes when what matters changes (version, command, description, tools, scope…), never with secrets."""
        keep = {k: v for k, v in asdict(self).items()
                if k not in ("state", "flags", "evidence", "last_verified", "tools", "details")}
        keep["details"] = {k: v for k, v in self.details.items() if not k.startswith("_")}
        return hashlib.sha256(json.dumps(keep, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:20]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Extension":
        d = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**d)

    def level(self) -> int:
        return STATES.index(self.state) if self.state in STATES else 0

    def usable(self) -> bool:
        """Can be counted on right now (needs real evidence, not just a config file)."""
        bad = {"removido", "falha", "indisponivel", "somente_web", "incompativel", "desabilitado", "requer_login",
               "requer_aprovacao"}
        return self.level() >= STATES.index("conectado") and not (set(self.flags) & bad)
