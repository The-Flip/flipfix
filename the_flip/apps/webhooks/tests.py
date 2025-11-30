"""Tests for webhook functionality."""

from unittest.mock import MagicMock, patch

import requests
from django.test import TestCase

from the_flip.apps.core.test_utils import (
    create_log_entry,
    create_machine,
    create_problem_report,
    create_staff_user,
)
from the_flip.apps.webhooks.formatters import (
    format_discord_message,
    format_test_message,
)
from the_flip.apps.webhooks.models import (
    WebhookEndpoint,
    WebhookEventSubscription,
    WebhookSettings,
)
from the_flip.apps.webhooks.tasks import deliver_webhooks


class WebhookEndpointModelTests(TestCase):
    """Tests for the WebhookEndpoint model."""

    def test_create_endpoint(self):
        """Can create a webhook endpoint."""
        endpoint = WebhookEndpoint.objects.create(
            name="Test Endpoint",
            url="https://discord.com/api/webhooks/123/abc",
            is_enabled=True,
        )
        self.assertEqual(str(endpoint), "Test Endpoint (enabled)")

    def test_disabled_endpoint_str(self):
        """Disabled endpoint shows in string representation."""
        endpoint = WebhookEndpoint.objects.create(
            name="Test Endpoint",
            url="https://discord.com/api/webhooks/123/abc",
            is_enabled=False,
        )
        self.assertEqual(str(endpoint), "Test Endpoint (disabled)")


class WebhookEventSubscriptionTests(TestCase):
    """Tests for webhook event subscriptions."""

    def test_create_subscription(self):
        """Can subscribe an endpoint to an event type."""
        endpoint = WebhookEndpoint.objects.create(
            name="Test Endpoint",
            url="https://discord.com/api/webhooks/123/abc",
        )
        subscription = WebhookEventSubscription.objects.create(
            endpoint=endpoint,
            event_type=WebhookEndpoint.EVENT_PROBLEM_REPORT_CREATED,
        )
        self.assertEqual(str(subscription), "Test Endpoint → Problem Report Created")

    def test_unique_subscription(self):
        """Cannot create duplicate subscriptions."""
        endpoint = WebhookEndpoint.objects.create(
            name="Test Endpoint",
            url="https://discord.com/api/webhooks/123/abc",
        )
        WebhookEventSubscription.objects.create(
            endpoint=endpoint,
            event_type=WebhookEndpoint.EVENT_PROBLEM_REPORT_CREATED,
        )
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            WebhookEventSubscription.objects.create(
                endpoint=endpoint,
                event_type=WebhookEndpoint.EVENT_PROBLEM_REPORT_CREATED,
            )


class WebhookSettingsTests(TestCase):
    """Tests for the singleton WebhookSettings model."""

    def test_get_settings_creates_if_missing(self):
        """get_settings creates the singleton if it doesn't exist."""
        self.assertEqual(WebhookSettings.objects.count(), 0)
        settings = WebhookSettings.get_settings()
        self.assertEqual(WebhookSettings.objects.count(), 1)
        self.assertTrue(settings.webhooks_enabled)

    def test_singleton_enforces_pk1(self):
        """Singleton save always uses pk=1."""
        settings1 = WebhookSettings(webhooks_enabled=True)
        settings1.save()
        self.assertEqual(settings1.pk, 1)

        # Update via get_settings
        settings2 = WebhookSettings.get_settings()
        settings2.webhooks_enabled = False
        settings2.save()
        self.assertEqual(WebhookSettings.objects.count(), 1)
        self.assertFalse(WebhookSettings.objects.get(pk=1).webhooks_enabled)


