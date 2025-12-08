"""Tests for webhook delivery logic."""

from unittest.mock import MagicMock, patch

import requests
from constance.test import override_config
from django.test import TestCase

from the_flip.apps.core.test_utils import create_machine, create_problem_report
from the_flip.apps.discord.tasks import deliver_webhook


class WebhookDeliveryTests(TestCase):
    """Tests for webhook delivery logic."""

    def setUp(self):
        self.machine = create_machine()

    @override_config(DISCORD_WEBHOOK_URL="")
    def test_skips_when_no_webhook_url(self):
        """Skips delivery when no webhook URL is configured."""
        report = create_problem_report(machine=self.machine)
        result = deliver_webhook("problem_report_created", report.pk, "ProblemReport")

        self.assertEqual(result["status"], "skipped")
        self.assertIn("no webhook URL", result["reason"])

    @override_config(
        DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/123/abc",
        DISCORD_WEBHOOKS_ENABLED=False,
    )
    def test_skips_when_webhooks_disabled(self):
        """Skips delivery when webhooks are globally disabled."""
        report = create_problem_report(machine=self.machine)
        result = deliver_webhook("problem_report_created", report.pk, "ProblemReport")

        self.assertEqual(result["status"], "skipped")
        self.assertIn("globally disabled", result["reason"])

    @override_config(
        DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/123/abc",
        DISCORD_WEBHOOKS_ENABLED=True,
        DISCORD_WEBHOOKS_PROBLEM_REPORTS=True,
    )
    @patch("the_flip.apps.discord.tasks.requests.post")
    def test_successful_delivery(self, mock_post):
        """Successfully delivers webhook."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        report = create_problem_report(machine=self.machine)
        result = deliver_webhook("problem_report_created", report.pk, "ProblemReport")

        self.assertEqual(result["status"], "success")
        mock_post.assert_called_once()

    @override_config(
        DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/123/abc",
        DISCORD_WEBHOOKS_ENABLED=True,
        DISCORD_WEBHOOKS_PROBLEM_REPORTS=True,
    )
    @patch("the_flip.apps.discord.tasks.requests.post")
    def test_handles_delivery_failure(self, mock_post):
        """Handles webhook delivery failure gracefully."""
        mock_post.side_effect = requests.RequestException("Connection error")

        report = create_problem_report(machine=self.machine)
        # Capture expected warning log to avoid noise in test output
        with self.assertLogs("the_flip.apps.discord.tasks", level="WARNING"):
            result = deliver_webhook("problem_report_created", report.pk, "ProblemReport")

        self.assertEqual(result["status"], "error")
        self.assertIn("Connection error", result["error"])
