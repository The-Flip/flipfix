"""Tests for debounced (coalesced) Discord notifications.

Covers the two halves of the mechanism:

* ``dispatch_webhook`` routing — buffer maintainer activity, but post anonymous
  (visitor) events and Discord-originated echoes without debouncing.
* ``flush_pending_notifications`` — combine a quiet actor's buffered events into a
  single message, honour the max-wait cap, keep single events rich, and cope with
  records deleted before the flush.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from constance.test import override_config
from django.test import TestCase, tag
from django.utils import timezone

from flipfix.apps.accounts.models import Maintainer
from flipfix.apps.core.test_utils import (
    create_log_entry,
    create_machine,
    create_maintainer_user,
    create_part_request,
    create_part_request_update,
    create_problem_report,
)
from flipfix.apps.discord.models import DiscordMessageMapping, PendingNotification
from flipfix.apps.discord.tasks import dispatch_webhook, flush_pending_notifications

WEBHOOK_URL = "https://discord.com/api/webhooks/123/abc"


def _ok_response() -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status.return_value = None
    return response


@tag("tasks")
@override_config(
    DISCORD_WEBHOOKS_ENABLED=True,
    DISCORD_WEBHOOK_URL=WEBHOOK_URL,
    DISCORD_NOTIFICATION_COALESCING_ENABLED=True,
)
class DispatchRoutingTests(TestCase):
    """dispatch_webhook decides between buffering and immediate delivery."""

    def setUp(self):
        self.machine = create_machine()
        self.user = create_maintainer_user()

    @patch("flipfix.apps.discord.tasks.async_task")
    def test_maintainer_event_is_buffered(self, mock_async):
        log = create_log_entry(machine=self.machine, created_by=self.user, text="Fixed flipper")

        dispatch_webhook("log_entry", log.pk)

        mock_async.assert_not_called()
        pending = PendingNotification.objects.get()
        self.assertEqual(pending.handler_name, "log_entry")
        self.assertEqual(pending.object_id, log.pk)
        self.assertEqual(pending.actor, self.user)
        self.assertIsNone(pending.sent_at)

    @patch("flipfix.apps.discord.tasks.async_task")
    def test_anonymous_problem_report_posts_immediately(self, mock_async):
        # Visitor submissions have no reported_by_user → should not debounce.
        report = create_problem_report(machine=self.machine)

        dispatch_webhook("problem_report", report.pk)

        mock_async.assert_called_once()
        self.assertEqual(PendingNotification.objects.count(), 0)

    @patch("flipfix.apps.discord.tasks.async_task")
    def test_maintainer_problem_report_is_buffered(self, mock_async):
        report = create_problem_report(machine=self.machine, reported_by_user=self.user)

        dispatch_webhook("problem_report", report.pk)

        mock_async.assert_not_called()
        self.assertEqual(PendingNotification.objects.count(), 1)

    @patch("flipfix.apps.discord.tasks.async_task")
    def test_discord_originated_event_is_skipped(self, mock_async):
        log = create_log_entry(machine=self.machine, created_by=self.user)
        DiscordMessageMapping.mark_processed("discord_msg_1", log)

        dispatch_webhook("log_entry", log.pk)

        mock_async.assert_not_called()
        self.assertEqual(PendingNotification.objects.count(), 0)

    @override_config(DISCORD_NOTIFICATION_COALESCING_ENABLED=False)
    @patch("flipfix.apps.discord.tasks.async_task")
    def test_coalescing_off_posts_immediately(self, mock_async):
        log = create_log_entry(machine=self.machine, created_by=self.user)

        dispatch_webhook("log_entry", log.pk)

        mock_async.assert_called_once()
        self.assertEqual(PendingNotification.objects.count(), 0)


@tag("tasks")
@override_config(DISCORD_WEBHOOKS_ENABLED=True, DISCORD_WEBHOOK_URL=WEBHOOK_URL)
class FlushTests(TestCase):
    """flush_pending_notifications combines and delivers due buffers."""

    def setUp(self):
        self.user = create_maintainer_user()
        self.maintainer = Maintainer.objects.get(user=self.user)
        self.machine = create_machine()

    def _buffer(self, handler_name: str, obj, *, minutes_ago: float, actor=None):
        """Buffer an event and backdate it to simulate an elapsed window."""
        pending = PendingNotification.objects.create(
            handler_name=handler_name,
            object_id=obj.pk,
            actor=actor or self.user,
        )
        PendingNotification.objects.filter(pk=pending.pk).update(
            buffered_at=timezone.now() - timedelta(minutes=minutes_ago)
        )
        return pending

    @patch("flipfix.apps.discord.tasks.requests.post")
    def test_combines_events_by_machine(self, mock_post):
        mock_post.return_value = _ok_response()
        other = create_machine()
        log1 = create_log_entry(machine=self.machine, created_by=self.user, text="Replaced coil")
        report = create_problem_report(machine=self.machine, reported_by_user=self.user)
        log2 = create_log_entry(machine=other, created_by=self.user, text="Cleaned playfield")
        for handler_name, obj in (
            ("log_entry", log1),
            ("problem_report", report),
            ("log_entry", log2),
        ):
            self._buffer(handler_name, obj, minutes_ago=6)  # quiet period elapsed

        result = flush_pending_notifications()

        self.assertEqual(result.status, "success")
        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(len(payload["embeds"]), 1)
        embed = payload["embeds"][0]
        self.assertIn("3 updates", embed["title"])
        self.assertIn(self.machine.short_display_name, embed["description"])
        self.assertIn(other.short_display_name, embed["description"])
        self.assertEqual(PendingNotification.objects.filter(sent_at__isnull=True).count(), 0)

    @patch("flipfix.apps.discord.tasks.requests.post")
    def test_waits_while_actor_still_active(self, mock_post):
        log = create_log_entry(machine=self.machine, created_by=self.user)
        self._buffer("log_entry", log, minutes_ago=2)  # < 5 min quiet, < 15 min cap

        result = flush_pending_notifications()

        mock_post.assert_not_called()
        self.assertEqual(result.status, "success")  # ran, but flushed nobody
        self.assertEqual(PendingNotification.objects.filter(sent_at__isnull=True).count(), 1)

    @patch("flipfix.apps.discord.tasks.requests.post")
    def test_max_wait_cap_flushes_active_actor(self, mock_post):
        mock_post.return_value = _ok_response()
        old = create_log_entry(machine=self.machine, created_by=self.user, text="first")
        recent = create_log_entry(machine=self.machine, created_by=self.user, text="latest")
        self._buffer("log_entry", old, minutes_ago=16)  # oldest past the 15-min cap
        self._buffer("log_entry", recent, minutes_ago=1)  # still active → quiet not met

        flush_pending_notifications()

        mock_post.assert_called_once()
        self.assertEqual(PendingNotification.objects.filter(sent_at__isnull=True).count(), 0)

    @patch("flipfix.apps.discord.tasks.requests.post")
    def test_single_event_keeps_rich_embed(self, mock_post):
        mock_post.return_value = _ok_response()
        log = create_log_entry(machine=self.machine, created_by=self.user, text="Solo entry")
        self._buffer("log_entry", log, minutes_ago=6)

        flush_pending_notifications()

        mock_post.assert_called_once()
        title = mock_post.call_args.kwargs["json"]["embeds"][0]["title"]
        # The rich single-record embed is titled by machine, not the digest header.
        self.assertNotIn("update", title.lower())
        self.assertIn(self.machine.short_display_name, title)

    @patch("flipfix.apps.discord.tasks.requests.post")
    def test_separate_actors_get_separate_messages(self, mock_post):
        mock_post.return_value = _ok_response()
        other_user = create_maintainer_user()
        log_a = create_log_entry(machine=self.machine, created_by=self.user, text="a")
        log_b = create_log_entry(machine=self.machine, created_by=other_user, text="b")
        self._buffer("log_entry", log_a, minutes_ago=6, actor=self.user)
        self._buffer("log_entry", log_b, minutes_ago=6, actor=other_user)

        flush_pending_notifications()

        self.assertEqual(mock_post.call_count, 2)

    @patch("flipfix.apps.discord.tasks.requests.post")
    def test_skips_deleted_records_but_delivers_survivors(self, mock_post):
        mock_post.return_value = _ok_response()
        survivor = create_log_entry(machine=self.machine, created_by=self.user, text="stays")
        doomed = create_log_entry(machine=self.machine, created_by=self.user, text="goes")
        self._buffer("log_entry", survivor, minutes_ago=6)
        self._buffer("log_entry", doomed, minutes_ago=6)
        doomed.delete()

        flush_pending_notifications()

        mock_post.assert_called_once()
        # Both rows are consumed once the group flushes.
        self.assertEqual(PendingNotification.objects.filter(sent_at__isnull=True).count(), 0)

    @patch("flipfix.apps.discord.tasks.requests.post")
    def test_consumes_buffer_when_all_records_deleted(self, mock_post):
        log = create_log_entry(machine=self.machine, created_by=self.user)
        self._buffer("log_entry", log, minutes_ago=6)
        log.delete()

        flush_pending_notifications()

        mock_post.assert_not_called()
        self.assertEqual(PendingNotification.objects.filter(sent_at__isnull=True).count(), 0)

    @override_config(DISCORD_WEBHOOKS_ENABLED=False)
    @patch("flipfix.apps.discord.tasks.requests.post")
    def test_flush_skips_when_webhooks_disabled(self, mock_post):
        log = create_log_entry(machine=self.machine, created_by=self.user)
        self._buffer("log_entry", log, minutes_ago=6)

        result = flush_pending_notifications()

        self.assertEqual(result.status, "skipped")
        mock_post.assert_not_called()
        self.assertEqual(PendingNotification.objects.filter(sent_at__isnull=True).count(), 1)

    @patch("flipfix.apps.discord.tasks.requests.post")
    def test_delivery_failure_leaves_buffer_for_retry(self, mock_post):
        import requests

        mock_post.side_effect = requests.RequestException("Discord down")
        log = create_log_entry(machine=self.machine, created_by=self.user)
        self._buffer("log_entry", log, minutes_ago=6)

        flush_pending_notifications()

        # Not marked sent → next run retries.
        self.assertEqual(PendingNotification.objects.filter(sent_at__isnull=True).count(), 1)

    @patch("flipfix.apps.discord.tasks.requests.post")
    def test_combined_parts_events_render(self, mock_post):
        from flipfix.apps.parts.models import PartRequest

        mock_post.return_value = _ok_response()
        request = create_part_request(
            requested_by=self.maintainer, machine=self.machine, text="Flipper coil A-12345"
        )
        # A status-change update whose own text is an auto-generated "Status changed…".
        update = create_part_request_update(
            part_request=request,
            posted_by=self.maintainer,
            text="Status changed: Requested → Ordered",
            new_status=PartRequest.Status.ORDERED,
        )
        self._buffer("part_request", request, minutes_ago=6)
        self._buffer("part_request_update", update, minutes_ago=6)

        flush_pending_notifications()

        mock_post.assert_called_once()
        embed = mock_post.call_args.kwargs["json"]["embeds"][0]
        self.assertIn("2 updates", embed["title"])
        # The update line names the part (not just "Status changed") and its status.
        self.assertIn("Flipper coil A-12345", embed["description"])
        self.assertIn("Ordered", embed["description"])
