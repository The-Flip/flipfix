"""Tests for the replay_notification_coalescing management command."""

from __future__ import annotations

import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path

from django.core.management import CommandError, call_command
from django.test import TestCase, tag
from django.utils import timezone

from flipfix.apps.core.test_utils import create_log_entry, create_machine, create_maintainer_user
from flipfix.apps.discord.management.commands.replay_notification_coalescing import (
    ReplayEvent,
    batch_by_actor,
    render_payload,
    sessions,
)
from flipfix.apps.discord.tasks import COALESCE_MAX_WAIT, COALESCE_QUIET_PERIOD
from flipfix.apps.discord.webhook_handlers import WebhookHandler


class _Actor:
    """Stand-in for a User: the buffering only ever reads the primary key."""

    def __init__(self, pk: int) -> None:
        self.pk = pk


def _event(fired_at, actor: _Actor | None) -> ReplayEvent:
    # Buffering reads only the timestamp and the actor, so the record and its
    # handler can be inert stand-ins.
    return ReplayEvent(
        handler=WebhookHandler(),
        obj=None,
        fired_at=fired_at,
        actor=actor,
        attributed=actor,
    )


@tag("commands")
class BufferSimulationTests(TestCase):
    """The replay must debounce exactly as flush_pending_notifications does."""

    def setUp(self):
        self.base = timezone.now().replace(microsecond=0)
        self.actor = _Actor(1)

    def test_events_within_the_quiet_period_share_a_batch(self):
        events = [
            _event(self.base, self.actor),
            _event(self.base + timedelta(minutes=2), self.actor),
        ]
        batches = batch_by_actor(events)

        self.assertEqual(len(batches), 1)
        self.assertEqual(len(batches[0].events), 2)
        # Flushed a quiet period after the *last* event, not the first.
        self.assertEqual(
            batches[0].flush_at, self.base + timedelta(minutes=2) + COALESCE_QUIET_PERIOD
        )
        self.assertFalse(batches[0].capped)

    def test_silence_longer_than_the_quiet_period_starts_a_new_batch(self):
        events = [
            _event(self.base, self.actor),
            _event(self.base + COALESCE_QUIET_PERIOD + timedelta(minutes=1), self.actor),
        ]
        batches = batch_by_actor(events)

        self.assertEqual([len(b.events) for b in batches], [1, 1])

    def test_max_wait_caps_a_continuously_active_actor(self):
        # An event every two minutes for half an hour: never quiet, so only the
        # cap can close the buffer.
        events = [_event(self.base + timedelta(minutes=2 * i), self.actor) for i in range(15)]
        batches = batch_by_actor(events)

        self.assertGreater(len(batches), 1)
        self.assertTrue(batches[0].capped)
        self.assertEqual(batches[0].flush_at, self.base + COALESCE_MAX_WAIT)
        # Nothing is dropped when a batch is cut short.
        self.assertEqual(sum(len(b.events) for b in batches), len(events))

    def test_actors_are_buffered_independently(self):
        other = _Actor(2)
        events = [
            _event(self.base, self.actor),
            _event(self.base + timedelta(seconds=30), other),
            _event(self.base + timedelta(minutes=1), self.actor),
        ]
        batches = batch_by_actor(events)

        self.assertEqual(sorted(len(b.events) for b in batches), [1, 2])

    def test_events_with_no_actor_are_never_buffered(self):
        self.assertEqual(batch_by_actor([_event(self.base, None)]), [])

    def test_a_capped_session_regroups_into_one_session(self):
        events = [_event(self.base + timedelta(minutes=2 * i), self.actor) for i in range(15)]
        batches = batch_by_actor(events)

        # The cap split the buffer, but the person never stopped working.
        self.assertEqual(len(sessions(batches)), 1)
        self.assertEqual(sessions(batches)[0], batches)

    def test_a_genuine_gap_separates_sessions(self):
        events = [
            _event(self.base, self.actor),
            _event(self.base + timedelta(hours=2), self.actor),
        ]
        self.assertEqual(len(sessions(batch_by_actor(events))), 2)


@tag("commands")
class PayloadRenderingTests(TestCase):
    def test_renders_title_link_body_and_photo_count(self):
        payload = {
            "embeds": [
                {
                    "title": "🗒️ Kicker",
                    "url": "https://example.test/logs/1/",
                    "description": "Fixed it.\n\n— william",
                    "image": {"url": "https://example.test/a.jpg"},
                },
                {"image": {"url": "https://example.test/b.jpg"}},
            ]
        }

        rendered = render_payload(payload)

        self.assertIn("TITLE  🗒️ Kicker", rendered)
        self.assertIn("LINK   https://example.test/logs/1/", rendered)
        self.assertIn("  Fixed it.", rendered)
        self.assertIn("IMAGES 2 photo embed(s)", rendered)
        # The counts describe the embed description, which is what Discord shows.
        self.assertIn("[20 chars, 4 words in body]", rendered)

    def test_omits_the_photo_line_when_there_are_none(self):
        payload = {"embeds": [{"title": "t", "description": "d"}]}
        self.assertNotIn("IMAGES", render_payload(payload))


@tag("commands")
class CommandTests(TestCase):
    def test_writes_a_document_from_the_local_history(self):
        user = create_maintainer_user()
        machine = create_machine()
        create_log_entry(machine=machine, text="Rebuilt the flippers.", created_by=user)
        create_log_entry(machine=machine, text="Status changed: Broken → Good", created_by=user)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "cases.md"
            stdout = StringIO()
            call_command("replay_notification_coalescing", output=str(output), stdout=stdout)

            document = output.read_text(encoding="utf-8")

        self.assertIn("# Discord notification coalescing — real cases", document)
        self.assertIn("## The stream, in numbers", document)
        self.assertIn("## What the rework changed", document)
        # The rendered payload comes from the live formatter, so the hand-written
        # entry leads and the automatic one folds in beneath it.
        self.assertIn("Rebuilt the flippers.", document)
        self.assertIn("Status changed: Broken → Good", document)

    def test_does_not_leave_site_url_overridden(self):
        from django.conf import settings

        before = settings.SITE_URL
        user = create_maintainer_user()
        create_log_entry(machine=create_machine(), text="A note.", created_by=user)

        with tempfile.TemporaryDirectory() as directory:
            call_command(
                "replay_notification_coalescing",
                output=str(Path(directory) / "cases.md"),
                stdout=StringIO(),
            )

        self.assertEqual(settings.SITE_URL, before)

    def test_empty_database_explains_what_to_run(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesMessage(CommandError, "No events found"):
                call_command(
                    "replay_notification_coalescing",
                    output=str(Path(directory) / "cases.md"),
                    stdout=StringIO(),
                )

    def test_rejects_an_unknown_timezone(self):
        with self.assertRaisesMessage(CommandError, "Unknown timezone"):
            call_command(
                "replay_notification_coalescing", tz="Mars/Olympus_Mons", stdout=StringIO()
            )
