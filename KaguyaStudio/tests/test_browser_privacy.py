"""Kaguya Browser protection rules (pure logic)."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kaguya.browser import privacy  # noqa: E402


class Rules(unittest.TestCase):
    def test_https_upgrade_only_for_public_sites(self):
        self.assertEqual(privacy.upgrade("http://exemplo.com/a?b=1#c"), "https://exemplo.com/a?b=1#c")
        self.assertEqual(privacy.upgrade("http://exemplo.com:80/"), "https://exemplo.com/")
        for local in ("http://localhost:8080/", "http://127.0.0.1/", "http://192.168.0.10/", "http://nas.local/",
                      "https://exemplo.com/", "file:///C:/a.html", "kaguya:inicio"):
            self.assertIsNone(privacy.upgrade(local), local)

    def test_trackers_and_third_parties(self):
        self.assertTrue(privacy.is_tracker("www.google-analytics.com"))
        self.assertTrue(privacy.is_tracker("stats.g.doubleclick.net"))
        self.assertFalse(privacy.is_tracker("www.youtube.com"))
        self.assertFalse(privacy.is_tracker("analytics.com.br"))
        self.assertEqual(privacy.site("www.mercadolivre.com.br"), "mercadolivre.com.br")
        self.assertFalse(privacy.third_party("www.youtube.com", "i.youtube.com"))
        self.assertTrue(privacy.third_party("www.loja.com.br", "connect.facebook.net"))

    def test_security_levels_and_downloads(self):
        self.assertEqual(privacy.security_of("https://a.com")[0], "seguro")
        self.assertEqual(privacy.security_of("http://a.com")[0], "inseguro")
        self.assertEqual(privacy.security_of("https://a.com", cert_error=True)[0], "inseguro")
        self.assertEqual(privacy.security_of("http://192.168.1.5")[0], "local")
        self.assertEqual(privacy.security_of("about:blank")[0], "interno")
        self.assertTrue(privacy.risky_download("instalador.EXE"))
        self.assertTrue(privacy.risky_download("script.ps1"))
        self.assertFalse(privacy.risky_download("foto.png"))

    def test_settings_roundtrip_and_safe_defaults(self):
        class Store(dict):
            def get_setting(self, k, d=None):
                return self.get(k, d)

            def set_setting(self, k, v):
                self[k] = v
        st = Store()
        s = privacy.Settings.load(st)
        self.assertTrue(s.https_only and s.block_trackers and s.block_third_party_cookies)
        self.assertEqual(s.dns, "sistema")          # no new third party without your choice
        s.dns, s.proxy = "quad9", "socks5://127.0.0.1:1080"
        s.save(st)
        self.assertEqual(privacy.Settings.load(st).dns, "quad9")
        st["browser.privacy"] = {"dns": "inventado", "xyz": 1}
        self.assertEqual(privacy.Settings.load(st).dns, "sistema")


if __name__ == "__main__":
    unittest.main()
