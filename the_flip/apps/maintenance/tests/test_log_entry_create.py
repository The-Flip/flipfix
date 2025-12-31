"""Tests for log entry creation views."""

from datetime import timedelta

from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.core.test_utils import (
    DATETIME_DISPLAY_FORMAT,
    DATETIME_INPUT_FORMAT,
    TestDataMixin,
    create_maintainer_user,
    create_problem_report,
)
from the_flip.apps.maintenance.models import LogEntry, ProblemReport


@tag("views")
class MachineLogCreateViewOccurredAtTests(TestDataMixin, TestCase):
    """Tests for MachineLogCreateView occurred_at handling."""

    def setUp(self):
        super().setUp()
        self.create_url = reverse("log-create-machine", kwargs={"slug": self.machine.slug})

    def test_create_log_entry_with_occurred_at(self):
        """Creating a log entry saves the specified occurred_at."""
        self.client.force_login(self.maintainer_user)

        occurred_at = timezone.now() - timedelta(days=3)
        response = self.client.post(
            self.create_url,
            {
                "occurred_at": occurred_at.strftime(DATETIME_INPUT_FORMAT),
                "submitter_name": "Test User",
                "text": "Work performed three days ago",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(LogEntry.objects.count(), 1)

        log_entry = LogEntry.objects.first()
        self.assertEqual(
            log_entry.occurred_at.strftime(DATETIME_DISPLAY_FORMAT),
            occurred_at.strftime(DATETIME_DISPLAY_FORMAT),
        )

    def test_create_log_entry_rejects_future_date(self):
        """View rejects log entries with future occurred_at dates."""
        self.client.force_login(self.maintainer_user)

        future_date = timezone.now() + timedelta(days=5)
        response = self.client.post(
            self.create_url,
            {
                "occurred_at": future_date.strftime(DATETIME_INPUT_FORMAT),
                "submitter_name": "Test User",
                "text": "Future work",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(LogEntry.objects.count(), 0)


@tag("views")
class LogEntryCreatedByTests(TestDataMixin, TestCase):
    """Tests for LogEntry created_by field via view."""

    def setUp(self):
        super().setUp()
        self.create_url = reverse("log-create-machine", kwargs={"slug": self.machine.slug})

    def test_created_by_set_when_creating_log_entry(self):
        """Creating a log entry should set the created_by field."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.create_url,
            {
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "submitter_name": "Some Other Person",
                "text": "Work performed",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(LogEntry.objects.count(), 1)

        log_entry = LogEntry.objects.first()
        self.assertEqual(log_entry.created_by, self.maintainer_user)

    def test_created_by_can_differ_from_maintainer(self):
        """created_by (who entered data) can differ from maintainers (who did work)."""
        work_doer = create_maintainer_user(username="workdoer", first_name="Work", last_name="Doer")

        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.create_url,
            {
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "submitter_name": "Work Doer",
                "text": "Work performed by someone else",
            },
        )

        self.assertEqual(response.status_code, 302)
        log_entry = LogEntry.objects.first()

        self.assertEqual(log_entry.created_by, self.maintainer_user)
        self.assertIn(Maintainer.objects.get(user=work_doer), log_entry.maintainers.all())


@tag("views")
class LogEntryProblemReportTests(TestDataMixin, TestCase):
    """Tests for creating log entries from problem reports."""

    def setUp(self):
        super().setUp()
        self.problem_report = create_problem_report(
            machine=self.machine,
            problem_type=ProblemReport.ProblemType.STUCK_BALL,
            description="Ball stuck in the playfield",
        )
        self.create_url = reverse(
            "log-create-problem-report", kwargs={"pk": self.problem_report.pk}
        )

    def test_create_view_accessible_to_staff(self):
        """Staff users should be able to access the log entry create form from problem report."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.create_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "maintenance/log_entry_new.html")

    def test_create_view_shows_problem_report_context(self):
        """Create form should show the problem report context."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.create_url)

        # Sidebar shows "Problem" label with linked problem card
        self.assertContains(response, "sidebar-card--problem")
        self.assertContains(response, self.machine.name)

    def test_create_log_entry_inherits_machine_from_problem_report(self):
        """Log entry created from problem report should inherit the machine."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.create_url,
            {
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "submitter_name": "Test User",
                "text": "Investigated the stuck ball issue",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(LogEntry.objects.count(), 1)

        log_entry = LogEntry.objects.first()
        self.assertEqual(log_entry.machine, self.machine)

    def test_create_log_entry_links_to_problem_report(self):
        """Log entry created from problem report should be linked to the problem report."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.create_url,
            {
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "submitter_name": "Test User",
                "text": "Fixed the stuck ball",
            },
        )

        self.assertEqual(response.status_code, 302)
        log_entry = LogEntry.objects.first()
        self.assertEqual(log_entry.problem_report, self.problem_report)

    def test_create_log_entry_redirects_to_problem_report(self):
        """After creating log entry from problem report, should redirect back to problem report."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.create_url,
            {
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "submitter_name": "Test User",
                "text": "Fixed the issue",
            },
        )

        expected_url = reverse("problem-report-detail", kwargs={"pk": self.problem_report.pk})
        self.assertRedirects(response, expected_url)

    def test_regular_log_entry_has_no_problem_report(self):
        """Log entries created from machine context should not have a problem_report."""
        self.client.force_login(self.maintainer_user)
        regular_url = reverse("log-create-machine", kwargs={"slug": self.machine.slug})

        response = self.client.post(
            regular_url,
            {
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "submitter_name": "Test User",
                "text": "Regular maintenance",
            },
        )

        self.assertEqual(response.status_code, 302)
        log_entry = LogEntry.objects.first()
        self.assertIsNone(log_entry.problem_report)

    def test_close_problem_checkbox_closes_problem_report(self):
        """Checking 'close the problem report' should close it when creating log entry."""
        self.client.force_login(self.maintainer_user)
        self.assertEqual(self.problem_report.status, ProblemReport.Status.OPEN)

        response = self.client.post(
            self.create_url,
            {
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "submitter_name": "Test User",
                "text": "Fixed the stuck ball",
                "close_problem": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.problem_report.refresh_from_db()
        self.assertEqual(self.problem_report.status, ProblemReport.Status.CLOSED)

    def test_without_close_problem_checkbox_leaves_problem_open(self):
        """Not checking 'close the problem report' should leave it open."""
        self.client.force_login(self.maintainer_user)
        self.assertEqual(self.problem_report.status, ProblemReport.Status.OPEN)

        response = self.client.post(
            self.create_url,
            {
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "submitter_name": "Test User",
                "text": "Investigated the issue",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.problem_report.refresh_from_db()
        self.assertEqual(self.problem_report.status, ProblemReport.Status.OPEN)
