"""Tests for the one-time log-entry de-duplication logic."""

from __future__ import annotations

from datetime import timedelta

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, tag
from django.utils import timezone

from flipfix.apps.accounts.models import Maintainer
from flipfix.apps.catalog.models import MachineInstance
from flipfix.apps.core.models import RecordReference
from flipfix.apps.core.test_utils import (
    TemporaryMediaMixin,
    TestDataMixin,
    create_maintainer_user,
    create_uploaded_image,
)
from flipfix.apps.maintenance.deduplication import deduplicate_log_entries
from flipfix.apps.maintenance.models import LogEntry, LogEntryMedia


def _run():
    """Run the de-duplication against the real models, silencing the summary."""
    return deduplicate_log_entries(apps, log=lambda message: None)


def _make_entry(machine, user, text, created_at, **kwargs):
    """Create a LogEntry, then force its auto_now_add created_at to a fixed time."""
    entry = LogEntry.objects.create(
        machine=machine,
        text=text,
        occurred_at=created_at,
        created_by=user,
        **kwargs,
    )
    LogEntry.objects.filter(pk=entry.pk).update(created_at=created_at)
    entry.refresh_from_db()
    return entry


@tag("models")
class DeduplicateLogEntriesTests(TemporaryMediaMixin, TestDataMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.user = self.maintainer_user
        self.base = timezone.now() - timedelta(days=1)

    def test_collapses_a_retry_burst_to_the_earliest_entry(self):
        """Two identical entries seconds apart collapse onto the earlier one."""
        survivor = _make_entry(self.machine, self.user, "Fixed flippers", self.base)
        loser = _make_entry(
            self.machine, self.user, "Fixed flippers", self.base + timedelta(seconds=30)
        )

        result = _run()

        self.assertEqual(result["clusters"], 1)
        self.assertEqual(result["deleted"], 1)
        self.assertTrue(LogEntry.objects.filter(pk=survivor.pk).exists())
        self.assertFalse(LogEntry.objects.filter(pk=loser.pk).exists())

    def test_entries_outside_the_window_are_kept(self):
        """Identical entries more than the window apart are not duplicates."""
        _make_entry(self.machine, self.user, "Fixed flippers", self.base)
        _make_entry(self.machine, self.user, "Fixed flippers", self.base + timedelta(minutes=10))

        result = _run()

        self.assertEqual(result["clusters"], 0)
        self.assertEqual(LogEntry.objects.count(), 2)

    def test_chain_is_anchored_to_the_first_entry_not_the_previous(self):
        """A chain of near-matches cannot snowball past the window and eat a real entry."""
        # Gaps of 90s each: 0s and 90s cluster (both within 2min of the first),
        # but 180s is >2min from the first, so it stays its own kept entry.
        _make_entry(self.machine, self.user, "Fixed flippers", self.base)
        _make_entry(self.machine, self.user, "Fixed flippers", self.base + timedelta(seconds=90))
        _make_entry(self.machine, self.user, "Fixed flippers", self.base + timedelta(seconds=180))

        result = _run()

        self.assertEqual(result["deleted"], 1)
        self.assertEqual(LogEntry.objects.count(), 2)

    def test_different_text_is_not_a_duplicate(self):
        """Entries with different text are never merged."""
        _make_entry(self.machine, self.user, "Fixed flippers", self.base)
        _make_entry(self.machine, self.user, "Replaced a bulb", self.base + timedelta(seconds=30))

        _run()

        self.assertEqual(LogEntry.objects.count(), 2)

    def test_different_author_is_not_a_duplicate(self):
        """Two people logging the same text concurrently both keep their entries."""
        other = create_maintainer_user(username="other", first_name="Other", last_name="Person")
        _make_entry(self.machine, self.user, "Fixed flippers", self.base)
        _make_entry(self.machine, other, "Fixed flippers", self.base + timedelta(seconds=30))

        _run()

        self.assertEqual(LogEntry.objects.count(), 2)

    def test_media_is_repointed_to_the_survivor(self):
        """A loser's media moves to the survivor rather than being deleted."""
        survivor = _make_entry(self.machine, self.user, "Fixed flippers", self.base)
        loser = _make_entry(
            self.machine, self.user, "Fixed flippers", self.base + timedelta(seconds=30)
        )
        media = LogEntryMedia.objects.create(
            log_entry=loser,
            media_type=LogEntryMedia.MediaType.PHOTO,
            file=SimpleUploadedFile(
                "photo.jpg", create_uploaded_image().read(), content_type="image/jpeg"
            ),
        )

        result = _run()

        self.assertEqual(result["media_repointed"], 1)
        media.refresh_from_db()
        self.assertEqual(media.log_entry_id, survivor.pk)

    def test_maintainers_are_unioned_onto_the_survivor(self):
        """A loser's maintainers are added to the survivor before deletion."""
        survivor = _make_entry(self.machine, self.user, "Fixed flippers", self.base)
        loser = _make_entry(
            self.machine, self.user, "Fixed flippers", self.base + timedelta(seconds=30)
        )
        extra = Maintainer.objects.get(user=create_maintainer_user(username="helper"))
        loser.maintainers.add(extra)

        _run()

        self.assertIn(extra, survivor.maintainers.all())

    def test_loser_references_are_pruned(self):
        """A loser's markdown-link references are removed, not left orphaned."""
        survivor = _make_entry(self.machine, self.user, "Fixed flippers", self.base)
        loser = _make_entry(
            self.machine, self.user, "Fixed flippers", self.base + timedelta(seconds=30)
        )
        logentry_ct = ContentType.objects.get_for_model(LogEntry)
        machine_ct = ContentType.objects.get_for_model(MachineInstance)
        RecordReference.objects.create(
            source_type=logentry_ct,
            source_id=loser.pk,
            target_type=machine_ct,
            target_id=self.machine.pk,
        )

        _run()

        self.assertFalse(
            RecordReference.objects.filter(source_type=logentry_ct, source_id=loser.pk).exists()
        )
        self.assertTrue(LogEntry.objects.filter(pk=survivor.pk).exists())

    def test_inbound_references_to_a_loser_are_pruned(self):
        """A backlink pointing at a collapsed duplicate is removed, not left dangling."""
        survivor = _make_entry(self.machine, self.user, "Fixed flippers", self.base)
        loser = _make_entry(
            self.machine, self.user, "Fixed flippers", self.base + timedelta(seconds=30)
        )
        logentry_ct = ContentType.objects.get_for_model(LogEntry)
        # A separate entry links TO the loser (the loser is the reference target).
        source = _make_entry(self.machine, self.user, f"See [[log:{loser.pk}]]", self.base)
        RecordReference.objects.create(
            source_type=logentry_ct,
            source_id=source.pk,
            target_type=logentry_ct,
            target_id=loser.pk,
        )

        _run()

        self.assertFalse(
            RecordReference.objects.filter(target_type=logentry_ct, target_id=loser.pk).exists()
        )
        self.assertTrue(LogEntry.objects.filter(pk=survivor.pk).exists())
        self.assertTrue(LogEntry.objects.filter(pk=source.pk).exists())
