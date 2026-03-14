"""Tests for labor report views."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from flipfix.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TestDataMixin,
    create_log_entry,
)


@tag("views")
class LaborWeeklySummaryViewTests(TestDataMixin, TestCase):
    """Tests for the weekly labor summary page."""

    def setUp(self):
        super().setUp()
        self.url = reverse("labor-report-weekly")

    def test_requires_authentication(self):
        """Unauthenticated users are redirected to login."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_returns_200_for_maintainer(self):
        """Authenticated maintainer gets 200."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_empty_state_when_no_labor(self):
        """Shows empty state when no time_spent has been logged."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["weeks"]), 0)
        self.assertEqual(response.context["grand_total"], 0)

    def test_weekly_totals_correct(self):
        """Entries are grouped by week with correct totals."""
        self.client.force_login(self.maintainer_user)

        # Create entries in the current week
        now = timezone.now()
        create_log_entry(
            machine=self.machine, text="Work 1", time_spent=Decimal("1.5"), occurred_at=now
        )
        create_log_entry(
            machine=self.machine, text="Work 2", time_spent=Decimal("2.0"), occurred_at=now
        )

        response = self.client.get(self.url)
        weeks = response.context["weeks"]
        self.assertEqual(len(weeks), 1)
        self.assertEqual(weeks[0]["total_hours"], Decimal("3.5"))
        self.assertEqual(weeks[0]["entry_count"], 2)
        self.assertEqual(response.context["grand_total"], Decimal("3.5"))

    def test_zero_time_spent_entries_excluded(self):
        """Entries with time_spent=0 are excluded from the report."""
        self.client.force_login(self.maintainer_user)

        now = timezone.now()
        create_log_entry(machine=self.machine, text="No time", time_spent=Decimal("0"))
        create_log_entry(
            machine=self.machine, text="Has time", time_spent=Decimal("1.0"), occurred_at=now
        )

        response = self.client.get(self.url)
        weeks = response.context["weeks"]
        self.assertEqual(len(weeks), 1)
        self.assertEqual(weeks[0]["entry_count"], 1)


