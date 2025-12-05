"""Tests for webhook signal triggers."""

from unittest.mock import patch

from django.test import TestCase

from the_flip.apps.core.test_utils import create_log_entry, create_machine, create_staff_user
from the_flip.apps.discord.models import WebhookEndpoint, WebhookEventSubscription
from the_flip.apps.maintenance.models import ProblemReport


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

    @patch("the_flip.apps.discord.tasks.async_task")
    def test_signal_fires_on_problem_report_created(self, mock_async):
        """Signal fires when a problem report is created."""
        report = ProblemReport.objects.create(
            machine=self.machine,
            description="Test problem",
        )

        mock_async.assert_called()
        call_args = mock_async.call_args
        self.assertEqual(call_args[0][1], "problem_report_created")
        self.assertEqual(call_args[0][2], report.pk)

    @patch("the_flip.apps.discord.tasks.async_task")
    def test_signal_fires_on_log_entry_created(self, mock_async):
        """Signal fires when a log entry is created."""
        staff_user = create_staff_user()
        log_entry = create_log_entry(machine=self.machine, created_by=staff_user)

        # Find the log_entry_created call
        calls = [c for c in mock_async.call_args_list if c[0][1] == "log_entry_created"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][2], log_entry.pk)
