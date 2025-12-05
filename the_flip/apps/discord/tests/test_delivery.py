"""Tests for webhook delivery logic."""

from unittest.mock import MagicMock, patch

import requests
from django.test import TestCase

from the_flip.apps.core.test_utils import create_machine, create_problem_report
from the_flip.apps.discord.models import WebhookEndpoint, WebhookEventSubscription
from the_flip.apps.discord.tasks import deliver_webhooks


class WebhookDeliveryTests(TestCase):
    """Tests for webhook delivery logic."""

    def setUp(self):
        self.machine = create_machine()
        self.endpoint = WebhookEndpoint.objects.create(
            name="Test Endpoint",
            url="https://discord.com/api/webhooks/123/abc",
            is_enabled=True,
        )
        WebhookEventSubscription.objects.create(
            endpoint=self.endpoint,
            event_type=WebhookEndpoint.EVENT_PROBLEM_REPORT_CREATED,
            is_enabled=True,
        )

    def test_skips_when_no_subscriptions(self):
        """Skips delivery when no endpoints are subscribed."""
        WebhookEventSubscription.objects.all().delete()

        report = create_problem_report(machine=self.machine)
        result = deliver_webhooks("problem_report_created", report.pk, "ProblemReport")

        self.assertEqual(result["status"], "skipped")
        self.assertIn("no subscribed endpoints", result["reason"])

    def test_skips_disabled_endpoint(self):
        """Skips disabled endpoints."""
        self.endpoint.is_enabled = False
        self.endpoint.save()

        report = create_problem_report(machine=self.machine)
        result = deliver_webhooks("problem_report_created", report.pk, "ProblemReport")

        self.assertEqual(result["status"], "skipped")

    @patch("the_flip.apps.discord.tasks.requests.post")
    def test_successful_delivery(self, mock_post):
        """Successfully delivers webhook."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        report = create_problem_report(machine=self.machine)
        result = deliver_webhooks("problem_report_created", report.pk, "ProblemReport")

        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["status"], "success")
        mock_post.assert_called_once()

    @patch("the_flip.apps.discord.tasks.requests.post")
    def test_handles_delivery_failure(self, mock_post):
        """Handles webhook delivery failure gracefully."""
        mock_post.side_effect = requests.RequestException("Connection error")

        report = create_problem_report(machine=self.machine)
        # Capture expected warning log to avoid noise in test output
        with self.assertLogs("the_flip.apps.discord.tasks", level="WARNING"):
            result = deliver_webhooks("problem_report_created", report.pk, "ProblemReport")

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["results"][0]["status"], "error")
        self.assertIn("Connection error", result["results"][0]["error"])
