"""Voice engines behind one contract, with capabilities checked at runtime (never assumed).

* ``kokoro``  — Kokoro-82M ONNX (Apache-2.0), local, pt-BR ``pf_dora`` mixes. Installed by the Studio on request.
* ``windows`` — the voices installed in Windows (SAPI), local.
* ``qwen3`` / ``chatterbox`` — heavier neural engines listed with their real status. They need PyTorch and
  several GB in an isolated environment, so they are **never installed automatically**: the user must authorise it.

Per-character voice profiles (engine, voice, style, speed, volume) are stored separately from the personality text.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import sys
import time

STYLES = {"natural": ("Natural", 1.0), "suave": ("Suave", 0.95), "animado": ("Animado", 1.07), "formal": ("Formal", 0.98)}


@dataclass
class Capabilities:
    id: str
    name: str
    installed: bool
    local: bool = True
    languages: tuple[str, ...] = ("pt-BR",)
    streaming: str = "por frase (o Studio fala cada frase assim que fica pronta)"
    cloning: bool = False
    emotion_control: bool = False
    speed_control: bool = True
    voices: list[tuple[str, str]] = field(default_factory=list)   # (id, label)
    license: str = ""
    size: str = ""
    notes: str = ""
    status: str = ""          # human-readable state shown in the panel

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VoiceProfile:
    engine: str = "auto"      # auto | kokoro | windows | qwen3 | chatterbox
    voice: str = ""           # engine-specific voice id ("" = character default)
    style: str = "natural"
    speed: float = 1.0        # multiplier on top of the style
    volume: int = 90          # 0..100, applied to this character's audio only

    def to_dict(self) -> dict:
        return asdict(self)


def load_profile(store, agent: str) -> VoiceProfile:
    raw = store.get_setting(f"voice.profile.{agent}", None) or {}
    p = VoiceProfile(**{k: v for k, v in raw.items() if k in VoiceProfile.__dataclass_fields__})
    if not p.voice:  # migrate the per-agent Kokoro preset chosen in 4.x
        legacy = store.get_setting(f"voice.neural_{agent}", None)
        if legacy:
            p.voice = legacy
    p.style = p.style if p.style in STYLES else "natural"
    p.speed = max(0.7, min(1.4, float(p.speed or 1.0)))
    p.volume = max(0, min(100, int(p.volume)))
    return p


def save_profile(store, agent: str, p: VoiceProfile) -> None:
    store.set_setting(f"voice.profile.{agent}", p.to_dict())
    if p.engine in ("auto", "kokoro") and p.voice:
        store.set_setting(f"voice.neural_{agent}", p.voice)   # keep the 4.x readers working


# --------------------------------------------------------------------------- engines
class KokoroEngine:
    id = "kokoro"

    def __init__(self, neural):
        self.neural = neural

    def probe(self) -> Capabilities:
        from .neural import PRESETS, package_available
        pkg = package_available()
        ready = self.neural.ready
        return Capabilities(
            id="kokoro", name="Kokoro-82M (ONNX)", installed=ready, license="Apache-2.0",
            size="≈ 120 MB (modelo int8 + vozes)", voices=[(k, p.label) for k, p in PRESETS.items()],
            status=("pronto" if ready else "biblioteca presente; vozes ainda não baixadas (Configurações › Voz)" if pkg
                    else "biblioteca de voz neural ausente nesta cópia"),
            notes="pt-BR: pf_dora (feminina), pm_alex/pm_santa (masculinas); misturas de estilo pelo Studio. "
                  "Sem clonagem nem controle de emoção.")

    def synth(self, text: str, profile: VoiceProfile, agent: str):
        from .neural import DEFAULT_PRESET
        voice = profile.voice or DEFAULT_PRESET.get(agent, "dora")
        style, speed = self.neural.style(voice)
        total = max(0.6, min(1.6, speed * STYLES[profile.style][1] * profile.speed))
        audio, sr = self.neural._load().create(text, voice=style, speed=total, lang="pt-br")
        return audio, sr


class WindowsEngine:
    id = "windows"

    def __init__(self, voice_name_getter=None):
        self._names = voice_name_getter

    def probe(self) -> Capabilities:
        from .tts import Speaker
        ok = sys.platform == "win32" and Speaker.backend() is not None
        voices = []
        if ok:
            try:
                voices = [(v, v) for v in Speaker.voices()]
            except Exception:
                voices = []
        return Capabilities(id="windows", name="Vozes do Windows (SAPI)", installed=ok, license="do Windows",
                            size="já instaladas", voices=voices, streaming="por frase",
                            status="pronto" if ok else "só no Windows",
                            notes="Qualidade depende das vozes instaladas (ex.: Microsoft Maria/Francisca).")

    def synth(self, text: str, profile: VoiceProfile, agent: str):
        from .speech import sapi_synth
        name = profile.voice or (self._names(agent) if self._names else "")
        return sapi_synth(lambda _a: name)(text, agent)


HEAVY = {
    "qwen3": Capabilities(
        id="qwen3", name="Qwen3-TTS 0.6B (Base / CustomVoice)", installed=False, license="Apache-2.0",
        size="PyTorch + modelo: vários GB", cloning=True, streaming="declarado pelo projeto (a medir)",
        status="não instalado — precisa da sua autorização (ambiente Python 3.12 isolado, PyTorch, download do modelo)",
        notes="Português listado oficialmente; sotaque BR a avaliar de ouvido. Clonagem só com referência sua e "
              "consentimento. Base e CustomVoice são modelos diferentes. Desempenho na sua GPU/CPU a medir."),
    "chatterbox": Capabilities(
        id="chatterbox", name="Chatterbox Multilingual V3 (pt-BR)", installed=False, license="MIT",
        size="PyTorch + checkpoint pt-BR: vários GB", cloning=True, emotion_control=True,
        status="não instalado — precisa da sua autorização; projeto arquivado (sem manutenção desde 08/2026)",
        notes="Checkpoint pt-BR tem carregador e arquivos próprios (verificar antes). Expressivo, mas sem manutenção."),
}


class VoiceEngines:
    """Registry + 'auto' choice. Only one engine synthesises at a time (the speech queue has one worker)."""

    def __init__(self, neural, windows_name_getter=None):
        self.engines = {"kokoro": KokoroEngine(neural), "windows": WindowsEngine(windows_name_getter)}

    def capabilities(self) -> list[Capabilities]:
        return [e.probe() for e in self.engines.values()] + list(HEAVY.values())

    def resolve(self, profile: VoiceProfile):
        if profile.engine in self.engines and self.engines[profile.engine].probe().installed:
            return self.engines[profile.engine]
        for eid in ("kokoro", "windows"):   # auto / fallback order: best local voice first
            e = self.engines.get(eid)
            if e is not None and e.probe().installed:
                return e
        return None

    def synth(self, text: str, profile: VoiceProfile, agent: str):
        """(audio float32, sr, engine id) with this character's volume applied."""
        import numpy as np
        engine = self.resolve(profile)
        if engine is None:
            raise RuntimeError("Nenhum motor de voz disponível.")
        audio, sr = engine.synth(text, profile, agent)
        audio = np.asarray(audio, dtype="float32") * (profile.volume / 100)
        return audio, sr, engine.id


