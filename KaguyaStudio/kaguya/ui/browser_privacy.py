"""Privacidade e segurança do Kaguya Browser: the state of this page and the switches, explained plainly."""
from __future__ import annotations

from PySide6.QtWidgets import (QButtonGroup, QDialog, QHBoxLayout, QLineEdit, QRadioButton, QScrollArea,
                               QVBoxLayout, QWidget)

from ..browser import privacy
from ..browser.share import NAMES
from .theme import C
from .widgets import Card, Toggle, button, label

VPN_TEXT = (
    "<b>E VPN?</b> Uma VPN faz todo o seu tráfego passar pelo servidor de outra empresa: esconde seu IP dos sites e "
    "o que você acessa do seu provedor — mas <b>esse servidor passa a ver tudo</b>. Por isso o Studio não traz uma "
    "\"VPN grátis\" embutida: seria justamente um terceiro desconhecido no meio dos seus dados. Se você usa uma VPN "
    "confiável no Windows, o Kaguya Browser já passa por ela automaticamente. Para mandar <i>só o navegador</i> por "
    "uma VPN/proxy que você roda no PC, use o campo Proxy abaixo.")


class PrivacyDialog(QDialog):
    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.setWindowTitle("Privacidade e segurança — Kaguya Browser")
        self.resize(640, 680)
        outer = QVBoxLayout(self)
        area = QScrollArea()
        area.setWidgetResizable(True)
        from PySide6.QtCore import Qt
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setSpacing(10)
        area.setWidget(body)
        outer.addWidget(area, 1)
        st = page.privacy
        # ---- this page
        here = Card()
        here.lay.addWidget(label("ESTA PÁGINA", "section"))
        v = page._cur()
        url = v.url().toString() if v is not None else ""
        level, text = privacy.security_of(url, v is not None and v.tab_id in page.cert_errors)
        color = {"seguro": C["success"], "inseguro": C["danger"], "local": C["info"], "interno": C["muted"]}[level]
        self.page_state = label(f"<span style='color:{color}'>●</span> {text}", None, wrap=True)
        here.lay.addWidget(self.page_state)
        n = page.guard.blocked_for(url) if page.guard is not None else 0
        tab = page.shares.tab(v.tab_id) if v is not None else None
        ai = ("compartilhada com " + " e ".join(NAMES.get(a, a) for a in sorted(tab.readers))) if tab is not None and tab.readers else \
            "nenhuma IA vê esta aba"
        here.lay.addWidget(label(f"Rastreadores bloqueados neste site: {n} • IA: {ai}" +
                                 (" • aba anônima (nada fica gravado)" if v is not None and v.private else ""),
                                 "dim", wrap=True))
        lay.addWidget(here)
        # ---- switches
        prot = Card()
        prot.lay.addWidget(label("PROTEÇÃO (vale para todas as abas)", "section"))
        self.t_https = Toggle("HTTPS sempre (criptografia; avisa se o site não tiver)", st.https_only)
        self.t_trackers = Toggle("Bloquear rastreadores conhecidos", st.block_trackers)
        self.t_cookies = Toggle("Bloquear cookies de terceiros", st.block_third_party_cookies)
        for t, why in ((self.t_https, None),
                       (self.t_trackers, "Google Analytics, pixels de anúncio do Facebook/TikTok, gravação de sessão "
                                         "(Hotjar, Clarity)… Não é um bloqueador de anúncios completo."),
                       (self.t_cookies, "Impede que um site siga você pelos outros sites com cookies.")):
            prot.lay.addWidget(t)
            if why:
                prot.lay.addWidget(label(why, "dim", wrap=True))
        prot.lay.addWidget(label("Sempre ligados: WebRTC sem expor seus IPs locais, pedido de não rastrear (GPC), "
                                 "certificado inválido bloqueia a página, câmera/microfone/localização/notificações "
                                 "sempre pedem permissão, aviso antes de baixar programas.", "dim", wrap=True))
        lay.addWidget(prot)
        # ---- DNS
        dns = Card()
        dns.lay.addWidget(label("DNS CRIPTOGRAFADO", "section"))
        dns.lay.addWidget(label("Quando você abre um site, o nome dele é consultado num servidor DNS. Sem "
                                "criptografia, quem controla a rede (Wi-Fi, provedor) vê a lista de sites. Com DNS "
                                "criptografado (DNS over HTTPS), só o serviço escolhido vê essas consultas.",
                                "dim", wrap=True))
        self.dns_group = QButtonGroup(self)
        for i, (key, (name, _t)) in enumerate(privacy.DNS_PROVIDERS.items()):
            r = QRadioButton(name)
            r.setProperty("key", key)
            r.setChecked(key == st.dns)
            self.dns_group.addButton(r, i)
            dns.lay.addWidget(r)
        dns.lay.addWidget(label(f"Em uso agora: {getattr(page, 'dns_status', 'DNS do sistema')}", "dim"))
        lay.addWidget(dns)
        # ---- VPN / proxy
        vpn = Card()
        vpn.lay.addWidget(label("VPN E PROXY", "section"))
        vtext = label(VPN_TEXT, None, wrap=True)
        vpn.lay.addWidget(vtext)
        row = QHBoxLayout()
        self.proxy = QLineEdit(st.proxy)
        self.proxy.setPlaceholderText("Proxy só do navegador (opcional), ex.: socks5://127.0.0.1:1080")
        row.addWidget(label("Proxy:", "dim"))
        row.addWidget(self.proxy, 1)
        vpn.lay.addLayout(row)
        vpn.lay.addWidget(label("O proxy vale depois de reiniciar o Studio. Deixe vazio para usar a conexão normal "
                                "(ou a VPN do Windows).", "dim", wrap=True))
        lay.addWidget(vpn)
        # ---- data
        data = Card()
        data.lay.addWidget(label("SEUS DADOS", "section"))
        data.lay.addWidget(label("Abas pessoais guardam login e histórico só neste PC (pasta do Studio). Abas "
                                 "anônimas e abas de pesquisa das IAs não gravam nada e nunca veem seus logins. "
                                 "Nenhuma IA vê uma aba até você compartilhar.", "dim", wrap=True))
        clear = button("Apagar dados de navegação…", "trash", "ghost")
        clear.clicked.connect(page.clear_data)
        data.lay.addWidget(clear)
        lay.addWidget(data)
        lay.addStretch(1)
        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = button("Fechar", "x", "ghost")
        cancel.clicked.connect(self.reject)
        save = button("Salvar", "check", "primary")
        save.clicked.connect(self.save)
        btns.addWidget(cancel)
        btns.addWidget(save)
        outer.addLayout(btns)

    def save(self):
        st = self.page.privacy
        st.https_only = self.t_https.isChecked()
        st.block_trackers = self.t_trackers.isChecked()
        st.block_third_party_cookies = self.t_cookies.isChecked()
        checked = self.dns_group.checkedButton()
        st.dns = checked.property("key") if checked is not None else "sistema"
        proxy = self.proxy.text().strip()
        if proxy and not proxy.startswith(("socks5://", "socks4://", "http://", "https://")):
            self.proxy.setStyleSheet(f"border: 1px solid {C['danger']};")
            self.proxy.setToolTip("Use socks5://host:porta ou http://host:porta")
            return
        restart = proxy != st.proxy
        st.proxy = proxy
        self.page.apply_privacy()
        self.page.win.toast("Proteção do navegador salva." + (" O proxy vale depois de reiniciar o Studio."
                                                              if restart else ""))
        self.accept()
