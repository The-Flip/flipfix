"""Tests for the analyze_notification_clusters management command."""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase, tag
from django.utils import timezone

from flipfix.apps.core.test_utils import create_log_entry, create_machine, create_maintainer_user
from flipfix.apps.discord.management.commands.analyze_notification_clusters import (
    Event,
    gap_clusters,
    global_peaks,
)


def _event(fired_at, *, actor="u:1", machine_id=1, event_type="log_entry") -> Event:
    return Event(
        fired_at=fired_at,
        event_type=event_type,
        actor_key=actor,
        actor_label=actor,
        machine_id=machine_id,
        machine_label=f"machine {machine_id}",
        summary="x",
    )


@tag("commands")
class ClusteringHelperTests(TestCase):
    def setUp(self):
        self.base = timezone.now()

    def test_gap_splits_when_silence_exceeds_threshold(self):
        events = [
            _event(self.base),
            _event(self.base + timedelta(minutes=2)),
            _event(self.base + timedelta(minutes=30)),  # new session after the gap
        ]
        clusters = gap_clusters(events, lambda e: e.actor_key, timedelta(minutes=10))
        self.assertEqual(sorted(c.size for c in clusters), [1, 2])

    def test_gap_separates_distinct_keys(self):
        events = [
            _event(self.base, actor="u:1"),
            _event(self.base + timedelta(minutes=1), actor="u:2"),
        ]
        clusters = gap_clusters(events, lambda e: e.actor_key, timedelta(minutes=10))
        self.assertEqual([c.size for c in clusters], [1, 1])

    def test_global_peaks_respects_min_peak(self):
        events = [_event(self.base + timedelta(seconds=30 * i)) for i in range(6)]
        self.assertEqual(len(global_peaks(events, timedelta(minutes=15), min_peak=5)), 1)
        self.assertEqual(len(global_peaks(events, timedelta(minutes=15), min_peak=7)), 0)


@tag("commands")
class AnalyzeCommandTests(TestCase):
    def _run(self, **opts):
        out = StringIO()
        call_command("analyze_notification_clusters", stdout=out, **opts)
        return out.getvalue()

    def test_runs_and_reports_reconstructed_events(self):
        user = create_maintainer_user()
        machine = create_machine()
        create_log_entry(machine=machine, created_by=user, text="one")
        create_log_entry(machine=machine, created_by=user, text="two")

        output = self._run()

        self.assertIn("RECONSTRUCTED", output)
        self.assertIn("LENS A", output)

    def test_empty_database_reports_gracefully(self):
        self.assertIn("No creation events", self._run())

    def test_rejects_non_positive_bucket(self):
        with self.assertRaises(CommandError):
            self._run(bucket=0)

    def test_rejects_malformed_since(self):
        with self.assertRaises(CommandError):
            self._run(since="not-a-date")