# --------------------------------------------------------------------------- benchmark
def benchmark(engines: VoiceEngines, profile: VoiceProfile, agent: str, phrases: list[dict], runs: int = 1) -> dict:
    """Real measurements: synthesis time per phrase, audio duration, RTF, and time to the first sentence's audio
    (TTFA without the sound card's own latency, which cannot be measured from here)."""
    from .normalize import normalize
    from .speech import split_sentences
    rows, errors = [], []
    engine = engines.resolve(profile)
    if engine is None:
        return {"engine": None, "rows": [], "errors": ["nenhum motor disponível"]}
    for ph in phrases:
        text = normalize(ph["text"])
        for _ in range(runs):
            try:
                first, _rest = split_sentences(text, final=True, first_max=55)
                t0 = time.perf_counter()
                engine.synth(first[0] if first else text, profile, agent)
                ttfa = time.perf_counter() - t0
                t1 = time.perf_counter()
                audio, sr = engine.synth(text, profile, agent)
                gen = time.perf_counter() - t1
                dur = len(audio) / float(sr)
                rows.append({"id": ph.get("id", ""), "ttfa_s": round(ttfa, 3), "gen_s": round(gen, 3),
                             "audio_s": round(dur, 3), "rtf": round(gen / dur, 3) if dur else None})
            except Exception as exc:  # recorded, never hidden
                errors.append(f"{ph.get('id', '')}: {exc}")
    def pct(vals, q):
        vals = sorted(v for v in vals if v is not None)
        return round(vals[min(len(vals) - 1, int(q * (len(vals) - 1) + 0.5))], 3) if vals else None
    return {"engine": engine.id, "agent": agent, "profile": profile.to_dict(), "rows": rows, "errors": errors,
            "ttfa_p50": pct([r["ttfa_s"] for r in rows], 0.5), "ttfa_p95": pct([r["ttfa_s"] for r in rows], 0.95),
            "rtf_p50": pct([r["rtf"] for r in rows], 0.5), "when": time.strftime("%Y-%m-%d %H:%M")}
