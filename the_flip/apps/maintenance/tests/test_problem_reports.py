"""Tests for problem report views and functionality."""

from datetime import timedelta

from django.conf import settings
from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from the_flip.apps.core.test_utils import (
    TestDataMixin,
    create_log_entry,
    create_problem_report,
    create_staff_user,
)
from the_flip.apps.maintenance.models import LogEntry, ProblemReport


@tag("views")
class ProblemReportDetailViewTests(TestDataMixin, TestCase):
    """Tests for the problem report detail view."""

    def setUp(self):
        super().setUp()
        self.report = create_problem_report(
            machine=self.machine,
            problem_type=ProblemReport.PROBLEM_STUCK_BALL,
            description="Ball is stuck in the upper playfield",
            reported_by_name="John Doe",
            reported_by_contact="john@example.com",
            device_info="iPhone 12",
            ip_address="192.168.1.1",
        )
        self.detail_url = reverse("problem-report-detail", kwargs={"pk": self.report.pk})

    def test_detail_view_requires_authentication(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_detail_view_requires_staff_permission(self):
        """Non-staff users should be denied access (403)."""
        self.client.login(username="regularuser", password="testpass123")
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 403)

    def test_detail_view_accessible_to_staff(self):
        """Staff users should be able to access the detail page."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "maintenance/problem_report_detail.html")

    def test_detail_view_displays_report_information(self):
        """Detail page should display core report information with reporter when available."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.detail_url)

        self.assertContains(response, self.machine.display_name)
        self.assertContains(response, "Stuck Ball")
        self.assertContains(response, "Ball is stuck in the upper playfield")
        self.assertContains(response, "by John Doe")
        self.assertContains(response, "Open")

    def test_detail_view_with_reported_by_user_hides_device_information(self):
        """If report was submitted by a logged-in user, only show the user."""
        submitter = create_staff_user(
            username="reportsubmitter", first_name="Report", last_name="Submitter"
        )
        self.report.reported_by_user = submitter
        self.report.save()

        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.detail_url)

        self.assertContains(response, "by Report Submitter")
        self.assertNotContains(response, "john@example.com")
        self.assertNotContains(response, "iPhone 12")
        self.assertNotContains(response, "192.168.1.1")

    def test_detail_view_hides_reporter_for_anonymous_submission(self):
        """Anonymous submissions should not render reporter details."""
        self.report.reported_by_user = None
        self.report.reported_by_name = ""
        self.report.reported_by_contact = ""
        self.report.device_info = ""
        self.report.ip_address = None
        self.report.save()

        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.detail_url)

        self.assertNotContains(response, "by ")

    def test_detail_view_shows_close_button_for_open_report(self):
        """Detail page should show 'Close Problem Report' button for open reports."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.detail_url)

        self.assertContains(response, "Close Problem Report")
        self.assertNotContains(response, "Re-Open Problem Report")

    def test_detail_view_shows_reopen_button_for_closed_report(self):
        """Detail page should show 'Re-Open Problem Report' button for closed reports."""
        self.report.status = ProblemReport.STATUS_CLOSED
        self.report.save()

        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.detail_url)

        self.assertContains(response, "Re-Open Problem Report")
        self.assertNotContains(response, "Close Problem Report")

    def test_status_toggle_requires_staff(self):
        """Non-staff users should not be able to toggle status."""
        self.client.login(username="regularuser", password="testpass123")
        response = self.client.post(self.detail_url)
        self.assertEqual(response.status_code, 403)

        self.report.refresh_from_db()
        self.assertEqual(self.report.status, ProblemReport.STATUS_OPEN)

    def test_status_toggle_from_open_to_closed(self):
        """Staff users should be able to close an open report."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.post(self.detail_url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.detail_url)

        self.report.refresh_from_db()
        self.assertEqual(self.report.status, ProblemReport.STATUS_CLOSED)
        log_entry = LogEntry.objects.latest("created_at")
        self.assertEqual(log_entry.text, "Closed problem report")
        self.assertEqual(log_entry.problem_report, self.report)
        self.assertEqual(log_entry.machine, self.machine)
        self.assertEqual(log_entry.created_by, self.staff_user)
        self.assertTrue(log_entry.maintainers.filter(user=self.staff_user).exists())

    def test_status_toggle_from_closed_to_open(self):
        """Staff users should be able to re-open a closed report."""
        self.report.status = ProblemReport.STATUS_CLOSED
        self.report.save()

        self.client.login(username="staffuser", password="testpass123")
        response = self.client.post(self.detail_url)

        self.assertEqual(response.status_code, 302)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, ProblemReport.STATUS_OPEN)
        log_entry = LogEntry.objects.latest("created_at")
        self.assertEqual(log_entry.text, "Re-opened problem report")
        self.assertEqual(log_entry.problem_report, self.report)
        self.assertEqual(log_entry.machine, self.machine)
        self.assertEqual(log_entry.created_by, self.staff_user)
        self.assertTrue(log_entry.maintainers.filter(user=self.staff_user).exists())

    def test_status_toggle_shows_close_message(self):
        """Closing a report should show appropriate success message."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.post(self.detail_url, follow=True)

        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), "Problem report closed.")

    def test_status_toggle_shows_reopen_message(self):
        """Re-opening a report should show appropriate success message."""
        self.report.status = ProblemReport.STATUS_CLOSED
        self.report.save()

        self.client.login(username="staffuser", password="testpass123")
        response = self.client.post(self.detail_url, follow=True)

        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), "Problem report re-opened.")


@tag("views")
class ProblemReportListViewTests(TestDataMixin, TestCase):
    """Tests for the global problem report list view."""

    def setUp(self):
        super().setUp()
        self.report = create_problem_report(machine=self.machine, description="Test problem")
        self.list_url = reverse("problem-report-list")

    def test_list_view_requires_authentication(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_list_view_requires_staff_permission(self):
        """Non-staff users should be denied access (403)."""
        self.client.login(username="regularuser", password="testpass123")
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    def test_list_view_accessible_to_staff(self):
        """Staff users should be able to access the list page."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "maintenance/problem_report_list.html")

    def test_list_view_contains_link_to_detail(self):
        """List view should contain links to detail pages."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.list_url)

        detail_url = reverse("problem-report-detail", kwargs={"pk": self.report.pk})
        self.assertContains(response, detail_url)

    def test_list_view_pagination(self):
        """List view should paginate results."""
        self.client.login(username="staffuser", password="testpass123")
        for i in range(15):
            create_problem_report(machine=self.machine, description=f"Problem {i}")

        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["reports"]), 10)
        self.assertTrue(response.context["page_obj"].has_next())

    def test_list_view_search_by_description(self):
        """List view should filter by description text."""
        self.client.login(username="staffuser", password="testpass123")
        create_problem_report(machine=self.machine, description="Unique flippers broken")

        response = self.client.get(self.list_url, {"q": "flippers"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["reports"]), 1)
        self.assertContains(response, "Unique flippers broken")

    def test_list_view_search_by_machine_name(self):
        """List view should filter by machine model name."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.list_url, {"q": "Test Machine"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["reports"]), 1)

    def test_list_view_search_no_results(self):
        """List view should show empty message when search has no results."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.list_url, {"q": "nonexistent"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["reports"]), 0)
        self.assertContains(response, "No problem reports match your search")


@tag("views", "ajax")
class ProblemReportListPartialViewTests(TestDataMixin, TestCase):
    """Tests for the problem report list AJAX endpoint."""

    def setUp(self):
        super().setUp()
        self.entries_url = reverse("problem-report-list-entries")

    def test_partial_view_returns_json(self):
        """AJAX endpoint should return JSON response."""
        self.client.login(username="staffuser", password="testpass123")
        create_problem_report(machine=self.machine, description="Test problem")

        response = self.client.get(self.entries_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

        data = response.json()
        self.assertIn("items", data)
        self.assertIn("has_next", data)
        self.assertIn("next_page", data)

    def test_partial_view_pagination(self):
        """AJAX endpoint should paginate and return correct metadata."""
        self.client.login(username="staffuser", password="testpass123")
        for i in range(15):
            create_problem_report(machine=self.machine, description=f"Problem {i}")

        response = self.client.get(self.entries_url, {"page": 1})
        data = response.json()
        self.assertTrue(data["has_next"])
        self.assertEqual(data["next_page"], 2)

        response = self.client.get(self.entries_url, {"page": 2})
        data = response.json()
        self.assertFalse(data["has_next"])
        self.assertIsNone(data["next_page"])

    def test_partial_view_search(self):
        """AJAX endpoint should respect search query."""
        self.client.login(username="staffuser", password="testpass123")
        create_problem_report(machine=self.machine, description="Flipper issue")
        create_problem_report(machine=self.machine, description="Display broken")

        response = self.client.get(self.entries_url, {"q": "Flipper"})
        data = response.json()
        self.assertIn("Flipper issue", data["items"])
        self.assertNotIn("Display broken", data["items"])

    def test_partial_view_requires_staff(self):
        """AJAX endpoint should require staff permission."""
        self.client.login(username="regularuser", password="testpass123")
        response = self.client.get(self.entries_url)
        self.assertEqual(response.status_code, 403)


@tag("views")
class MachineProblemReportListViewTests(TestDataMixin, TestCase):
    """Tests for the machine-specific problem report list view."""

    def setUp(self):
        super().setUp()
        self.report = create_problem_report(machine=self.machine, description="Test problem")
        self.machine_list_url = reverse(
            "machine-problem-reports", kwargs={"slug": self.machine.slug}
        )

    def test_machine_list_view_contains_link_to_detail(self):
        """Machine-specific list view should contain links to detail pages."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.machine_list_url)

        detail_url = reverse("problem-report-detail", kwargs={"pk": self.report.pk})
        self.assertContains(response, detail_url)


