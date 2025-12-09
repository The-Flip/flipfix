"""Tests for webhook signal triggers."""

from unittest.mock import patch

from django.test import TestCase

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.core.test_utils import (
    create_log_entry,
    create_machine,
    create_maintainer_user,
    create_part_request,
    create_part_request_update,
)
from the_flip.apps.maintenance.models import ProblemReport
from the_flip.apps.parts.models import PartRequest


class WebhookSignalTests(TestCase):
    """Tests for webhook signal triggers."""

    def setUp(self):
        self.machine = create_machine()

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
        maintainer_user = create_maintainer_user()
        log_entry = create_log_entry(machine=self.machine, created_by=maintainer_user)

        # Find the log_entry_created call
        calls = [c for c in mock_async.call_args_list if c[0][1] == "log_entry_created"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][2], log_entry.pk)


class PartRequestWebhookSignalTests(TestCase):
    """Tests for part request webhook signal triggers."""

    def setUp(self):
        self.maintainer_user = create_maintainer_user()
        self.maintainer = Maintainer.objects.get(user=self.maintainer_user)
        self.machine = create_machine()

    @patch("the_flip.apps.discord.tasks.async_task")
    def test_signal_fires_on_part_request_created(self, mock_async):
        """Signal fires when a part request is created."""
        part_request = create_part_request(
            requested_by=self.maintainer,
            machine=self.machine,
        )

        # Find the part_request_created call
        calls = [c for c in mock_async.call_args_list if c[0][1] == "part_request_created"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][2], part_request.pk)

    @patch("the_flip.apps.discord.tasks.async_task")
    def test_signal_fires_on_part_request_update_created(self, mock_async):
        """Signal fires when a part request update is created."""
        part_request = create_part_request(requested_by=self.maintainer)
        mock_async.reset_mock()

        update = create_part_request_update(
            part_request=part_request,
            posted_by=self.maintainer,
            text="Update text",
        )

        # Find the part_request_update_created call
        calls = [c for c in mock_async.call_args_list if c[0][1] == "part_request_update_created"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][2], update.pk)

    @patch("the_flip.apps.discord.tasks.async_task")
    def test_signal_fires_on_status_change_via_update(self, mock_async):
        """Signal fires when status changes via an update."""
        part_request = create_part_request(requested_by=self.maintainer)
        mock_async.reset_mock()

        create_part_request_update(
            part_request=part_request,
            posted_by=self.maintainer,
            text="Ordered it",
            new_status=PartRequest.STATUS_ORDERED,
        )

        # Should fire both update_created and status_changed
        event_types = [c[0][1] for c in mock_async.call_args_list]
        self.assertIn("part_request_update_created", event_types)
        self.assertIn("part_request_status_changed", event_types)
