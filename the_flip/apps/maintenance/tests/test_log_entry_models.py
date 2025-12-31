"""Tests for LogEntry model and form behavior."""

from datetime import timedelta

from django.test import TestCase, tag
from django.utils import timezone

from the_flip.apps.core.test_utils import (
    DATETIME_INPUT_FORMAT,
    TestDataMixin,
    create_log_entry,
)
from the_flip.apps.maintenance.forms import LogEntryQuickForm
from the_flip.apps.maintenance.models import LogEntry


@tag("models")
class LogEntryOccurredAtTests(TestDataMixin, TestCase):
    """Tests for LogEntry occurred_at field."""

    def test_occurred_at_defaults_to_now(self):
        """occurred_at defaults to current time when not specified."""
        before = timezone.now()
        log_entry = create_log_entry(machine=self.machine, text="Test entry")
        after = timezone.now()

        self.assertIsNotNone(log_entry.occurred_at)
        self.assertGreaterEqual(log_entry.occurred_at, before)
        self.assertLessEqual(log_entry.occurred_at, after)

    def test_occurred_at_can_be_set_explicitly(self):
        """occurred_at can be set to a specific datetime."""
        specific_date = timezone.now() - timedelta(days=5)
        log_entry = create_log_entry(
            machine=self.machine, text="Historical entry", occurred_at=specific_date
        )
        self.assertEqual(log_entry.occurred_at, specific_date)

    def test_log_entries_ordered_by_occurred_at_descending(self):
        """Log entries are ordered by occurred_at descending by default.

        Creates records where created_at order differs from occurred_at order
        to ensure we're actually sorting by occurred_at, not created_at.
        """
        now = timezone.now()

        # Create in this order: middle, oldest, newest
        # If sorting by created_at, we'd get: middle, oldest, newest
        # If sorting by occurred_at desc, we should get: newest, middle, oldest
        middle = create_log_entry(
            machine=self.machine,
            text="Middle entry",
            occurred_at=now - timedelta(days=5),
        )
        oldest = create_log_entry(
            machine=self.machine,
            text="Oldest entry",
            occurred_at=now - timedelta(days=10),
        )
        newest = create_log_entry(
            machine=self.machine,
            text="Newest entry",
            occurred_at=now,
        )

        entries = list(LogEntry.objects.all())
        self.assertEqual(entries, [newest, middle, oldest])


@tag("forms")
class LogEntryQuickFormOccurredAtTests(TestCase):
    """Tests for LogEntryQuickForm occurred_at validation."""

    def test_form_valid_with_past_date(self):
        """Form accepts past dates."""
        past_date = timezone.now() - timedelta(days=5)
        form_data = {
            "occurred_at": past_date.strftime(DATETIME_INPUT_FORMAT),
            "submitter_name": "Test User",
            "text": "Test description",
        }
        form = LogEntryQuickForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_valid_with_today(self):
        """Form accepts today's date."""
        today = timezone.localtime().replace(hour=12, minute=0, second=0, microsecond=0)
        form_data = {
            "occurred_at": today.strftime(DATETIME_INPUT_FORMAT),
            "submitter_name": "Test User",
            "text": "Test description",
        }
        form = LogEntryQuickForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_invalid_with_future_date(self):
        """Form rejects future dates with validation error."""
        future_date = timezone.now() + timedelta(days=5)
        form_data = {
            "occurred_at": future_date.strftime(DATETIME_INPUT_FORMAT),
            "submitter_name": "Test User",
            "text": "Test description",
        }
        form = LogEntryQuickForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("occurred_at", form.errors)
        self.assertIn("future", form.errors["occurred_at"][0].lower())
