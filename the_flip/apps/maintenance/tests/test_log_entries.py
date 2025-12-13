"""Tests for log entry views and functionality."""

from datetime import timedelta

from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TestDataMixin,
    create_log_entry,
    create_maintainer_user,
    create_problem_report,
)
from the_flip.apps.maintenance.forms import LogEntryQuickForm
from the_flip.apps.maintenance.models import LogEntry, ProblemReport


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
            "work_date": past_date.strftime("%Y-%m-%dT%H:%M"),
            "submitter_name": "Test User",
            "text": "Test description",
        }
        form = LogEntryQuickForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_valid_with_today(self):
        """Form accepts today's date."""
        today = timezone.localtime().replace(hour=12, minute=0, second=0, microsecond=0)
        form_data = {
            "work_date": today.strftime("%Y-%m-%dT%H:%M"),
            "submitter_name": "Test User",
            "text": "Test description",
        }
        form = LogEntryQuickForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_invalid_with_future_date(self):
        """Form rejects future dates with validation error."""
        future_date = timezone.now() + timedelta(days=5)
        form_data = {
            "work_date": future_date.strftime("%Y-%m-%dT%H:%M"),
            "submitter_name": "Test User",
            "text": "Test description",
        }
        form = LogEntryQuickForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("work_date", form.errors)
        self.assertIn("future", form.errors["work_date"][0].lower())