@tag("views", "public")
class ProblemReportCreateViewTests(TestDataMixin, TestCase):
    """Tests for the public problem report submission view."""

    def setUp(self):
        super().setUp()
        self.url = reverse("problem-report-create", kwargs={"slug": self.machine.slug})

    def test_create_view_accessible_without_login(self):
        """Problem report form should be accessible to anonymous users."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "maintenance/problem_report_form.html")

    def test_create_view_shows_correct_machine_name(self):
        """Problem report form should show the machine's display name."""
        response = self.client.get(self.url)
        self.assertContains(response, self.machine.display_name)

    def test_create_problem_report_success(self):
        """Successfully creating a problem report should save it with correct data."""
        data = {
            "problem_type": ProblemReport.PROBLEM_STUCK_BALL,
            "description": "Ball is stuck behind the bumpers",
        }
        response = self.client.post(self.url, data, REMOTE_ADDR="192.168.1.100")

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, self.machine.get_absolute_url())

        self.assertEqual(ProblemReport.objects.count(), 1)
        report = ProblemReport.objects.first()
        self.assertEqual(report.machine, self.machine)
        self.assertEqual(report.problem_type, ProblemReport.PROBLEM_STUCK_BALL)
        self.assertEqual(report.description, "Ball is stuck behind the bumpers")
        self.assertEqual(report.status, ProblemReport.STATUS_OPEN)
        self.assertEqual(report.ip_address, "192.168.1.100")

    def test_create_problem_report_with_other_type(self):
        """Problem type can be explicitly set to 'other'."""
        data = {
            "problem_type": ProblemReport.PROBLEM_OTHER,
            "description": "Something is wrong",
        }
        response = self.client.post(self.url, data, REMOTE_ADDR="192.168.1.100")

        self.assertEqual(response.status_code, 302)
        report = ProblemReport.objects.first()
        self.assertEqual(report.problem_type, ProblemReport.PROBLEM_OTHER)

    def test_create_problem_report_captures_user_agent(self):
        """Problem report should capture the User-Agent header."""
        data = {
            "problem_type": ProblemReport.PROBLEM_NO_CREDITS,
            "description": "Credits not working",
        }
        self.client.post(
            self.url,
            data,
            REMOTE_ADDR="192.168.1.100",
            HTTP_USER_AGENT="Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)",
        )

        report = ProblemReport.objects.first()
        self.assertIn("iPhone", report.device_info)
        self.assertIn("Mozilla", report.device_info)

    def test_create_problem_report_records_logged_in_user(self):
        """Submitting while authenticated should set reported_by_user."""
        maintainer = create_staff_user(username="maintainer")
        self.client.login(username="maintainer", password="testpass123")
        data = {
            "problem_type": ProblemReport.PROBLEM_STUCK_BALL,
            "description": "Ball locked up",
        }
        self.client.post(self.url, data, REMOTE_ADDR="203.0.113.42")

        report = ProblemReport.objects.first()
        self.assertEqual(report.reported_by_user, maintainer)
        self.assertEqual(report.ip_address, "203.0.113.42")

    def test_rate_limiting_blocks_excessive_submissions(self):
        """Rate limiting should block submissions after exceeding the limit."""
        for i in range(settings.RATE_LIMIT_REPORTS_PER_IP):
            data = {
                "problem_type": ProblemReport.PROBLEM_OTHER,
                "description": f"Report {i+1}",
            }
            response = self.client.post(self.url, data, REMOTE_ADDR="192.168.1.100")
            self.assertEqual(response.status_code, 302)

        data = {
            "problem_type": ProblemReport.PROBLEM_OTHER,
            "description": "This should be blocked",
        }
        response = self.client.post(self.url, data, REMOTE_ADDR="192.168.1.100")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ProblemReport.objects.count(), settings.RATE_LIMIT_REPORTS_PER_IP)

    def test_rate_limiting_allows_different_ips(self):
        """Rate limiting should be per IP address."""
        for i in range(settings.RATE_LIMIT_REPORTS_PER_IP):
            data = {
                "problem_type": ProblemReport.PROBLEM_OTHER,
                "description": f"Report from IP1 - {i+1}",
            }
            self.client.post(self.url, data, REMOTE_ADDR="192.168.1.100")

        data = {
            "problem_type": ProblemReport.PROBLEM_OTHER,
            "description": "Report from different IP",
        }
        response = self.client.post(self.url, data, REMOTE_ADDR="192.168.1.200")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ProblemReport.objects.count(), settings.RATE_LIMIT_REPORTS_PER_IP + 1)

    def test_rate_limiting_window_expires(self):
        """Rate limiting should reset after the time window expires."""
        for i in range(settings.RATE_LIMIT_REPORTS_PER_IP):
            data = {
                "problem_type": ProblemReport.PROBLEM_OTHER,
                "description": f"Report {i+1}",
            }
            self.client.post(self.url, data, REMOTE_ADDR="192.168.1.100")

        old_time = timezone.now() - timedelta(minutes=settings.RATE_LIMIT_WINDOW_MINUTES + 1)
        ProblemReport.objects.all().update(created_at=old_time)

        data = {
            "problem_type": ProblemReport.PROBLEM_OTHER,
            "description": "This should succeed after window expires",
        }
        response = self.client.post(self.url, data, REMOTE_ADDR="192.168.1.100")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ProblemReport.objects.count(), settings.RATE_LIMIT_REPORTS_PER_IP + 1)


