"""Kaguya Browser protection on top of QtWebEngine (rules and explanations in kaguya/browser/privacy.py)."""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineUrlRequestInfo, QWebEngineUrlRequestInterceptor

from ..browser import privacy


class Guard(QWebEngineUrlRequestInterceptor):
    """Runs for every request (on WebEngine's IO thread): HTTPS upgrade, tracker block, do-not-track."""
    blocked = Signal(str, int)          # first-party site, total blocked there (delivered on the GUI thread)

    def __init__(self, settings: privacy.Settings, parent: QObject | None = None):
        super().__init__(parent)
        self.settings = settings
        self.allowed_http: set[str] = set()     # sites the user chose to open without encryption (this session)
        self.upgraded: set[str] = set()         # hosts moved to https (to explain if https fails)
        self.counts: dict[str, int] = {}
        self.extra_block: set[str] = set()      # your own blocked sites (and tests)
        self._lock = threading.Lock()

    def interceptRequest(self, info: QWebEngineUrlRequestInfo):   # noqa: N802 (Qt name)
        try:
            url = info.requestUrl().toString()
            h = privacy.host(url)
            main = info.resourceType() == QWebEngineUrlRequestInfo.ResourceType.ResourceTypeMainFrame
            if main and self.settings.https_only and h not in self.allowed_http:
                up = privacy.upgrade(url)
                if up:
                    with self._lock:
                        self.upgraded.add(h)
                    info.redirect(QUrl(up))
                    return
            fp = privacy.host(info.firstPartyUrl().toString())
            if (not main and self.settings.block_trackers and (privacy.is_tracker(h) or h in self.extra_block)
                    and privacy.third_party(fp, h)):
                info.block(True)
                site = privacy.site(fp)
                with self._lock:
                    self.counts[site] = self.counts.get(site, 0) + 1
                    n = self.counts[site]
                self.blocked.emit(site, n)
                return
            info.setHttpHeader(b"Sec-GPC", b"1")
            info.setHttpHeader(b"DNT", b"1")
        except Exception:
            pass      # a failure here must never break browsing

    def blocked_for(self, url: str) -> int:
        with self._lock:
            return self.counts.get(privacy.site(privacy.host(url)), 0)


def harden(profile, guard: Guard, settings: privacy.Settings) -> None:
    """Safe defaults for a WebEngine profile."""
    profile.setUrlRequestInterceptor(guard)
    store = profile.cookieStore()
    store.setCookieFilter(lambda req: not (settings.block_third_party_cookies and req.thirdParty))
    s = profile.settings()
    W = QWebEngineSettings.WebAttribute
    for attr, on in ((W.WebRTCPublicInterfacesOnly, True), (W.JavascriptCanAccessClipboard, False),
                     (W.LocalContentCanAccessRemoteUrls, False), (W.LocalContentCanAccessFileUrls, False),
                     (W.AllowRunningInsecureContent, False), (W.AllowGeolocationOnInsecureOrigins, False)):
        try:
            s.setAttribute(attr, on)
        except Exception:
            pass


def apply_dns(settings: privacy.Settings) -> str:
    """Encrypted DNS (DNS over HTTPS) for the whole browser; returns what is in effect."""
    try:
        from PySide6.QtWebEngineCore import QWebEngineGlobalSettings as G
    except ImportError:
        return "indisponível nesta versão"
    name, template = privacy.DNS_PROVIDERS.get(settings.dns, privacy.DNS_PROVIDERS["sistema"])
    mode = G.DnsMode()
    if template:
        mode.secureMode = G.SecureDnsMode.SecureOnly
        mode.serverTemplates = [template]
    else:
        mode.secureMode = G.SecureDnsMode.SystemOnly
    try:
        G.setDnsMode(mode)
    except Exception as exc:
        return f"não aplicado: {exc}"
    return name


PERMISSION_NAMES = {"MediaAudioCapture": "o microfone", "MediaVideoCapture": "a câmera",
                    "MediaAudioVideoCapture": "a câmera e o microfone", "Geolocation": "a sua localização",
                    "Notifications": "mostrar notificações", "DesktopVideoCapture": "gravar a sua tela",
                    "DesktopAudioVideoCapture": "gravar a sua tela e o som", "ClipboardReadWrite": "ler a área de transferência",
                    "LocalFontsAccess": "ver as fontes instaladas", "MouseLock": "prender o mouse"}


def permission_text(kind) -> str:
    name = getattr(kind, "name", str(kind)).split(".")[-1]
    return PERMISSION_NAMES.get(name, name)
