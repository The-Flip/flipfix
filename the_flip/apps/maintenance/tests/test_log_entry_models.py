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
class LogEntryWorkDateTests(TestDataMixin, TestCase):
    """Tests for LogEntry work_date field."""

    def test_work_date_defaults_to_now(self):
        """Work date defaults to current time when not specified."""
        before = timezone.now()
        log_entry = create_log_entry(machine=self.machine, text="Test entry")
        after = timezone.now()

        self.assertIsNotNone(log_entry.work_date)
        self.assertGreaterEqual(log_entry.work_date, before)
        self.assertLessEqual(log_entry.work_date, after)

    def test_work_date_can_be_set_explicitly(self):
        """Work date can be set to a specific datetime."""
        specific_date = timezone.now() - timedelta(days=5)
        log_entry = create_log_entry(
            machine=self.machine, text="Historical entry", work_date=specific_date
        )
        self.assertEqual(log_entry.work_date, specific_date)

    def test_log_entries_ordered_by_work_date_descending(self):
        """Log entries are ordered by work_date descending by default."""
        old_entry = create_log_entry(
            machine=self.machine,
            text="Old entry",
            work_date=timezone.now() - timedelta(days=10),
        )
        new_entry = create_log_entry(
            machine=self.machine, text="New entry", work_date=timezone.now()
        )

        entries = list(LogEntry.objects.all())
        self.assertEqual(entries[0], new_entry)
        self.assertEqual(entries[1], old_entry)


@tag("forms")
class LogEntryQuickFormWorkDateTests(TestCase):
    """Tests for LogEntryQuickForm work_date validation."""

    def test_form_valid_with_past_date(self):
        """Form accepts past dates."""
        past_date = timezone.now() - timedelta(days=5)
        form_data = {
            "work_date": past_date.strftime(DATETIME_INPUT_FORMAT),
            "submitter_name": "Test User",
            "text": "Test description",
        }
        form = LogEntryQuickForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_valid_with_today(self):
        """Form accepts today's date."""
        today = timezone.localtime().replace(hour=12, minute=0, second=0, microsecond=0)
        form_data = {
            "work_date": today.strftime(DATETIME_INPUT_FORMAT),
            "submitter_name": "Test User",
            "text": "Test description",
        }
        form = LogEntryQuickForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_invalid_with_future_date(self):
        """Form rejects future dates with validation error."""
        future_date = timezone.now() + timedelta(days=5)
        form_data = {
            "work_date": future_date.strftime(DATETIME_INPUT_FORMAT),
            "submitter_name": "Test User",
            "text": "Test description",
        }
        form = LogEntryQuickForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("work_date", form.errors)
        self.assertIn("future", form.errors["work_date"][0].lower())
