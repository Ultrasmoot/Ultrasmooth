# security header and configuration tests
from security_tests.base_headers import (
    DbTestCase,
)  # noqa: F401
import re
from security_tests.base import (
    mock,
)  # noqa: F401
import os
import unittest


class SecurityHeaderTests(DbTestCase):
    def test_page_and_scripts_have_no_inline_event_handlers(self):
        # CSP blocks inline handlers attach them from .js files instead
        html = self.client.get("/").get_data(as_text=True)
        self.assertEqual(re.findall(r"\son[a-z]+\s*=\s*[\"']", html), [], "inline event handler in index.html")
        scripts = re.findall(r'<script src="(/static/js/[^"]+)"', html)
        self.assertGreater(len(scripts), 10, "the page should link the per-page scripts")
        for url in scripts:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
            self.assertEqual(re.findall(r"<[a-z][^>]*\son[a-z]+\s*=\s*[\\\"']", r.get_data(as_text=True)), [], f"inline handler built in {url}")

    def test_page_has_security_headers_and_nonce_matches_inline_script(self):
        r = self.client.get("/")
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("Referrer-Policy", r.headers)
        csp = r.headers["Content-Security-Policy"]
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertIn("object-src 'none'", csp)
        self.assertNotIn("script-src 'self' 'unsafe-inline'", csp)
        nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
        self.assertIn(f'<script nonce="{nonce}">window.GOOGLE_CLIENT_ID', r.get_data(as_text=True))

    def test_nonce_changes_on_every_page_load(self):
        n = [re.search(r"'nonce-([^']+)'", self.client.get("/").headers["Content-Security-Policy"]).group(1) for _ in range(2)]
        self.assertNotEqual(n[0], n[1])

    def test_api_answers_are_not_cached_and_also_carry_headers(self):
        r = self.call("get", "/api/auth/me", self.student)
        self.assertEqual(r.headers["Cache-Control"], "no-store")
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")
        self.assertNotIn("nonce-", r.headers["Content-Security-Policy"])

    def test_every_page_script_is_same_origin_or_nonced(self):
        html = self.client.get("/").get_data(as_text=True)
        for tag in re.findall(r"<script\b[^>]*>", html):
            self.assertTrue("src=" in tag or "nonce=" in tag, tag)


class ConfigTests(unittest.TestCase):
    def test_production_refuses_missing_or_placeholder_secret(self):
        import config

        for value in (None, "", "change-me", "dev-secret-change-me"):
            env = {"SECRET_KEY": value} if value is not None else {}
            with mock.patch.dict(os.environ, env, clear=True):
                if value is None:
                    os.environ.pop("SECRET_KEY", None)
                with self.assertRaises(RuntimeError):
                    config._load_secret_key("production")

    def test_production_accepts_real_secret_and_dev_allows_placeholder(self):
        import config

        with mock.patch.dict(os.environ, {"SECRET_KEY": "x" * 48}):
            self.assertEqual(config._load_secret_key("production"), "x" * 48)
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(config._load_secret_key("development"), "dev-secret-change-me")