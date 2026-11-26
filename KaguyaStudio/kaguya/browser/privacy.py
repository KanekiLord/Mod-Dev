"""Kaguya Browser protection — what each switch really does (no marketing):

* HTTPS sempre: pages are opened with encryption (http:// becomes https://). If the site has no HTTPS
  the Studio warns and only continues with your OK for that site.
* Bloqueio de rastreadores: requests to well-known tracking/analytics/ad-tracking domains (built-in
  list below) are refused. It is not a full ad blocker.
* Cookies de terceiros bloqueados: sites cannot follow you across other sites with cookies.
* DNS criptografado (DNS over HTTPS): the names of the sites you open no longer travel in clear text
  on your Wi-Fi/provider. It sends those lookups to the provider you pick instead (Quad9 or Cloudflare).
* WebRTC só pela interface pública: video-call APIs cannot reveal your local network addresses.
* Pedido para não rastrear (GPC/DNT) sent with every request.
* Camera, microphone, location, notifications and screen sharing always ask first.
* Invalid certificates block the page (never "continue anyway" in silence).

What a VPN is and why the Studio does not ship one: a VPN sends all your traffic through someone
else's server, hiding your IP from sites and your traffic from your provider — but that server sees
everything. A "free VPN" inside an app is exactly the kind of third party that can spy on you. The
browser follows the VPN you install in Windows (e.g. one you trust), and can use a proxy only for the
browser (Configurações › Navegador). Nothing is installed or enabled without your OK.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import ipaddress
from urllib.parse import urlsplit, urlunsplit

# well-known third-party trackers (analytics, ad-tracking, session recording, fingerprinting); parents match
# their subdomains. Short on purpose: blocking ad/CDN domains blindly breaks sites.
TRACKERS = frozenset("""
doubleclick.net googlesyndication.com googleadservices.com google-analytics.com googletagmanager.com
googletagservices.com adservice.google.com analytics.google.com app-measurement.com
connect.facebook.net pixel.facebook.com an.facebook.com analytics.tiktok.com ads.tiktok.com
analytics.twitter.com ads-twitter.com static.ads-twitter.com ads.linkedin.com px.ads.linkedin.com snap.licdn.com
bat.bing.com clarity.ms scorecardresearch.com quantserve.com quantcount.com hotjar.com hotjar.io
mouseflow.com fullstory.com crazyegg.com luckyorange.com inspectlet.com smartlook.com
segment.io segment.com mixpanel.com amplitude.com heapanalytics.com kissmetrics.com
criteo.com criteo.net taboola.com outbrain.com adnxs.com adsrvr.org rubiconproject.com pubmatic.com
openx.net casalemedia.com 33across.com moatads.com adform.net amazon-adsystem.com
mc.yandex.ru top-fwz1.mail.ru newrelic.com nr-data.net
branch.io adjust.com appsflyer.com kochava.com onesignal.com
""".split())
EXECUTABLES = (".exe", ".msi", ".bat", ".cmd", ".ps1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".scr", ".pif",
               ".com", ".jar", ".hta", ".lnk", ".reg", ".dll", ".cpl", ".msc", ".appx", ".msix")
DNS_PROVIDERS = {
    "sistema": ("DNS do sistema/provedor (sem criptografia garantida)", ""),
    "quad9": ("Quad9 — fundação sem fins lucrativos, bloqueia domínios maliciosos", "https://dns.quad9.net/dns-query"),
    "cloudflare": ("Cloudflare 1.1.1.1 — rápido", "https://cloudflare-dns.com/dns-query"),
}
# two-label public suffixes common for Brazilian/English sites (enough to tell first- from third-party)
_SUFFIX2 = {"com.br", "net.br", "org.br", "gov.br", "edu.br", "art.br", "co.uk", "org.uk", "gov.uk", "ac.uk",
            "com.au", "co.jp", "co.kr", "com.ar", "com.mx", "com.pt", "co.in", "github.io", "blogspot.com"}


@dataclass
class Settings:
    https_only: bool = True
    block_trackers: bool = True
    block_third_party_cookies: bool = True
    dns: str = "sistema"
    proxy: str = ""            # e.g. socks5://127.0.0.1:9050 — applied when the Studio starts

    @classmethod
    def load(cls, store) -> "Settings":
        raw = store.get_setting("browser.privacy", {}) if store is not None else {}
        s = cls(**{k: v for k, v in (raw or {}).items() if k in cls.__dataclass_fields__})
        if s.dns not in DNS_PROVIDERS:
            s.dns = "sistema"
        return s

    def save(self, store) -> None:
        store.set_setting("browser.privacy", asdict(self))


def host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def is_local(h: str) -> bool:
    h = (h or "").strip("[]").lower()
    if h in ("localhost", "") or h.endswith(".localhost") or h.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(h)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return False


def site(h: str) -> str:
    """Registrable domain ("www.youtube.com" → "youtube.com", "a.b.com.br" → "b.com.br")."""
    parts = [p for p in (h or "").lower().split(".") if p]
    if len(parts) <= 2:
        return ".".join(parts)
    if ".".join(parts[-2:]) in _SUFFIX2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def third_party(first_party_host: str, request_host: str) -> bool:
    return bool(first_party_host and request_host) and site(first_party_host) != site(request_host)


def is_tracker(h: str) -> bool:
    labels = (h or "").lower().rstrip(".").split(".")
    return any(".".join(labels[i:]) in TRACKERS for i in range(len(labels) - 1))


def upgrade(url: str) -> str | None:
    """https:// version of an http:// address (None when it should stay as is: local addresses, other schemes)."""
    try:
        p = urlsplit(url)
    except ValueError:
        return None
    if p.scheme != "http" or is_local(p.hostname or ""):
        return None
    netloc = p.netloc[:-3] if p.netloc.endswith(":80") else p.netloc
    return urlunsplit(("https", netloc, p.path, p.query, p.fragment))


def risky_download(name: str) -> bool:
    return (name or "").lower().endswith(EXECUTABLES)


def security_of(url: str, cert_error: bool = False) -> tuple[str, str]:
    """(level, text) for the address bar: seguro | inseguro | local | interno."""
    try:
        p = urlsplit(url)
    except ValueError:
        return "inseguro", "Endereço inválido"
    if p.scheme in ("kaguya", "about", "data", "qrc", "chrome", ""):
        return "interno", "Página do Kaguya Studio"
    if p.scheme == "file":
        return "local", "Arquivo do seu computador"
    if cert_error:
        return "inseguro", "Certificado inválido: a conexão pode estar sendo interceptada"
    if p.scheme == "https":
        return "seguro", "Conexão criptografada (HTTPS)"
    if is_local(p.hostname or ""):
        return "local", "Endereço da sua rede local"
    return "inseguro", "Conexão sem criptografia (HTTP): quem está na rede pode ver e alterar a página"