class DiscordFormatterTests(TestCase):
    """Tests for Discord message formatting.

    These tests verify the structure of webhook messages, not exact wording.
    This makes them resilient to copy changes.
    """

    def setUp(self):
        self.machine = create_machine()
        self.staff_user = create_staff_user()

    def test_format_problem_report_created(self):
        """Format a new problem report message."""
        report = create_problem_report(machine=self.machine)
        message = format_discord_message("problem_report_created", report)

        # Verify structure
        self.assertIn("embeds", message)
        self.assertEqual(len(message["embeds"]), 1)
        embed = message["embeds"][0]

        # Required fields exist
        self.assertIn("title", embed)
        self.assertIn("description", embed)
        self.assertIn("url", embed)
        self.assertIn("color", embed)

        # Title includes machine name
        self.assertIn(self.machine.display_name, embed["title"])

        # URL points to the problem report
        self.assertIn(f"/problem-reports/{report.pk}/", embed["url"])

    def test_format_log_entry_created(self):
        """Format a new log entry message."""
        log_entry = create_log_entry(machine=self.machine, created_by=self.staff_user)
        message = format_discord_message("log_entry_created", log_entry)

        embed = message["embeds"][0]

        # Required fields exist
        self.assertIn("title", embed)
        self.assertIn("description", embed)
        self.assertIn("url", embed)
        self.assertIn("color", embed)

        # Title includes machine name
        self.assertIn(self.machine.display_name, embed["title"])

        # Description includes log text
        self.assertIn(log_entry.text, embed["description"])

        # URL points to the log entry
        self.assertIn(f"/logs/{log_entry.pk}/", embed["url"])

    def test_format_log_entry_with_problem_report(self):
        """Format a log entry attached to a problem report includes PR link."""
        report = create_problem_report(machine=self.machine)
        log_entry = create_log_entry(
            machine=self.machine,
            created_by=self.staff_user,
            problem_report=report,
        )
        message = format_discord_message("log_entry_created", log_entry)

        embed = message["embeds"][0]

        # Description includes link to the problem report
        self.assertIn(f"/problem-reports/{report.pk}/", embed["description"])

    def test_format_log_entry_with_photos(self):
        """Format a log entry with photos creates multiple embeds for gallery."""
        from django.core.files.base import ContentFile

        from the_flip.apps.maintenance.models import LogEntryMedia

        log_entry = create_log_entry(machine=self.machine, created_by=self.staff_user)

        # Create mock photos
        for i in range(3):
            media = LogEntryMedia(
                log_entry=log_entry,
                media_type=LogEntryMedia.TYPE_PHOTO,
                display_order=i,
            )
            media.file.save(f"test{i}.jpg", ContentFile(b"fake image data"), save=True)

        message = format_discord_message("log_entry_created", log_entry)

        # Should have 3 embeds (main + 2 additional for gallery effect)
        self.assertEqual(len(message["embeds"]), 3)

        # First embed has title, description, and image
        self.assertIn("title", message["embeds"][0])
        self.assertIn("image", message["embeds"][0])

        # All embeds share the same URL (required for Discord gallery)
        main_url = message["embeds"][0]["url"]
        for embed in message["embeds"][1:]:
            self.assertIn("image", embed)
            self.assertEqual(embed["url"], main_url)

    def test_format_test_message(self):
        """Format a test message has required structure."""
        message = format_test_message("problem_report_created")

        self.assertIn("embeds", message)
        embed = message["embeds"][0]
        self.assertIn("title", embed)
        self.assertIn("description", embed)


class WebhookDeliveryTests(TestCase):
    """Tests for webhook delivery logic."""

    def setUp(self):
        self.machine = create_machine()
        self.staff_user = create_staff_user()
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

    def test_skips_when_globally_disabled(self):
        """Skips delivery when webhooks are globally disabled."""
        settings = WebhookSettings.get_settings()
        settings.webhooks_enabled = False
        settings.save()

        report = create_problem_report(machine=self.machine)
        result = deliver_webhooks("problem_report_created", report.pk, "ProblemReport")

        self.assertEqual(result["status"], "skipped")
        self.assertIn("globally disabled", result["reason"])

    def test_skips_when_event_type_disabled(self):
        """Skips delivery when event type is disabled."""
        settings = WebhookSettings.get_settings()
        settings.problem_reports_enabled = False
        settings.save()

        report = create_problem_report(machine=self.machine)
        result = deliver_webhooks("problem_report_created", report.pk, "ProblemReport")

        self.assertEqual(result["status"], "skipped")
        self.assertIn("problem report webhooks disabled", result["reason"])

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

    @patch("the_flip.apps.webhooks.tasks.requests.post")
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

    @patch("the_flip.apps.webhooks.tasks.requests.post")
    def test_handles_delivery_failure(self, mock_post):
        """Handles webhook delivery failure gracefully."""
        mock_post.side_effect = requests.RequestException("Connection error")

        report = create_problem_report(machine=self.machine)
        result = deliver_webhooks("problem_report_created", report.pk, "ProblemReport")

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["results"][0]["status"], "error")
        self.assertIn("Connection error", result["results"][0]["error"])


class WebhookSignalTests(TestCase):
    """Tests for webhook signal triggers."""

    def setUp(self):
        self.machine = create_machine()
        self.endpoint = WebhookEndpoint.objects.create(
            name="Test Endpoint",
            url="https://discord.com/api/webhooks/123/abc",
            is_enabled=True,
        )
        # Subscribe to all events
        for event_type, _ in WebhookEndpoint.EVENT_CHOICES:
            WebhookEventSubscription.objects.create(
                endpoint=self.endpoint,
                event_type=event_type,
                is_enabled=True,
            )

    @patch("the_flip.apps.webhooks.tasks.async_task")
    def test_signal_fires_on_problem_report_created(self, mock_async):
        """Signal fires when a problem report is created."""
        report = create_problem_report(machine=self.machine)

        mock_async.assert_called()
        call_args = mock_async.call_args
        self.assertEqual(call_args[0][1], "problem_report_created")
        self.assertEqual(call_args[0][2], report.pk)

    @patch("the_flip.apps.webhooks.tasks.async_task")
    def test_signal_fires_on_log_entry_created(self, mock_async):
        """Signal fires when a log entry is created."""
        staff_user = create_staff_user()
        log_entry = create_log_entry(machine=self.machine, created_by=staff_user)

        # Find the log_entry_created call
        calls = [c for c in mock_async.call_args_list if c[0][1] == "log_entry_created"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][2], log_entry.pk)