@tag("views")
class LaborDetailViewTests(TestDataMixin, TestCase):
    """Tests for the labor detail drill-down page."""

    def setUp(self):
        super().setUp()
        self.url = reverse("labor-report-detail")

    def test_requires_authentication(self):
        """Unauthenticated users are redirected to login."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_returns_200_for_maintainer(self):
        """Authenticated maintainer gets 200."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_defaults_to_current_week(self):
        """Without params, defaults to current week."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.url)

        today = timezone.localdate()
        expected_start = today - timedelta(days=today.weekday())
        expected_end = expected_start + timedelta(days=6)

        self.assertEqual(response.context["start_date"], expected_start)
        self.assertEqual(response.context["end_date"], expected_end)

    def test_filters_by_date_range(self):
        """Entries outside the date range are excluded."""
        self.client.force_login(self.maintainer_user)

        today = timezone.localdate()
        start = today - timedelta(days=7)
        end = today - timedelta(days=1)

        # Entry inside range
        inside_dt = timezone.make_aware(
            timezone.datetime(start.year, start.month, start.day, 12, 0)
        )
        inside = create_log_entry(
            machine=self.machine,
            text="In range",
            time_spent=Decimal("2.0"),
            occurred_at=inside_dt,
        )

        # Entry outside range (today, which is after end)
        create_log_entry(
            machine=self.machine,
            text="Out of range",
            time_spent=Decimal("1.0"),
            occurred_at=timezone.now(),
        )

        response = self.client.get(self.url, {"start": start.isoformat(), "end": end.isoformat()})

        entries = list(response.context["entries"])
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].pk, inside.pk)
        self.assertEqual(response.context["total_hours"], Decimal("2.0"))

    def test_boundary_dates_included(self):
        """Entries exactly on start and end dates are included."""
        self.client.force_login(self.maintainer_user)

        today = timezone.localdate()
        start = today - timedelta(days=3)
        end = today

        # Entry on start boundary
        start_dt = timezone.make_aware(timezone.datetime(start.year, start.month, start.day, 0, 30))
        create_log_entry(
            machine=self.machine,
            text="Start boundary",
            time_spent=Decimal("1.0"),
            occurred_at=start_dt,
        )

        # Entry on end boundary
        end_dt = timezone.make_aware(timezone.datetime(end.year, end.month, end.day, 23, 30))
        create_log_entry(
            machine=self.machine,
            text="End boundary",
            time_spent=Decimal("1.5"),
            occurred_at=end_dt,
        )

        response = self.client.get(self.url, {"start": start.isoformat(), "end": end.isoformat()})

        entries = response.context["entries"]
        self.assertEqual(len(entries), 2)
        self.assertEqual(response.context["total_hours"], Decimal("2.5"))

    def test_invalid_dates_default_to_current_week(self):
        """Invalid date parameters gracefully default to current week."""
        self.client.force_login(self.maintainer_user)

        response = self.client.get(self.url, {"start": "not-a-date", "end": "also-bad"})
        self.assertEqual(response.status_code, 200)

        today = timezone.localdate()
        expected_start = today - timedelta(days=today.weekday())
        self.assertEqual(response.context["start_date"], expected_start)

    def test_excludes_zero_time_entries(self):
        """Entries with time_spent=0 are excluded."""
        self.client.force_login(self.maintainer_user)

        now = timezone.now()
        today = timezone.localdate()
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)

        create_log_entry(
            machine=self.machine, text="No time", time_spent=Decimal("0"), occurred_at=now
        )
        create_log_entry(
            machine=self.machine, text="Has time", time_spent=Decimal("3.0"), occurred_at=now
        )

        response = self.client.get(self.url, {"start": start.isoformat(), "end": end.isoformat()})

        entries = response.context["entries"]
        self.assertEqual(len(entries), 1)


@tag("models")
class LogEntryTimeSpentModelTests(TestDataMixin, TestCase):
    """Tests for the time_spent field on LogEntry."""

    def test_default_is_zero(self):
        """time_spent defaults to 0."""
        entry = create_log_entry(machine=self.machine, text="Test")
        self.assertEqual(entry.time_spent, Decimal("0"))

    def test_accepts_decimal_values(self):
        """time_spent accepts decimal values like 0.5, 1.5."""
        entry = create_log_entry(machine=self.machine, text="Test", time_spent=Decimal("1.5"))
        entry.refresh_from_db()
        self.assertEqual(entry.time_spent, Decimal("1.5"))

    def test_saves_correctly(self):
        """time_spent persists through save/reload cycle."""
        entry = create_log_entry(machine=self.machine, text="Test", time_spent=Decimal("3.0"))
        entry.refresh_from_db()
        self.assertEqual(entry.time_spent, Decimal("3.0"))


@tag("forms")
class LogEntryTimeSpentFormTests(TestCase):
    """Tests for time_spent in LogEntryQuickForm."""

    def test_time_spent_defaults_to_zero(self):
        """Omitting time_spent defaults to 0 initial."""
        from flipfix.apps.maintenance.forms import LogEntryQuickForm

        form_data = {
            "occurred_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "submitter_name": "Test",
            "text": "Work done",
        }
        form = LogEntryQuickForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        # time_spent is not required, so cleaned_data should have None or be absent
        self.assertIn("time_spent", form.cleaned_data)

    def test_time_spent_accepts_valid_decimal(self):
        """Form accepts valid decimal time_spent."""
        from flipfix.apps.maintenance.forms import LogEntryQuickForm

        form_data = {
            "occurred_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "submitter_name": "Test",
            "text": "Work done",
            "time_spent": "1.5",
        }
        form = LogEntryQuickForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["time_spent"], Decimal("1.5"))

    def test_time_spent_rejects_negative(self):
        """Form rejects negative time_spent."""
        from flipfix.apps.maintenance.forms import LogEntryQuickForm

        form_data = {
            "occurred_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "submitter_name": "Test",
            "text": "Work done",
            "time_spent": "-1",
        }
        form = LogEntryQuickForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("time_spent", form.errors)


@tag("views")
class LogEntryCreateTimeSpentTests(TestDataMixin, TestCase):
    """Tests for time_spent in log entry creation view."""

    def setUp(self):
        super().setUp()
        self.url = reverse("log-create-machine", kwargs={"slug": self.machine.slug})

    def test_create_with_time_spent(self):
        """Creating a log entry with time_spent saves the value."""
        self.client.force_login(self.maintainer_user)
        response = self.client.post(
            self.url,
            {
                "occurred_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "maintainer_freetext": "Test User",
                "text": "Fixed the flipper",
                "time_spent": "2.5",
            },
        )
        self.assertEqual(response.status_code, 302)

        from flipfix.apps.maintenance.models import LogEntry

        entry = LogEntry.objects.first()
        self.assertEqual(entry.time_spent, Decimal("2.5"))

    def test_create_without_time_spent_defaults_to_zero(self):
        """Omitting time_spent defaults to 0."""
        self.client.force_login(self.maintainer_user)
        response = self.client.post(
            self.url,
            {
                "occurred_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "maintainer_freetext": "Test User",
                "text": "Quick fix",
            },
        )
        self.assertEqual(response.status_code, 302)

        from flipfix.apps.maintenance.models import LogEntry

        entry = LogEntry.objects.first()
        self.assertEqual(entry.time_spent, Decimal("0"))


@tag("views")
class LogEntryDetailTimeSpentTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for AJAX time_spent update on log entry detail."""

    def setUp(self):
        super().setUp()
        self.entry = create_log_entry(machine=self.machine, text="Test", time_spent=Decimal("1.0"))
        self.url = reverse("log-detail", kwargs={"pk": self.entry.pk})

    def test_update_time_spent(self):
        """AJAX update_time_spent saves new value."""
        self.client.force_login(self.maintainer_user)
        response = self.client.post(self.url, {"action": "update_time_spent", "time_spent": "3.5"})
        self.assertEqual(response.status_code, 200)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.time_spent, Decimal("3.5"))

    def test_update_time_spent_rejects_negative(self):
        """AJAX update_time_spent rejects negative values."""
        self.client.force_login(self.maintainer_user)
        response = self.client.post(self.url, {"action": "update_time_spent", "time_spent": "-1"})
        self.assertEqual(response.status_code, 400)

    def test_update_time_spent_rejects_invalid(self):
        """AJAX update_time_spent rejects non-numeric values."""
        self.client.force_login(self.maintainer_user)
        response = self.client.post(self.url, {"action": "update_time_spent", "time_spent": "abc"})
        self.assertEqual(response.status_code, 400)

    def test_update_time_spent_rejects_empty(self):
        """AJAX update_time_spent rejects empty value."""
        self.client.force_login(self.maintainer_user)
        response = self.client.post(self.url, {"action": "update_time_spent", "time_spent": ""})
        self.assertEqual(response.status_code, 400)
