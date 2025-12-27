"""Tests for webhook signal triggers."""

from unittest.mock import patch

from constance.test import override_config
from django.test import TestCase, tag

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.core.test_utils import (
    create_log_entry,
    create_machine,
    create_maintainer_user,
    create_part_request,
    create_part_request_update,
    create_problem_report,
)
from the_flip.apps.discord.models import DiscordMessageMapping
from the_flip.apps.maintenance.models import ProblemReport


@tag("tasks")
@override_config(DISCORD_WEBHOOKS_ENABLED=True, DISCORD_WEBHOOK_URL="https://test.webhook")
class WebhookSignalTests(TestCase):
    """Tests for webhook signal triggers."""

    def setUp(self):
        self.machine = create_machine()

    @patch("the_flip.apps.discord.tasks.async_task")
    def test_signal_fires_on_problem_report_created(self, mock_async):
        """Signal fires when a problem report is created."""
        # All webhook signals use transaction.on_commit
        with self.captureOnCommitCallbacks(execute=True):
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

        # Log entry signal uses transaction.on_commit, so we need to capture and execute
        with self.captureOnCommitCallbacks(execute=True):
            log_entry = create_log_entry(machine=self.machine, created_by=maintainer_user)

        # Find the log_entry_created call
        calls = [c for c in mock_async.call_args_list if c[0][1] == "log_entry_created"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][2], log_entry.pk)


@tag("tasks")
@override_config(DISCORD_WEBHOOKS_ENABLED=True, DISCORD_WEBHOOK_URL="https://test.webhook")
class PartRequestWebhookSignalTests(TestCase):
    """Tests for part request webhook signal triggers."""

    def setUp(self):
        self.maintainer_user = create_maintainer_user()
        self.maintainer = Maintainer.objects.get(user=self.maintainer_user)
        self.machine = create_machine()

    @patch("the_flip.apps.discord.tasks.async_task")
    def test_signal_fires_on_part_request_created(self, mock_async):
        """Signal fires when a part request is created."""
        # All webhook signals use transaction.on_commit
        with self.captureOnCommitCallbacks(execute=True):
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
        with self.captureOnCommitCallbacks(execute=True):
            part_request = create_part_request(requested_by=self.maintainer)
        mock_async.reset_mock()

        # All webhook signals use transaction.on_commit
        with self.captureOnCommitCallbacks(execute=True):
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
        """Status change via update only fires update_created (not a separate status event)."""
        from the_flip.apps.parts.models import PartRequest

        with self.captureOnCommitCallbacks(execute=True):
            part_request = create_part_request(requested_by=self.maintainer)
        mock_async.reset_mock()

        # All webhook signals use transaction.on_commit
        with self.captureOnCommitCallbacks(execute=True):
            create_part_request_update(
                part_request=part_request,
                posted_by=self.maintainer,
                text="Ordered it",
                new_status=PartRequest.Status.ORDERED,
            )

        # Should only fire update_created (status info is included in the update message)
        event_types = [c[0][1] for c in mock_async.call_args_list]
        self.assertIn("part_request_update_created", event_types)
        self.assertNotIn("part_request_status_changed", event_types)


@tag("tasks")
@override_config(DISCORD_WEBHOOKS_ENABLED=True, DISCORD_WEBHOOK_URL="https://test.webhook")
class DiscordOriginatedRecordTests(TestCase):
    """Tests that webhooks are NOT dispatched for Discord-originated records.

    When the Discord bot creates a record in Flipfix, we don't want to
    post it back to Discord via webhook (that would be redundant).
    """

    def setUp(self):
        self.machine = create_machine()

    @patch("the_flip.apps.discord.tasks.async_task")
    def test_signal_skips_discord_originated_problem_report(self, mock_async):
        """No webhook when ProblemReport was created from Discord."""
        with self.captureOnCommitCallbacks(execute=True):
            report = create_problem_report(machine=self.machine)
            # Mark as Discord-originated BEFORE transaction commits
            DiscordMessageMapping.mark_processed("discord_msg_123", report)

        # Should NOT have fired problem_report_created webhook
        calls = [c for c in mock_async.call_args_list if c[0][1] == "problem_report_created"]
        self.assertEqual(len(calls), 0, "Webhook should not fire for Discord-originated record")

    @patch("the_flip.apps.discord.tasks.async_task")
    def test_signal_skips_discord_originated_log_entry(self, mock_async):
        """No webhook when LogEntry was created from Discord."""
        maintainer_user = create_maintainer_user()

        with self.captureOnCommitCallbacks(execute=True):
            log_entry = create_log_entry(machine=self.machine, created_by=maintainer_user)
            # Mark as Discord-originated BEFORE transaction commits
            DiscordMessageMapping.mark_processed("discord_msg_456", log_entry)

        # Should NOT have fired log_entry_created webhook
        calls = [c for c in mock_async.call_args_list if c[0][1] == "log_entry_created"]
        self.assertEqual(len(calls), 0, "Webhook should not fire for Discord-originated record")

    @patch("the_flip.apps.discord.tasks.async_task")
    def test_signal_skips_discord_originated_part_request(self, mock_async):
        """No webhook when PartRequest was created from Discord."""
        maintainer_user = create_maintainer_user()
        maintainer = Maintainer.objects.get(user=maintainer_user)

        with self.captureOnCommitCallbacks(execute=True):
            part_request = create_part_request(
                requested_by=maintainer,
                machine=self.machine,
            )
            # Mark as Discord-originated BEFORE transaction commits
            DiscordMessageMapping.mark_processed("discord_msg_789", part_request)

        # Should NOT have fired part_request_created webhook
        calls = [c for c in mock_async.call_args_list if c[0][1] == "part_request_created"]
        self.assertEqual(len(calls), 0, "Webhook should not fire for Discord-originated record")