@tag("views")
class ProblemReportDetailLogEntriesTests(TestDataMixin, TestCase):
    """Tests for log entries display on problem report detail page."""

    def setUp(self):
        super().setUp()
        self.problem_report = create_problem_report(
            machine=self.machine,
            problem_type=ProblemReport.PROBLEM_STUCK_BALL,
            description="Ball stuck",
        )
        self.detail_url = reverse("problem-report-detail", kwargs={"pk": self.problem_report.pk})

    def test_detail_page_shows_add_log_entry_button(self):
        """Problem report detail should have Add Log Entry button."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.detail_url)

        self.assertContains(response, "Add Log Entry")
        add_url = reverse("log-create-problem-report", kwargs={"pk": self.problem_report.pk})
        self.assertContains(response, add_url)

    def test_detail_page_shows_linked_log_entries(self):
        """Problem report detail should display linked log entries."""
        create_log_entry(
            machine=self.machine,
            problem_report=self.problem_report,
            text="Investigated the issue",
        )

        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.detail_url)

        self.assertContains(response, "Investigated the issue")

    def test_detail_page_shows_no_log_entries_message(self):
        """Problem report detail should show message when no log entries exist."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.detail_url)

        self.assertContains(response, "No log entries yet")


@tag("views", "ajax")
class ProblemReportLogEntriesPartialViewTests(TestDataMixin, TestCase):
    """Tests for the log entries AJAX endpoint on problem report detail."""

    def setUp(self):
        super().setUp()
        self.problem_report = create_problem_report(
            machine=self.machine,
            problem_type=ProblemReport.PROBLEM_STUCK_BALL,
            description="Ball stuck",
        )
        self.entries_url = reverse(
            "problem-report-log-entries", kwargs={"pk": self.problem_report.pk}
        )

    def test_returns_json(self):
        """AJAX endpoint should return JSON response."""
        self.client.login(username="staffuser", password="testpass123")
        create_log_entry(
            machine=self.machine,
            problem_report=self.problem_report,
            text="Test log entry",
        )

        response = self.client.get(self.entries_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

        data = response.json()
        self.assertIn("items", data)
        self.assertIn("has_next", data)
        self.assertIn("next_page", data)

    def test_only_returns_linked_log_entries(self):
        """AJAX endpoint should only return log entries linked to this problem report."""
        create_log_entry(
            machine=self.machine,
            problem_report=self.problem_report,
            text="Linked entry",
        )
        create_log_entry(
            machine=self.machine,
            text="Unlinked entry",
        )

        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.entries_url)

        data = response.json()
        self.assertIn("Linked entry", data["items"])
        self.assertNotIn("Unlinked entry", data["items"])

    def test_pagination(self):
        """AJAX endpoint should paginate results."""
        self.client.login(username="staffuser", password="testpass123")
        for i in range(15):
            create_log_entry(
                machine=self.machine,
                problem_report=self.problem_report,
                text=f"Log entry {i}",
            )

        # First page
        response = self.client.get(self.entries_url, {"page": 1})
        data = response.json()
        self.assertTrue(data["has_next"])
        self.assertEqual(data["next_page"], 2)

        # Second page
        response = self.client.get(self.entries_url, {"page": 2})
        data = response.json()
        self.assertFalse(data["has_next"])
        self.assertIsNone(data["next_page"])

    def test_requires_staff(self):
        """AJAX endpoint should require staff permission."""
        self.client.login(username="regularuser", password="testpass123")
        response = self.client.get(self.entries_url)
        self.assertEqual(response.status_code, 403)
