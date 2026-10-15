"""Tests for worker-to-web service configuration."""

from __future__ import annotations

import secrets

from django.test import SimpleTestCase, tag

from flipfix.apps.core.web_service import require_web_service_config

TOKEN = secrets.token_hex(16)


@tag("tasks")
class RequireWebServiceConfigTests(SimpleTestCase):
    """The worker token must only travel over HTTPS, except to this machine."""

    def test_accepts_https(self):
        """HTTPS URLs are accepted for any host."""
        url = "https://flipfix.example.org"

        self.assertEqual(require_web_service_config(url, TOKEN), (url, TOKEN))

    def test_accepts_plain_http_to_loopback(self):
        """Local development may use plain HTTP to this machine."""
        for url in ("http://localhost:8000", "http://127.0.0.1:8765", "http://[::1]:8000"):
            with self.subTest(url=url):
                self.assertEqual(require_web_service_config(url, TOKEN), (url, TOKEN))

    def test_rejects_plain_http_to_other_hosts(self):
        """Plain HTTP elsewhere would send the token in cleartext."""
        for url in ("http://flipfix.example.org", "http://10.0.0.5:8000", "ftp://localhost"):
            with self.subTest(url=url), self.assertRaises(ValueError) as ctx:
                require_web_service_config(url, TOKEN)
            self.assertIn("DJANGO_WEB_SERVICE_URL", str(ctx.exception))

    def test_names_every_missing_setting(self):
        """Missing settings are all named in one error."""
        with self.assertRaises(ValueError) as ctx:
            require_web_service_config(None, None)

        self.assertIn("DJANGO_WEB_SERVICE_URL", str(ctx.exception))
        self.assertIn("TRANSCODING_UPLOAD_TOKEN", str(ctx.exception))