@tag("views")
class MachineLogCreateViewWorkDateTests(TestDataMixin, TestCase):
    """Tests for MachineLogCreateView work_date handling."""

    def setUp(self):
        super().setUp()
        self.create_url = reverse("log-create-machine", kwargs={"slug": self.machine.slug})

    def test_create_log_entry_with_work_date(self):
        """Creating a log entry saves the specified work_date."""
        self.client.force_login(self.staff_user)

        work_date = timezone.now() - timedelta(days=3)
        response = self.client.post(
            self.create_url,
            {
                "work_date": work_date.strftime("%Y-%m-%dT%H:%M"),
                "submitter_name": "Test User",
                "text": "Work performed three days ago",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(LogEntry.objects.count(), 1)

        log_entry = LogEntry.objects.first()
        self.assertEqual(
            log_entry.work_date.strftime("%Y-%m-%d %H:%M"),
            work_date.strftime("%Y-%m-%d %H:%M"),
        )

    def test_create_log_entry_rejects_future_date(self):
        """View rejects log entries with future work dates."""
        self.client.force_login(self.staff_user)

        future_date = timezone.now() + timedelta(days=5)
        response = self.client.post(
            self.create_url,
            {
                "work_date": future_date.strftime("%Y-%m-%dT%H:%M"),
                "submitter_name": "Test User",
                "text": "Future work",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(LogEntry.objects.count(), 0)


@tag("views", "ajax")
class LogEntryDetailViewWorkDateTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for LogEntryDetailView AJAX work_date updates."""

    def setUp(self):
        super().setUp()
        self.log_entry = create_log_entry(machine=self.machine, text="Test entry")
        self.detail_url = reverse("log-detail", kwargs={"pk": self.log_entry.pk})

    def test_update_work_date_ajax(self):
        """AJAX endpoint updates work_date successfully."""
        self.client.force_login(self.staff_user)

        new_date = timezone.now() - timedelta(days=7)
        response = self.client.post(
            self.detail_url,
            {
                "action": "update_work_date",
                "work_date": new_date.strftime("%Y-%m-%dT%H:%M"),
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["success"])

        self.log_entry.refresh_from_db()
        self.assertEqual(
            self.log_entry.work_date.strftime("%Y-%m-%d %H:%M"),
            new_date.strftime("%Y-%m-%d %H:%M"),
        )

    def test_update_work_date_rejects_future(self):
        """AJAX endpoint rejects future dates."""
        self.client.force_login(self.staff_user)

        future_date = timezone.now() + timedelta(days=5)
        response = self.client.post(
            self.detail_url,
            {
                "action": "update_work_date",
                "work_date": future_date.strftime("%Y-%m-%dT%H:%M"),
            },
        )

        self.assertEqual(response.status_code, 400)
        result = response.json()
        self.assertFalse(result["success"])
        self.assertIn("future", result["error"].lower())

    def test_update_work_date_rejects_invalid_format(self):
        """AJAX endpoint rejects invalid date formats."""
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.detail_url,
            {"action": "update_work_date", "work_date": "not-a-valid-date"},
        )

        self.assertEqual(response.status_code, 400)
        result = response.json()
        self.assertFalse(result["success"])
        self.assertIn("Invalid date format", result["error"])

    def test_update_work_date_rejects_empty(self):
        """AJAX endpoint rejects empty date values."""
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.detail_url, {"action": "update_work_date", "work_date": ""}
        )

        self.assertEqual(response.status_code, 400)
        result = response.json()
        self.assertFalse(result["success"])


@tag("views", "ajax")
class LogEntryDetailViewTextUpdateTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for LogEntryDetailView AJAX text updates."""

    def setUp(self):
        super().setUp()
        self.log_entry = create_log_entry(machine=self.machine, text="Original text")
        self.detail_url = reverse("log-detail", kwargs={"pk": self.log_entry.pk})

    def test_update_text_success(self):
        """AJAX endpoint updates text successfully."""
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.detail_url,
            {"action": "update_text", "text": "Updated description"},
        )

        self.assertEqual(response.status_code, 200)
        self.log_entry.refresh_from_db()
        self.assertEqual(self.log_entry.text, "Updated description")

    def test_update_text_empty(self):
        """AJAX endpoint allows empty text."""
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.detail_url,
            {"action": "update_text", "text": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.log_entry.refresh_from_db()
        self.assertEqual(self.log_entry.text, "")

    def test_update_text_requires_auth(self):
        """AJAX endpoint requires authentication."""
        response = self.client.post(
            self.detail_url,
            {"action": "update_text", "text": "Should fail"},
        )

        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_update_text_requires_maintainer(self):
        """AJAX endpoint requires maintainer access."""
        self.client.force_login(self.regular_user)

        response = self.client.post(
            self.detail_url,
            {"action": "update_text", "text": "Should fail"},
        )

        self.assertEqual(response.status_code, 403)


@tag("views")
class LogEntryProblemReportUpdateTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for updating the problem report of a log entry via AJAX."""

    def setUp(self):
        super().setUp()
        from the_flip.apps.core.test_utils import create_machine

        self.other_machine = create_machine(slug="other-machine")
        self.problem_report = create_problem_report(
            machine=self.machine,
            description="Original problem",
        )
        self.other_problem_report = create_problem_report(
            machine=self.other_machine,
            description="Other problem",
        )
        self.log_entry = create_log_entry(
            machine=self.machine,
            problem_report=self.problem_report,
            text="Linked log entry",
        )
        self.detail_url = reverse("log-detail", kwargs={"pk": self.log_entry.pk})

    def test_update_problem_report_success(self):
        """Successfully update log entry's problem report."""
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.detail_url,
            {
                "action": "update_problem_report",
                "problem_report_id": str(self.other_problem_report.pk),
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["success"])

        self.log_entry.refresh_from_db()
        self.assertEqual(self.log_entry.problem_report, self.other_problem_report)

    def test_update_problem_report_changes_machine(self):
        """Updating problem report also changes the machine to match."""
        self.client.force_login(self.staff_user)

        self.client.post(
            self.detail_url,
            {
                "action": "update_problem_report",
                "problem_report_id": str(self.other_problem_report.pk),
            },
        )

        self.log_entry.refresh_from_db()
        self.assertEqual(self.log_entry.machine, self.other_machine)

    def test_unlink_from_problem_report(self):
        """Setting problem_report_id to 'none' unlinks the log entry."""
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.detail_url,
            {
                "action": "update_problem_report",
                "problem_report_id": "none",
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["success"])

        self.log_entry.refresh_from_db()
        self.assertIsNone(self.log_entry.problem_report)
        # Machine should remain the same
        self.assertEqual(self.log_entry.machine, self.machine)

    def test_link_orphan_to_problem_report(self):
        """An orphan log entry can be linked to a problem report."""
        orphan_entry = create_log_entry(
            machine=self.machine,
            text="Orphan log entry",
        )
        detail_url = reverse("log-detail", kwargs={"pk": orphan_entry.pk})

        self.client.force_login(self.staff_user)
        response = self.client.post(
            detail_url,
            {
                "action": "update_problem_report",
                "problem_report_id": str(self.other_problem_report.pk),
            },
        )

        self.assertEqual(response.status_code, 200)
        orphan_entry.refresh_from_db()
        self.assertEqual(orphan_entry.problem_report, self.other_problem_report)
        self.assertEqual(orphan_entry.machine, self.other_machine)

    def test_update_problem_report_noop_when_same(self):
        """Selecting the same problem report returns noop status."""
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.detail_url,
            {
                "action": "update_problem_report",
                "problem_report_id": str(self.problem_report.pk),
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "noop")

    def test_update_problem_report_invalid_id(self):
        """Invalid problem report ID returns 404 error."""
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.detail_url,
            {
                "action": "update_problem_report",
                "problem_report_id": "99999",
            },
        )

        self.assertEqual(response.status_code, 404)
        result = response.json()
        self.assertFalse(result["success"])

    def test_update_problem_report_requires_maintainer_permission(self):
        """Regular users (non-maintainers) cannot update problem report."""
        self.client.force_login(self.regular_user)

        response = self.client.post(
            self.detail_url,
            {
                "action": "update_problem_report",
                "problem_report_id": str(self.other_problem_report.pk),
            },
        )

        self.assertEqual(response.status_code, 403)


@tag("views")
class LogEntryMachineUpdateTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for updating the machine of an orphan log entry via AJAX."""

    def setUp(self):
        super().setUp()
        from the_flip.apps.core.test_utils import create_machine

        self.other_machine = create_machine(slug="other-machine")
        self.orphan_entry = create_log_entry(
            machine=self.machine,
            text="Orphan log entry",
        )
        self.detail_url = reverse("log-detail", kwargs={"pk": self.orphan_entry.pk})

    def test_update_machine_success(self):
        """Successfully update orphan log entry's machine."""
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.detail_url,
            {
                "action": "update_machine",
                "machine_slug": self.other_machine.slug,
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["success"])

        self.orphan_entry.refresh_from_db()
        self.assertEqual(self.orphan_entry.machine, self.other_machine)

    def test_update_machine_noop_when_same(self):
        """Selecting the same machine returns noop status."""
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.detail_url,
            {
                "action": "update_machine",
                "machine_slug": self.machine.slug,
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "noop")

    def test_update_machine_invalid_slug(self):
        """Invalid machine slug returns 404 error."""
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.detail_url,
            {
                "action": "update_machine",
                "machine_slug": "nonexistent-machine",
            },
        )

        self.assertEqual(response.status_code, 404)
        result = response.json()
        self.assertFalse(result["success"])

    def test_update_machine_rejected_for_linked_entry(self):
        """Updating machine directly on a linked log entry returns error."""
        linked_entry = create_log_entry(
            machine=self.machine,
            problem_report=create_problem_report(machine=self.machine),
            text="Linked log entry",
        )
        detail_url = reverse("log-detail", kwargs={"pk": linked_entry.pk})

        self.client.force_login(self.staff_user)
        response = self.client.post(
            detail_url,
            {
                "action": "update_machine",
                "machine_slug": self.other_machine.slug,
            },
        )

        self.assertEqual(response.status_code, 400)
        result = response.json()
        self.assertFalse(result["success"])
        self.assertIn("problem report", result["error"].lower())

    def test_update_machine_requires_maintainer_permission(self):
        """Regular users (non-maintainers) cannot update machine."""
        self.client.force_login(self.regular_user)

        response = self.client.post(
            self.detail_url,
            {
                "action": "update_machine",
                "machine_slug": self.other_machine.slug,
            },
        )

        self.assertEqual(response.status_code, 403)


@tag("models")
class LogEntryCreatedByTests(TestDataMixin, TestCase):
    """Tests for LogEntry created_by field."""

    def setUp(self):
        super().setUp()
        self.create_url = reverse("log-create-machine", kwargs={"slug": self.machine.slug})

    def test_created_by_set_when_creating_log_entry(self):
        """Creating a log entry should set the created_by field."""
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.create_url,
            {
                "work_date": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "submitter_name": "Some Other Person",
                "text": "Work performed",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(LogEntry.objects.count(), 1)

        log_entry = LogEntry.objects.first()
        self.assertEqual(log_entry.created_by, self.staff_user)

    def test_created_by_can_differ_from_maintainer(self):
        """created_by (who entered data) can differ from maintainers (who did work)."""
        work_doer = create_maintainer_user(username="workdoer", first_name="Work", last_name="Doer")

        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.create_url,
            {
                "work_date": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "submitter_name": "Work Doer",
                "text": "Work performed by someone else",
            },
        )

        self.assertEqual(response.status_code, 302)
        log_entry = LogEntry.objects.first()

        self.assertEqual(log_entry.created_by, self.staff_user)
        self.assertIn(Maintainer.objects.get(user=work_doer), log_entry.maintainers.all())


@tag("views")
class LogEntryProblemReportTests(TestDataMixin, TestCase):
    """Tests for creating log entries from problem reports."""

    def setUp(self):
        super().setUp()
        self.problem_report = create_problem_report(
            machine=self.machine,
            problem_type=ProblemReport.PROBLEM_STUCK_BALL,
            description="Ball stuck in the playfield",
        )
        self.create_url = reverse(
            "log-create-problem-report", kwargs={"pk": self.problem_report.pk}
        )

    def test_create_view_accessible_to_staff(self):
        """Staff users should be able to access the log entry create form from problem report."""
        self.client.force_login(self.staff_user)
        response = self.client.get(self.create_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "maintenance/log_entry_new.html")

    def test_create_view_shows_problem_report_context(self):
        """Create form should show the problem report context."""
        self.client.force_login(self.staff_user)
        response = self.client.get(self.create_url)

        # Sidebar shows "Problem" label with linked problem card
        self.assertContains(response, "sidebar-card--problem")
        self.assertContains(response, self.machine.display_name)

    def test_create_log_entry_inherits_machine_from_problem_report(self):
        """Log entry created from problem report should inherit the machine."""
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.create_url,
            {
                "work_date": timezone.now().strftime("%Y-%m-%dT%H:%M"),
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
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.create_url,
            {
                "work_date": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "submitter_name": "Test User",
                "text": "Fixed the stuck ball",
            },
        )

        self.assertEqual(response.status_code, 302)
        log_entry = LogEntry.objects.first()
        self.assertEqual(log_entry.problem_report, self.problem_report)

    def test_create_log_entry_redirects_to_problem_report(self):
        """After creating log entry from problem report, should redirect back to problem report."""
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.create_url,
            {
                "work_date": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "submitter_name": "Test User",
                "text": "Fixed the issue",
            },
        )

        expected_url = reverse("problem-report-detail", kwargs={"pk": self.problem_report.pk})
        self.assertRedirects(response, expected_url)

    def test_regular_log_entry_has_no_problem_report(self):
        """Log entries created from machine context should not have a problem_report."""
        self.client.force_login(self.staff_user)
        regular_url = reverse("log-create-machine", kwargs={"slug": self.machine.slug})

        response = self.client.post(
            regular_url,
            {
                "work_date": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "submitter_name": "Test User",
                "text": "Regular maintenance",
            },
        )

        self.assertEqual(response.status_code, 302)
        log_entry = LogEntry.objects.first()
        self.assertIsNone(log_entry.problem_report)

    def test_close_problem_checkbox_closes_problem_report(self):
        """Checking 'close the problem report' should close it when creating log entry."""
        self.client.force_login(self.staff_user)
        self.assertEqual(self.problem_report.status, ProblemReport.STATUS_OPEN)

        response = self.client.post(
            self.create_url,
            {
                "work_date": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "submitter_name": "Test User",
                "text": "Fixed the stuck ball",
                "close_problem": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.problem_report.refresh_from_db()
        self.assertEqual(self.problem_report.status, ProblemReport.STATUS_CLOSED)

    def test_without_close_problem_checkbox_leaves_problem_open(self):
        """Not checking 'close the problem report' should leave it open."""
        self.client.force_login(self.staff_user)
        self.assertEqual(self.problem_report.status, ProblemReport.STATUS_OPEN)

        response = self.client.post(
            self.create_url,
            {
                "work_date": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "submitter_name": "Test User",
                "text": "Investigated the issue",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.problem_report.refresh_from_db()
        self.assertEqual(self.problem_report.status, ProblemReport.STATUS_OPEN)


@tag("views")
class LogListSearchTests(TestDataMixin, TestCase):
    """Tests for global log list search."""

    def setUp(self):
        super().setUp()
        self.list_url = reverse("log-list")

    def test_search_includes_problem_report_description(self):
        """Search should match attached problem report description."""
        report = create_problem_report(machine=self.machine, description="Coil stop broken")
        log_with_report = create_log_entry(
            machine=self.machine,
            text="Investigated noisy coil",
            problem_report=report,
        )
        create_log_entry(machine=self.machine, text="Adjusted flipper alignment")

        self.client.force_login(self.staff_user)
        response = self.client.get(self.list_url, {"q": "coil stop"})

        self.assertContains(response, log_with_report.text)
        self.assertContains(response, "Problem:")
        self.assertContains(response, "Coil stop broken")
        self.assertNotContains(response, "Adjusted flipper alignment")

    def test_search_includes_maintainer_names(self):
        """Search should match free-text maintainer names."""
        log_with_name = create_log_entry(
            machine=self.machine,
            text="Replaced coil",
            maintainer_names="Wandering Willie",
        )
        create_log_entry(machine=self.machine, text="Adjusted flipper alignment")

        self.client.force_login(self.staff_user)
        response = self.client.get(self.list_url, {"q": "Wandering"})

        self.assertContains(response, log_with_name.text)
        self.assertNotContains(response, "Adjusted flipper alignment")


@tag("views")
class MachineLogSearchTests(TestDataMixin, TestCase):
    """Tests for machine log view search."""

    def setUp(self):
        super().setUp()
        self.list_url = reverse("log-machine", kwargs={"slug": self.machine.slug})

    def test_search_includes_problem_report_reporter_name(self):
        """Search should match attached problem report's free-text reporter name."""
        report = create_problem_report(
            machine=self.machine,
            description="Ball stuck",
            reported_by_name="Visiting Vera",
        )
        log_with_report = create_log_entry(
            machine=self.machine,
            text="Cleared stuck ball",
            problem_report=report,
        )
        create_log_entry(machine=self.machine, text="Adjusted flipper alignment")

        self.client.force_login(self.staff_user)
        response = self.client.get(self.list_url, {"q": "Visiting"})

        self.assertContains(response, log_with_report.text)
        self.assertNotContains(response, "Adjusted flipper alignment")


@tag("views", "access-control")
class MachineBulkQRCodeViewAccessTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for MachineBulkQRCodeView access control.

    This view generates bulk QR codes for all machines.
    It requires maintainer portal access (staff or superuser).
    """

    def setUp(self):
        super().setUp()
        self.url = reverse("machine-qr-bulk")

    def test_requires_authentication(self):
        """Anonymous users are redirected to login."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_requires_maintainer_access(self):
        """Regular users (non-maintainers) get 403."""
        self.client.force_login(self.regular_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_accessible_to_maintainer(self):
        """Maintainers (staff users) can access the view."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_accessible_to_superuser(self):
        """Superusers can access the view."""
        self.client.force_login(self.superuser)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
