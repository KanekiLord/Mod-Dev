"""YouTube Intelligence — the assistant only works with what is really accessible, and says which levels it had.

* A — metadata: title, channel, date, duration, description, chapters (from the page the user opened, or the
      official public oEmbed endpoint for title/channel only).
* B — text: the captions/transcript YouTube itself offers to the viewer (caption tracks listed by the player, or the
      "Mostrar transcrição" panel the user opened). Timestamps kept; the assistant summarises, never republishes.
* C — visual: only frames the user captures with the button (a still of what is on screen at that moment).
      No hidden player, no audio extraction, no download, nothing behind login/DRM.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import re
from urllib.parse import parse_qs, quote, urlparse

OEMBED = "https://www.youtube.com/oembed?format=json&url="


def video_id(url: str) -> str | None:
    try:
        u = urlparse(url or "")
    except ValueError:
        return None
    host = (u.hostname or "").lower()
    if host.endswith("youtu.be"):
        vid = u.path.strip("/").split("/")[0]
    elif host.endswith("youtube.com") or host.endswith("youtube-nocookie.com"):
        if u.path == "/watch":
            vid = (parse_qs(u.query).get("v") or [""])[0]
        else:
            m = re.match(r"^/(shorts|live|embed|v)/([^/?#]+)", u.path)
            vid = m.group(2) if m else ""
    else:
        return None
    return vid if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid or "") else None


def fmt_ts(seconds: float) -> str:
    s = int(max(0, seconds))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def parse_ts(text: str) -> int | None:
    parts = (text or "").strip().split(":")
    if not 2 <= len(parts) <= 3 or not all(p.isdigit() for p in parts):
        return None
    total = 0
    for p in parts:
        total = total * 60 + int(p)
    return total


def parse_chapters(description: str) -> list[tuple[int, str]]:
    """Chapters as YouTube defines them: description lines that start (or end) with a timestamp, first at 0:00."""
    out = []
    for line in (description or "").splitlines():
        m = re.match(r"^\s*[\[(]?((?:\d{1,2}:)?\d{1,2}:\d{2})[\])]?\s*[-–—:|]?\s*(.+?)\s*$", line) or \
            re.match(r"^\s*(.+?)\s*[-–—|]?\s*[\[(]?((?:\d{1,2}:)?\d{1,2}:\d{2})[\])]?\s*$", line)
        if not m:
            continue
        a, b = m.group(1), m.group(2)
        ts, title = (parse_ts(a), b) if parse_ts(a) is not None else (parse_ts(b), a)
        if ts is not None and title:
            out.append((ts, title.strip(" -–—|")))
    if not out or out[0][0] != 0:
        return [] if len(out) < 2 else out   # not real chapters, but timestamps the author listed
    return out


def parse_json3(body: str) -> list[tuple[float, str]]:
    data = json.loads(body)
    segs = []
    for ev in data.get("events", []):
        text = "".join(s.get("utf8", "") for s in ev.get("segs", []) or []).replace("\n", " ").strip()
        if text:
            segs.append((ev.get("tStartMs", 0) / 1000.0, text))
    return segs


def parse_timedtext_xml(body: str) -> list[tuple[float, str]]:
    import html
    segs = []
    for m in re.finditer(r'<text start="([\d.]+)"[^>]*>(.*?)</text>', body or "", re.S):
        text = html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).replace("\n", " ").strip()
        if text:
            segs.append((float(m.group(1)), text))
    return segs


def parse_captions(body: str) -> list[tuple[float, str]]:
    b = (body or "").lstrip()
    if not b:
        return []
    if b.startswith("{"):
        return parse_json3(b)
    return parse_timedtext_xml(b)


def window(segments: list[tuple[float, str]], center: float, span: float = 60) -> list[tuple[float, str]]:
    return [(t, x) for t, x in segments if center - span / 2 <= t <= center + span / 2]


def transcript_text(segments: list[tuple[float, str]], limit: int = 30000) -> str:
    lines, size = [], 0
    for t, x in segments:
        line = f"[{fmt_ts(t)}] {x}"
        size += len(line) + 1
        if size > limit:
            lines.append(f"… (transcrição cortada; {len(segments)} trechos no total)")
            break
        lines.append(line)
    return "\n".join(lines)


def oembed(url: str, timeout: float = 10) -> dict:
    """Official public endpoint (no key, no login): title + channel only."""
    import urllib.request
    req = urllib.request.Request(OEMBED + quote(url, safe=""), headers={"User-Agent": "KaguyaStudio"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    return {"title": data.get("title", ""), "author": data.get("author_name", ""),
            "channel_url": data.get("author_url", "")}


# runs in the YouTube page the user opened; reads what the player itself exposes to the viewer
PAGE_JS = r"""
(function () {
  var want = new URLSearchParams(location.search).get("v") || (location.pathname.split("/")[2] || "");
  var pr = null, src = "";
  try { var mp = document.getElementById("movie_player");
        if (mp && mp.getPlayerResponse) { pr = mp.getPlayerResponse(); src = "player"; } } catch (e) {}
  if ((!pr || !pr.videoDetails || pr.videoDetails.videoId !== want) && window.ytInitialPlayerResponse &&
      ytInitialPlayerResponse.videoDetails && ytInitialPlayerResponse.videoDetails.videoId === want) {
    pr = ytInitialPlayerResponse; src = "initial"; }
  var d = (pr && pr.videoDetails) || {}, mf = (pr && pr.microformat && pr.microformat.playerMicroformatRenderer) || {};
  var tracks = [];
  try { (pr.captions.playerCaptionsTracklistRenderer.captionTracks || []).forEach(function (t) {
      tracks.push({lang: t.languageCode, name: (t.name && (t.name.simpleText || (t.name.runs || []).map(function (r) {
        return r.text; }).join(""))) || t.languageCode, kind: t.kind || "", url: t.baseUrl}); }); } catch (e) {}
  var segs = Array.from(document.querySelectorAll("ytd-transcript-segment-renderer")).map(function (s) {
    var ts = s.querySelector(".segment-timestamp"), tx = s.querySelector(".segment-text");
    return [ts ? ts.innerText.trim() : "", tx ? tx.innerText.trim() : ""]; });
  var v = document.querySelector("video");
  var r = v ? v.getBoundingClientRect() : null;
  return JSON.stringify({
    ok: !!(d && d.videoId === want), source: src, video_id: want, title: d.title || document.title,
    author: d.author || "", channel_id: d.channelId || "", length: parseInt(d.lengthSeconds || "0", 10),
    description: d.shortDescription || "", keywords: d.keywords || [], live: !!d.isLiveContent,
    publish_date: mf.publishDate || mf.uploadDate || "", category: mf.category || "",
    private: !!d.isPrivate, playable: !!(pr && pr.playabilityStatus && pr.playabilityStatus.status === "OK"),
    tracks: tracks, transcript_dom: segs, time: v ? v.currentTime : null, paused: v ? v.paused : null,
    video_rect: r ? [r.left, r.top, r.width, r.height] : null, dpr: window.devicePixelRatio || 1
  });
})()
"""


def caption_fetch_js(track_url: str) -> str:
    """Asks the page to fetch a caption track exactly as the player does when the viewer turns captions on.
    The result is left in a page variable that the Studio polls."""
    url = json.dumps(track_url + ("&" if "?" in track_url else "?") + "fmt=json3")
    return ("(function(){window.__kaguyaCaptions={state:'loading'};fetch(" + url + ",{credentials:'include'})"
            ".then(function(r){return r.text().then(function(t){window.__kaguyaCaptions={state:'done',status:r.status,"
            "body:t};});}).catch(function(e){window.__kaguyaCaptions={state:'error',error:String(e)};});"
            "return 'started';})()")


CAPTION_POLL_JS = "JSON.stringify(window.__kaguyaCaptions || {state: 'none'})"


def pick_track(tracks: list[dict], prefer: tuple[str, ...] = ("pt", "pt-BR", "en")) -> dict | None:
    if not tracks:
        return None
    manual = [t for t in tracks if t.get("kind") != "asr"]
    for pool in (manual, tracks):
        for lang in prefer:
            for t in pool:
                if (t.get("lang") or "").lower().startswith(lang.lower()):
                    return t
    return manual[0] if manual else tracks[0]


@dataclass
class Report:
    url: str
    video_id: str
    collected_at: str = field(default_factory=lambda: datetime.now().strftime("%d/%m/%Y %H:%M"))
    meta: dict = field(default_factory=dict)            # level A
    meta_source: str = ""                               # "página" | "oEmbed" | ""
    segments: list[tuple[float, str]] = field(default_factory=list)   # level B
    text_source: str = ""
    text_problem: str = ""
    frames: list[tuple[float, str]] = field(default_factory=list)     # level C: (time, png path)
    time: float | None = None
    tracks: list[dict] = field(default_factory=list)   # caption tracks the player lists for this video

    @classmethod
    def from_page(cls, url: str, page: dict) -> "Report":
        rep = cls(url=url, video_id=page.get("video_id") or video_id(url) or "")
        if page.get("ok"):
            rep.meta = {k: page.get(k) for k in ("title", "author", "length", "publish_date", "description",
                                                 "keywords", "category", "live")}
            rep.meta["chapters"] = parse_chapters(page.get("description", ""))
            rep.meta_source = "página do vídeo"
        rep.time = page.get("time")
        dom = [(parse_ts(ts), tx) for ts, tx in page.get("transcript_dom") or [] if parse_ts(ts) is not None and tx]
        if dom:
            rep.segments, rep.text_source = [(float(t), x) for t, x in dom], "painel “Mostrar transcrição” aberto"
        return rep

    def set_captions(self, body: str, track: dict) -> None:
        segs = parse_captions(body)
        if segs:
            self.segments = segs
            kind = "automáticas" if track.get("kind") == "asr" else "do autor"
            self.text_source = f"legendas {kind} do YouTube ({track.get('name') or track.get('lang')})"
            self.text_problem = ""
        else:
            self.text_problem = ("o YouTube não entregou o texto das legendas para este vídeo; abra “Mostrar "
                                 "transcrição” na página e tente de novo")

    def levels(self) -> dict[str, str]:
        a = (f"disponível ({self.meta_source})" if self.meta else "indisponível — a página do vídeo não carregou")
        if self.segments:
            b = f"disponível — {len(self.segments)} trechos com tempo ({self.text_source})"
        elif self.text_problem:
            b = "indisponível — " + self.text_problem
        elif self.tracks:
            b = (f"ainda não lido — o vídeo tem {len(self.tracks)} legenda(s); clique em “Ler legendas” "
                 "(até lá a IA não tem o texto)")
        else:
            b = "indisponível — o vídeo não tem legendas/transcrição acessíveis"
        c = (f"{len(self.frames)} quadro(s) capturado(s) por você em " + ", ".join(fmt_ts(t) for t, _ in self.frames)
             if self.frames else "nenhum quadro — a IA não vê o vídeo (use “Capturar quadro” se quiser)")
        return {"A — metadados": a, "B — texto": b, "C — visual": c}

    def context(self, mode: str = "video", around: float | None = None, span: float = 90) -> str:
        """Data block for the assistant. ``mode``: video (whole) | trecho (around a time)."""
        m = self.meta
        out = ["FONTE: vídeo do YouTube aberto pelo usuário no Kaguya Browser",
               f"URL: {self.url}", f"Coletado em: {self.collected_at}",
               "O QUE VOCÊ TEM DESTE VÍDEO (você NÃO assistiu nem ouviu o vídeo):"]
        out += [f"- {k}: {v}" for k, v in self.levels().items()]
        if m:
            out.append(f"Título: {m.get('title', '')}")
            out.append(f"Canal: {m.get('author', '')}")
            if m.get("publish_date"):
                out.append(f"Publicado em: {m['publish_date']}")
            if m.get("length"):
                out.append(f"Duração: {fmt_ts(m['length'])}")
            if m.get("chapters"):
                out.append("Capítulos: " + "; ".join(f"{fmt_ts(t)} {x}" for t, x in m["chapters"]))
            if m.get("description"):
                out.append("Descrição (do autor):\n" + m["description"][:5000])
        if self.segments:
            segs = self.segments
            if mode == "trecho" and around is not None:
                segs = window(self.segments, around, span)
                out.append(f"TRECHO PEDIDO: de {fmt_ts(max(0, around - span / 2))} a {fmt_ts(around + span / 2)}")
            out.append("TRANSCRIÇÃO COM TEMPOS:\n" + transcript_text(segs))
        for t, path in self.frames:
            out.append(f"Quadro capturado pelo usuário em {fmt_ts(t)}: {path}")
        return "\n".join(out)


REPORT_INSTRUCTIONS = (
    "Responda em português no formato de relatório: Fonte (canal, URL, data de coleta); Níveis usados (A/B/C e o que "
    "faltou); Resumo próprio (não reproduza a transcrição — cite só frases curtas com o tempo [m:ss]); Técnicas; "
    "Dependências e versões mencionadas; O que dá para confirmar e o que fica em dúvida. Nunca diga que viu ou ouviu o "
    "vídeo: você só tem os níveis listados.")


def prompt_for(action: str, rep: Report, project: str = "") -> tuple[str, str]:
    """(question shown in the chat, attached context) for the YouTube panel buttons."""
    title = rep.meta.get("title") or rep.url
    if action == "estudar" and rep.time is not None:
        q = f"Estude o trecho em {fmt_ts(rep.time)} do vídeo “{title}”: explique o que é ensinado ali, passo a passo."
        return q + "\n\n" + REPORT_INSTRUCTIONS, rep.context("trecho", rep.time)
    if action == "comparar":
        q = (f"Compare o que o vídeo “{title}” ensina com o meu projeto{(' ' + project) if project else ''}: o que é "
             "compatível (versões, APIs, dependências), o que precisaria mudar e quais testes provariam. Confira na "
             "documentação oficial quando possível. Não altere arquivos.")
        return q + "\n\n" + REPORT_INSTRUCTIONS, rep.context()
    q = f"Analise o vídeo “{title}”."
    return q + "\n\n" + REPORT_INSTRUCTIONS, rep.context()


def note_markdown(rep: Report, summary: str = "") -> str:
    """Draft for the Obsidian review queue (the user approves before it enters the vault)."""
    m = rep.meta
    lines = ["---", "tipo: estudo-video", f"fonte: {rep.url}", f"canal: {m.get('author', '')}",
             f"coletado: {rep.collected_at}", "niveis: [" + ", ".join(k.split(" ")[0] for k, v in rep.levels().items()
                                                                 if not v.startswith(("indisponível", "nenhum"))) + "]",
             "---", f"# {m.get('title') or rep.url}", ""]
    for k, v in rep.levels().items():
        lines.append(f"- **{k}**: {v}")
    if m.get("chapters"):
        lines += ["", "## Capítulos"] + [f"- [{fmt_ts(t)}]({rep.url}&t={int(t)}s) {x}" for t, x in m["chapters"]]
    if summary:
        lines += ["", "## Resumo", summary.strip()]
    lines += ["", "## Minhas notas", ""]
    return "\n".join(lines)
