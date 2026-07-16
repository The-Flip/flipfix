"""Tests for the daily maintenance report Discord webhook task."""

from __future__ import annotations

from unittest.mock import patch

from constance.test import override_config
from django.test import TestCase, tag
from django.utils.text import slugify

from flipfix.apps.catalog.models import Location, MachineInstance
from flipfix.apps.core.test_utils import create_machine, create_machine_model
from flipfix.apps.discord.tasks import _fit_discord_content, post_daily_maintenance_report

S = MachineInstance.OperationalStatus
Z = Location.Zone
WEBHOOK = "https://discord.example/webhook"  # pragma: allowlist secret


def _loc(name, zone):
    loc, _ = Location.objects.get_or_create(slug=slugify(name), defaults={"name": name})
    loc.zone = zone
    loc.save()
    return loc


@tag("tasks")
class PostDailyReportTests(TestCase):
    @override_config(DISCORD_WEBHOOK_URL="", DISCORD_WEBHOOKS_ENABLED=True)
    @patch("flipfix.apps.discord.tasks.requests.post")
    def test_skips_when_no_webhook_url(self, mock_post):
        result = post_daily_maintenance_report()
        self.assertEqual(result.status, "skipped")
        mock_post.assert_not_called()

    @override_config(DISCORD_WEBHOOK_URL=WEBHOOK, DISCORD_WEBHOOKS_ENABLED=False)
    @patch("flipfix.apps.discord.tasks.requests.post")
    def test_skips_when_webhooks_disabled(self, mock_post):
        result = post_daily_maintenance_report()
        self.assertEqual(result.status, "skipped")
        mock_post.assert_not_called()

    @override_config(DISCORD_WEBHOOK_URL=WEBHOOK, DISCORD_WEBHOOKS_ENABLED=True)
    @patch("flipfix.apps.discord.tasks.requests.post")
    def test_posts_markdown_content_with_link(self, mock_post):
        mock_post.return_value.status_code = 204
        mock_post.return_value.raise_for_status.return_value = None
        _loc("Coin-Op", Z.FRONT)

        result = post_daily_maintenance_report()

        self.assertEqual(result.status, "success")
        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        self.assertIn("content", payload)
        self.assertIn("Front of House", payload["content"])
        self.assertIn("/logs/daily-report/", payload["content"])

    @override_config(DISCORD_WEBHOOK_URL=WEBHOOK, DISCORD_WEBHOOKS_ENABLED=True)
    @patch("flipfix.apps.discord.tasks.requests.post")
    def test_content_stays_within_discord_limit(self, mock_post):
        mock_post.return_value.status_code = 204
        mock_post.return_value.raise_for_status.return_value = None
        front = _loc("Coin-Op", Z.FRONT)
        for i in range(120):
            create_machine(
                location=front,
                operational_status=S.BROKEN,
                model=create_machine_model(year=1970 + i % 50),
            )
        post_daily_maintenance_report()
        self.assertLessEqual(len(mock_post.call_args.kwargs["json"]["content"]), 2000)


@tag("tasks")
class FitDiscordContentTests(TestCase):
    def test_short_body_keeps_link(self):
        out = _fit_discord_content("hello", "link")
        self.assertEqual(out, "hello\n\nlink")

    def test_long_body_truncated_but_link_survives(self):
        out = _fit_discord_content("x" * 5000, "🔗 board")
        self.assertLessEqual(len(out), 2000)
        self.assertTrue(out.endswith("🔗 board"))
        self.assertIn("…", out)
