"""Tests for debounced (coalesced) Discord notifications.

Covers the two halves of the mechanism:

* ``dispatch_webhook`` routing — buffer the activity of whoever saved a record,
  but post signed-out (visitor) events and Discord-originated echoes without
  debouncing.
* ``flush_pending_notifications`` — one message per machine somebody worked on,
  led by what they wrote; routine record-keeping collapsed into a single summary;
  the max-wait cap; and records deleted before the flush.
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
from flipfix.apps.maintenance import auto_log

WEBHOOK_URL = "https://discord.com/api/webhooks/123/abc"


def _ok_response() -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status.return_value = None
    return response


def _set_history_user(obj, user):
    """Record who saved ``obj``, as the history middleware does for a real request."""
    type(obj).history.filter(id=obj.pk, history_type="+").update(history_user_id=user.pk)


def _payloads(mock_post) -> list[dict]:
    return [call.kwargs["json"] for call in mock_post.call_args_list]


def _descriptions(mock_post) -> list[str]:
    return [payload["embeds"][0]["description"] for payload in _payloads(mock_post)]


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
    def test_report_filed_on_someone_elses_behalf_is_buffered(self, mock_async):
        """Free-text attribution leaves reported_by_user null; the saver still groups it.

        This is the common case in production: a maintainer types a visitor's name
        into the attribution box rather than picking a maintainer, so the record
        credits nobody in the system even though a signed-in person filed it.
        """
        report = create_problem_report(machine=self.machine, reported_by_name="A visitor")
        _set_history_user(report, self.user)

        dispatch_webhook("problem_report", report.pk)

        mock_async.assert_not_called()
        self.assertEqual(PendingNotification.objects.get().actor, self.user)

    @patch("flipfix.apps.discord.tasks.async_task")
    def test_parts_request_without_requester_is_buffered(self, mock_async):
        request = create_part_request(machine=self.machine, text="Flipper coil")
        _set_history_user(request, self.user)

        dispatch_webhook("part_request", request.pk)

        mock_async.assert_not_called()
        self.assertEqual(PendingNotification.objects.get().actor, self.user)

    @patch("flipfix.apps.discord.tasks.async_task")
    def test_record_marked_not_to_announce_is_dropped(self, mock_async):
        """An intake checklist and friends are recorded, but not announced."""
        report = create_problem_report(
            machine=self.machine, reported_by_user=self.user, announce=False
        )

        dispatch_webhook("problem_report", report.pk)

        mock_async.assert_not_called()
        self.assertEqual(PendingNotification.objects.count(), 0)

    @override_config(DISCORD_NOTIFICATION_COALESCING_ENABLED=False)
    @patch("flipfix.apps.discord.tasks.async_task")
    def test_record_marked_not_to_announce_is_dropped_with_coalescing_off(self, mock_async):
        log = create_log_entry(machine=self.machine, created_by=self.user, announce=False)

        dispatch_webhook("log_entry", log.pk)

        mock_async.assert_not_called()

    @patch("flipfix.apps.discord.tasks.async_task")
    def test_records_without_an_announce_field_still_post(self, mock_async):
        """Parts records have no announce field; they must not be suppressed."""
        request = create_part_request(machine=self.machine, text="Flipper coil")

        dispatch_webhook("part_request", request.pk)

        self.assertEqual(
            mock_async.call_count + PendingNotification.objects.count(),
            1,
        )

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
    def test_work_on_a_machine_becomes_one_post_led_by_what_was_written(self, mock_post):
        """The motivating case: fix a machine, mark it Good, move it to the floor."""
        mock_post.return_value = _ok_response()
        repair = create_log_entry(
            machine=self.machine,
            created_by=self.user,
            text="Replaced all elastics and cleaned playfield.",
        )
        status = create_log_entry(
            machine=self.machine,
            created_by=self.user,
            text=auto_log.status_changed_text("Unknown", "Good"),
        )
        moved = create_log_entry(
            machine=self.machine,
            created_by=self.user,
            text=auto_log.moved_to_floor_text(self.machine.name),
        )
        for entry in (repair, status, moved):
            self._buffer("log_entry", entry, minutes_ago=6)

        result = flush_pending_notifications()

        self.assertEqual(result.status, "success")
        mock_post.assert_called_once()
        embed = mock_post.call_args.kwargs["json"]["embeds"][0]
        self.assertIn(self.machine.short_display_name, embed["title"])
        # The substantive entry leads, and the routine ones follow it as plain lines.
        self.assertIn("Replaced all elastics and cleaned playfield.", embed["description"])
        self.assertIn(auto_log.status_changed_text("Unknown", "Good"), embed["description"])
        self.assertIn("has moved to the floor!", embed["description"])
        self.assertEqual(PendingNotification.objects.filter(sent_at__isnull=True).count(), 0)

    @patch("flipfix.apps.discord.tasks.requests.post")
    def test_two_machines_worked_on_become_two_posts(self, mock_post):
        mock_post.return_value = _ok_response()
        other = create_machine()
        log1 = create_log_entry(machine=self.machine, created_by=self.user, text="Replaced coil")
        log2 = create_log_entry(machine=other, created_by=self.user, text="Cleaned playfield")
        for entry in (log1, log2):
            self._buffer("log_entry", entry, minutes_ago=6)

        flush_pending_notifications()

        self.assertEqual(mock_post.call_count, 2)
        descriptions = _descriptions(mock_post)
        self.assertTrue(any("Replaced coil" in d for d in descriptions))
        self.assertTrue(any("Cleaned playfield" in d for d in descriptions))
        self.assertEqual(PendingNotification.objects.filter(sent_at__isnull=True).count(), 0)

    @patch("flipfix.apps.discord.tasks.requests.post")
    def test_routine_changes_across_machines_become_one_summary(self, mock_post):
        """A sweep of status changes is grouped by action, not by machine."""
        mock_post.return_value = _ok_response()
        other = create_machine()
        for machine in (self.machine, other):
            entry = create_log_entry(
                machine=machine,
                created_by=self.user,
                text=auto_log.status_changed_text("Unknown", "Good"),
            )
            self._buffer("log_entry", entry, minutes_ago=6)

        flush_pending_notifications()

        mock_post.assert_called_once()
        embed = mock_post.call_args.kwargs["json"]["embeds"][0]
        self.assertIn("2 updates", embed["title"])
        self.assertIn("**Marked Good**", embed["description"])
        self.assertIn(self.machine.short_display_name, embed["description"])
        self.assertIn(other.short_display_name, embed["description"])

    @patch("flipfix.apps.discord.tasks.requests.post")
    def test_written_work_and_an_unrelated_sweep_split(self, mock_post):
        """A repair on one machine and bookkeeping on another are different news."""
        mock_post.return_value = _ok_response()
        other = create_machine()
        repair = create_log_entry(
            machine=self.machine, created_by=self.user, text="Rebuilt flipper"
        )
        routine = create_log_entry(
            machine=other,
            created_by=self.user,
            text=auto_log.status_changed_text("Good", "Fixing"),
        )
        for entry in (repair, routine):
            self._buffer("log_entry", entry, minutes_ago=6)

        flush_pending_notifications()

        self.assertEqual(mock_post.call_count, 2)
        titles = [payload["embeds"][0]["title"] for payload in _payloads(mock_post)]
        self.assertIn(f"🗒️ {self.machine.short_display_name}", titles)
        self.assertTrue(any("1 update" in title for title in titles))

    @patch("flipfix.apps.discord.tasks.requests.post")
    def test_closing_a_report_names_the_report(self, mock_post):
        """ "Closed problem report" alone says nothing; the follow-up line names it."""
        mock_post.return_value = _ok_response()
        report = create_problem_report(
            machine=self.machine,
            reported_by_user=self.user,
            description="Left flipper is dead",
        )
        repair = create_log_entry(
            machine=self.machine, created_by=self.user, text="New coil fitted"
        )
        closed = create_log_entry(
            machine=self.machine,
            created_by=self.user,
            problem_report=report,
            text=auto_log.CLOSED_REPORT_TEXT,
        )
        for handler_name, obj in (("log_entry", repair), ("log_entry", closed)):
            self._buffer(handler_name, obj, minutes_ago=6)

        flush_pending_notifications()

        mock_post.assert_called_once()
        description = mock_post.call_args.kwargs["json"]["embeds"][0]["description"]
        self.assertIn(f"{auto_log.CLOSED_REPORT_TEXT}: ", description)
        self.assertIn("Left flipper is dead", description)

    @patch("flipfix.apps.discord.tasks.requests.post")
    def test_one_post_failing_does_not_repost_the_others(self, mock_post):
        import requests

        other = create_machine()
        log1 = create_log_entry(machine=self.machine, created_by=self.user, text="Replaced coil")
        log2 = create_log_entry(machine=other, created_by=self.user, text="Cleaned playfield")
        rows = [self._buffer("log_entry", entry, minutes_ago=6) for entry in (log1, log2)]
        mock_post.side_effect = [_ok_response(), requests.RequestException("Discord down")]

        flush_pending_notifications()

        self.assertEqual(mock_post.call_count, 2)
        unsent = PendingNotification.objects.filter(sent_at__isnull=True)
        self.assertEqual([row.pk for row in unsent], [rows[1].pk])

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
        # The request leads (somebody wrote it); the bare status flip follows it,
        # naming the part rather than repeating "Status changed".
        self.assertIn("📦", embed["title"])
        self.assertIn("Marked Ordered: Flipper coil A-12345", embed["description"])

    @patch("flipfix.apps.discord.tasks.requests.post")
    def test_parts_summary_line_drops_the_supplier_url(self, mock_post):
        from flipfix.apps.parts.models import PartRequest

        mock_post.return_value = _ok_response()
        request = create_part_request(
            requested_by=self.maintainer,
            machine=self.machine,
            text="Drop target stickers\n\nhttps://www.pinballlife.com/some-very-long-product-url",
        )
        update = create_part_request_update(
            part_request=request,
            posted_by=self.maintainer,
            text=auto_log.status_changed_text("Requested", "Ordered"),
            new_status=PartRequest.Status.ORDERED,
        )
        repair = create_log_entry(machine=self.machine, created_by=self.user, text="Fitted them")
        for handler_name, obj in (
            ("log_entry", repair),
            ("part_request", request),
            ("part_request_update", update),
        ):
            self._buffer(handler_name, obj, minutes_ago=6)

        flush_pending_notifications()

        description = mock_post.call_args.kwargs["json"]["embeds"][0]["description"]
        self.assertIn("Marked Ordered: Drop target stickers", description)
        self.assertNotIn("pinballlife.com", description.split("— ")[-1])
