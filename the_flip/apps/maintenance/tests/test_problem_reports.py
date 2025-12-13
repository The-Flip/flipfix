"""Tests for problem report views and functionality."""

from datetime import timedelta

from django.conf import settings
from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TemporaryMediaMixin,
    TestDataMixin,
    create_log_entry,
    create_maintainer_user,
    create_problem_report,
)
from the_flip.apps.maintenance.models import LogEntry, ProblemReport, ProblemReportMedia


@tag("views")
class ProblemReportDetailViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
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
        self.client.force_login(self.regular_user)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 403)

    def test_detail_view_accessible_to_staff(self):
        """Staff users should be able to access the detail page."""
        self.client.force_login(self.staff_user)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "maintenance/problem_report_detail.html")

    def test_detail_view_displays_report_information(self):
        """Detail page should display core report information with reporter when available."""
        self.client.force_login(self.staff_user)
        response = self.client.get(self.detail_url)

        self.assertContains(response, self.machine.display_name)
        self.assertContains(response, "Stuck Ball")
        self.assertContains(response, "Ball is stuck in the upper playfield")
        self.assertContains(response, "by John Doe")
        self.assertContains(response, "Open")

    def test_detail_view_with_reported_by_user_hides_device_information(self):
        """If report was submitted by a logged-in user, only show the user."""
        submitter = create_maintainer_user(
            username="reportsubmitter", first_name="Report", last_name="Submitter"
        )
        self.report.reported_by_user = submitter
        self.report.reported_by_name = ""  # Clear so reported_by_user is used
        self.report.save()

        self.client.force_login(self.staff_user)
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

        self.client.force_login(self.staff_user)
        response = self.client.get(self.detail_url)

        self.assertNotContains(response, "by ")

    def test_detail_view_shows_close_button_for_open_report(self):
        """Detail page should show 'Close Problem' button for open reports."""
        self.client.force_login(self.staff_user)
        response = self.client.get(self.detail_url)

        self.assertContains(response, "Close Problem")
        self.assertNotContains(response, "Re-Open Problem")

    def test_detail_view_shows_reopen_button_for_closed_report(self):
        """Detail page should show 'Re-Open Problem' button for closed reports."""
        self.report.status = ProblemReport.STATUS_CLOSED
        self.report.save()

        self.client.force_login(self.staff_user)
        response = self.client.get(self.detail_url)

        self.assertContains(response, "Re-Open Problem")
        self.assertNotContains(response, "Close Problem")

    def test_status_toggle_requires_staff(self):
        """Non-staff users should not be able to toggle status."""
        self.client.force_login(self.regular_user)
        response = self.client.post(self.detail_url)
        self.assertEqual(response.status_code, 403)

        self.report.refresh_from_db()
        self.assertEqual(self.report.status, ProblemReport.STATUS_OPEN)

    def test_status_toggle_from_open_to_closed(self):
        """Staff users should be able to close an open report."""
        self.client.force_login(self.staff_user)
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

        self.client.force_login(self.staff_user)
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
        self.client.force_login(self.staff_user)
        response = self.client.post(self.detail_url, follow=True)

        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("closed", str(messages[0]))

    def test_status_toggle_shows_reopen_message(self):
        """Re-opening a report should show appropriate success message."""
        self.report.status = ProblemReport.STATUS_CLOSED
        self.report.save()

        self.client.force_login(self.staff_user)
        response = self.client.post(self.detail_url, follow=True)

        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("re-opened", str(messages[0]))

    def test_detail_view_search_filters_log_entries_by_text(self):
        """Search should filter log entries by text on the detail page."""
        create_log_entry(
            machine=self.machine,
            problem_report=self.report,
            text="Investigated coil stop issue",
        )
        create_log_entry(
            machine=self.machine,
            problem_report=self.report,
            text="Adjusted flipper alignment",
        )

        self.client.force_login(self.staff_user)
        response = self.client.get(self.detail_url, {"q": "coil"})

        self.assertContains(response, "Investigated coil stop issue")
        self.assertNotContains(response, "Adjusted flipper alignment")

    def test_detail_view_search_filters_log_entries_by_maintainer(self):
        """Search should match maintainer names on log entries."""
        tech = create_maintainer_user(username="techuser", first_name="Tech", last_name="Person")
        other = create_maintainer_user(
            username="otheruser", first_name="Other", last_name="Maintainer"
        )

        log_with_tech = create_log_entry(
            machine=self.machine,
            problem_report=self.report,
            text="Investigated coil stop issue",
        )
        log_with_other = create_log_entry(
            machine=self.machine,
            problem_report=self.report,
            text="Adjusted flipper alignment",
        )
        log_with_tech.maintainers.add(Maintainer.objects.get(user=tech))
        log_with_other.maintainers.add(Maintainer.objects.get(user=other))

        self.client.force_login(self.staff_user)
        response = self.client.get(self.detail_url, {"q": "Tech"})

        self.assertContains(response, "Investigated coil stop issue")
        self.assertNotContains(response, "Adjusted flipper alignment")


@tag("views", "ajax")
class ProblemReportDetailViewTextUpdateTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for ProblemReportDetailView AJAX text updates."""

    def setUp(self):
        super().setUp()
        self.report = create_problem_report(
            machine=self.machine,
            description="Original description",
        )
        self.detail_url = reverse("problem-report-detail", kwargs={"pk": self.report.pk})

    def test_update_text_success(self):
        """AJAX endpoint updates description successfully."""
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.detail_url,
            {"action": "update_text", "text": "Updated description"},
        )

        self.assertEqual(response.status_code, 200)
        self.report.refresh_from_db()
        self.assertEqual(self.report.description, "Updated description")

    def test_update_text_empty(self):
        """AJAX endpoint allows empty description."""
        self.client.force_login(self.staff_user)

        response = self.client.post(
            self.detail_url,
            {"action": "update_text", "text": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.report.refresh_from_db()
        self.assertEqual(self.report.description, "")

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
class ProblemReportMachineUpdateTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for updating the machine of a problem report via AJAX."""

    def setUp(self):
        super().setUp()
        from the_flip.apps.core.test_utils import create_machine

        self.report = create_problem_report(
            machine=self.machine,
            description="Test problem",
        )
        self.other_machine = create_machine(slug="other-machine")
        self.detail_url = reverse("problem-report-detail", kwargs={"pk": self.report.pk})

    def test_update_machine_success(self):
        """Successfully update problem report machine."""
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

        self.report.refresh_from_db()
        self.assertEqual(self.report.machine, self.other_machine)

    def test_update_machine_moves_linked_log_entries(self):
        """Updating machine also moves all linked log entries."""
        log_entry = create_log_entry(
            machine=self.machine,
            problem_report=self.report,
            text="Linked log entry",
        )

        self.client.force_login(self.staff_user)
        self.client.post(
            self.detail_url,
            {
                "action": "update_machine",
                "machine_slug": self.other_machine.slug,
            },
        )

        log_entry.refresh_from_db()
        self.assertEqual(log_entry.machine, self.other_machine)

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

    def test_update_machine_requires_authentication(self):
        """Anonymous users cannot update machine."""
        response = self.client.post(
            self.detail_url,
            {
                "action": "update_machine",
                "machine_slug": self.other_machine.slug,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

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


@tag("views")
class ProblemReportListViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
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
        self.client.force_login(self.regular_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    def test_list_view_accessible_to_staff(self):
        """Staff users should be able to access the list page."""
        self.client.force_login(self.staff_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "maintenance/problem_report_list.html")

    def test_list_view_contains_link_to_detail(self):
        """List view should contain links to detail pages."""
        self.client.force_login(self.staff_user)
        response = self.client.get(self.list_url)

        detail_url = reverse("problem-report-detail", kwargs={"pk": self.report.pk})
        self.assertContains(response, detail_url)

    def test_list_view_pagination(self):
        """List view should paginate results."""
        self.client.force_login(self.staff_user)
        for i in range(15):
            create_problem_report(machine=self.machine, description=f"Problem {i}")

        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["reports"]), 10)
        self.assertTrue(response.context["page_obj"].has_next())

    def test_list_view_search_by_description(self):
        """List view should filter by description text."""
        self.client.force_login(self.staff_user)
        create_problem_report(machine=self.machine, description="Unique flippers broken")

        response = self.client.get(self.list_url, {"q": "flippers"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["reports"]), 1)
        self.assertContains(response, "Unique flippers broken")

    def test_list_view_search_by_machine_name(self):
        """List view should filter by machine model name."""
        self.client.force_login(self.staff_user)
        response = self.client.get(self.list_url, {"q": "Test Machine"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["reports"]), 1)

    def test_list_view_search_no_results(self):
        """List view should show empty message when search has no results."""
        self.client.force_login(self.staff_user)
        response = self.client.get(self.list_url, {"q": "nonexistent"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["reports"]), 0)
        self.assertContains(response, "No problem reports match your search")

    def test_list_view_search_matches_log_entry_text(self):
        """List search should include attached log entry text."""
        create_log_entry(machine=self.machine, problem_report=self.report, text="Fixed coil stop")
        other_report = create_problem_report(machine=self.machine, description="Other issue")
        create_log_entry(machine=self.machine, problem_report=other_report, text="Different work")

        self.client.force_login(self.staff_user)
        response = self.client.get(self.list_url, {"q": "coil stop"})

        self.assertContains(response, self.report.description)
        self.assertNotContains(response, other_report.description)

    def test_list_view_search_matches_reporter_name(self):
        """List search should include free-text reporter name."""
        # Create report with free-text reporter name
        create_problem_report(
            machine=self.machine,
            description="Flickering lights",
            reported_by_name="Wandering Willie",
        )
        create_problem_report(machine=self.machine, description="Other issue")

        self.client.force_login(self.staff_user)
        response = self.client.get(self.list_url, {"q": "Wandering"})

        self.assertContains(response, "Flickering lights")
        self.assertNotContains(response, "Other issue")

    def test_list_view_search_matches_log_entry_maintainer_names(self):
        """List search should include free-text log entry maintainer names."""
        # Create report with log entry that has free-text maintainer name
        report_with_log = create_problem_report(
            machine=self.machine, description="Flickering lights"
        )
        create_log_entry(
            machine=self.machine,
            problem_report=report_with_log,
            text="Investigated issue",
            maintainer_names="Wandering Willie",
        )
        create_problem_report(machine=self.machine, description="Other issue")

        self.client.force_login(self.staff_user)
        response = self.client.get(self.list_url, {"q": "Wandering"})

        self.assertContains(response, "Flickering lights")
        self.assertNotContains(response, "Other issue")


@tag("views", "ajax")
class ProblemReportListPartialViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for the problem report list AJAX endpoint."""

    def setUp(self):
        super().setUp()
        self.entries_url = reverse("problem-report-list-entries")

    def test_partial_view_returns_json(self):
        """AJAX endpoint should return JSON response."""
        self.client.force_login(self.staff_user)
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
        self.client.force_login(self.staff_user)
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
        self.client.force_login(self.staff_user)
        create_problem_report(machine=self.machine, description="Flipper issue")
        create_problem_report(machine=self.machine, description="Display broken")

        response = self.client.get(self.entries_url, {"q": "Flipper"})
        data = response.json()
        self.assertIn("Flipper issue", data["items"])
        self.assertNotIn("Display broken", data["items"])

    def test_partial_view_search_matches_log_entry_text(self):
        """AJAX endpoint search should include attached log entry text."""
        self.client.force_login(self.staff_user)
        report_with_match = create_problem_report(machine=self.machine, description="Has match")
        create_log_entry(
            machine=self.machine, problem_report=report_with_match, text="Investigated coil stop"
        )
        report_no_match = create_problem_report(machine=self.machine, description="No match")
        create_log_entry(
            machine=self.machine, problem_report=report_no_match, text="Different work"
        )

        response = self.client.get(self.entries_url, {"q": "coil stop"})
        data = response.json()

        self.assertIn("Has match", data["items"])
        self.assertNotIn("No match", data["items"])

    def test_partial_view_requires_staff(self):
        """AJAX endpoint should require staff permission."""
        self.client.force_login(self.regular_user)
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
        self.client.force_login(self.staff_user)
        response = self.client.get(self.machine_list_url)

        detail_url = reverse("problem-report-detail", kwargs={"pk": self.report.pk})
        self.assertContains(response, detail_url)


@tag("views", "public")
class ProblemReportCreateViewTests(TestDataMixin, TestCase):
    """Tests for the public problem report submission view."""

    def setUp(self):
        super().setUp()
        self.url = reverse("public-problem-report-create", kwargs={"slug": self.machine.slug})

    def test_create_view_accessible_without_login(self):
        """Problem report form should be accessible to anonymous users."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "maintenance/problem_report_form_public.html")

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
        self.assertRedirects(response, self.url)  # Redirects back to itself

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
        maintainer = create_maintainer_user()
        self.client.force_login(maintainer)
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
                "description": f"Report {i + 1}",
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
                "description": f"Report from IP1 - {i + 1}",
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
                "description": f"Report {i + 1}",
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
        """Problem report detail should have Add Log button."""
        self.client.force_login(self.staff_user)
        response = self.client.get(self.detail_url)

        self.assertContains(response, "Add Log")
        add_url = reverse("log-create-problem-report", kwargs={"pk": self.problem_report.pk})
        self.assertContains(response, add_url)

    def test_detail_page_shows_linked_log_entries(self):
        """Problem report detail should display linked log entries."""
        create_log_entry(
            machine=self.machine,
            problem_report=self.problem_report,
            text="Investigated the issue",
        )

        self.client.force_login(self.staff_user)
        response = self.client.get(self.detail_url)

        self.assertContains(response, "Investigated the issue")

    def test_detail_page_shows_no_log_entries_message(self):
        """Problem report detail should show message when no log entries exist."""
        self.client.force_login(self.staff_user)
        response = self.client.get(self.detail_url)

        self.assertContains(response, "No log entries yet")


@tag("views", "ajax")
class ProblemReportLogEntriesPartialViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
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
        self.client.force_login(self.staff_user)
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

        self.client.force_login(self.staff_user)
        response = self.client.get(self.entries_url)

        data = response.json()
        self.assertIn("Linked entry", data["items"])
        self.assertNotIn("Unlinked entry", data["items"])

    def test_pagination(self):
        """AJAX endpoint should paginate results."""
        self.client.force_login(self.staff_user)
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
        self.client.force_login(self.regular_user)
        response = self.client.get(self.entries_url)
        self.assertEqual(response.status_code, 403)


@tag("views", "media")
class ProblemReportMediaCreateTests(TemporaryMediaMixin, TestDataMixin, TestCase):
    """Tests for media upload on problem report create page (maintainer)."""

    def setUp(self):
        super().setUp()
        self.create_url = reverse(
            "problem-report-create-machine", kwargs={"slug": self.machine.slug}
        )

    def test_create_with_media_upload(self):
        """Maintainer can upload media when creating a problem report."""
        from io import BytesIO

        from PIL import Image

        self.client.force_login(self.staff_user)

        # Create a valid image in memory
        img = Image.new("RGB", (100, 100), color="red")
        img_io = BytesIO()
        img.save(img_io, format="PNG")
        img_io.seek(0)
        img_io.name = "test.png"

        data = {
            "description": "Problem with media",
            "media_file": img_io,
        }
        response = self.client.post(self.create_url, data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ProblemReport.objects.count(), 1)
        report = ProblemReport.objects.first()
        # Maintainer form defaults to "Other" problem type
        self.assertEqual(report.problem_type, ProblemReport.PROBLEM_OTHER)
        self.assertEqual(report.media.count(), 1)
        media = report.media.first()
        self.assertEqual(media.media_type, ProblemReportMedia.TYPE_PHOTO)

    def test_create_without_media(self):
        """Problem report can be created without media."""
        self.client.force_login(self.staff_user)

        data = {
            "description": "No media attached",
        }
        response = self.client.post(self.create_url, data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ProblemReport.objects.count(), 1)
        report = ProblemReport.objects.first()
        # Maintainer form defaults to "Other" problem type
        self.assertEqual(report.problem_type, ProblemReport.PROBLEM_OTHER)
        self.assertEqual(report.media.count(), 0)

    def test_public_form_has_no_media_field(self):
        """Public problem report form should not have media upload field."""
        public_url = reverse("public-problem-report-create", kwargs={"slug": self.machine.slug})
        response = self.client.get(public_url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="media_file"')


@tag("views", "ajax", "media")
class ProblemReportMediaUploadTests(
    TemporaryMediaMixin, SuppressRequestLogsMixin, TestDataMixin, TestCase
):
    """Tests for AJAX media upload on problem report detail page."""

    def setUp(self):
        super().setUp()
        self.report = create_problem_report(
            machine=self.machine,
            description="Test problem",
        )
        self.detail_url = reverse("problem-report-detail", kwargs={"pk": self.report.pk})

    def test_upload_media_requires_staff(self):
        """Non-staff users cannot upload media."""
        from io import BytesIO

        from PIL import Image

        self.client.force_login(self.regular_user)

        img = Image.new("RGB", (100, 100), color="blue")
        img_io = BytesIO()
        img.save(img_io, format="PNG")
        img_io.seek(0)
        img_io.name = "test.png"

        data = {
            "action": "upload_media",
            "file": img_io,
        }
        response = self.client.post(self.detail_url, data)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(ProblemReportMedia.objects.count(), 0)

    def test_upload_media_success(self):
        """Staff can upload media via AJAX."""
        from io import BytesIO

        from PIL import Image

        self.client.force_login(self.staff_user)

        img = Image.new("RGB", (100, 100), color="green")
        img_io = BytesIO()
        img.save(img_io, format="PNG")
        img_io.seek(0)
        img_io.name = "test.png"

        data = {
            "action": "upload_media",
            "file": img_io,
        }
        response = self.client.post(self.detail_url, data)

        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertTrue(json_data["success"])
        self.assertIn("media_id", json_data)
        self.assertEqual(json_data["media_type"], "photo")

        self.assertEqual(ProblemReportMedia.objects.count(), 1)
        media = ProblemReportMedia.objects.first()
        self.assertEqual(media.problem_report, self.report)
        self.assertEqual(media.media_type, ProblemReportMedia.TYPE_PHOTO)


@tag("views", "ajax", "media")
class ProblemReportMediaDeleteTests(
    TemporaryMediaMixin, SuppressRequestLogsMixin, TestDataMixin, TestCase
):
    """Tests for AJAX media delete on problem report detail page."""

    def setUp(self):
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        super().setUp()
        self.report = create_problem_report(
            machine=self.machine,
            description="Test problem",
        )
        self.detail_url = reverse("problem-report-detail", kwargs={"pk": self.report.pk})

        # Create a valid image file for the media record
        img = Image.new("RGB", (100, 100), color="red")
        img_io = BytesIO()
        img.save(img_io, format="PNG")
        img_io.seek(0)

        self.media = ProblemReportMedia.objects.create(
            problem_report=self.report,
            media_type=ProblemReportMedia.TYPE_PHOTO,
            file=SimpleUploadedFile("test.png", img_io.read(), content_type="image/png"),
        )

    def test_delete_media_requires_staff(self):
        """Non-staff users cannot delete media."""
        self.client.force_login(self.regular_user)

        data = {
            "action": "delete_media",
            "media_id": self.media.id,
        }
        response = self.client.post(self.detail_url, data)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(ProblemReportMedia.objects.count(), 1)

    def test_delete_media_success(self):
        """Staff can delete media via AJAX."""
        self.client.force_login(self.staff_user)

        data = {
            "action": "delete_media",
            "media_id": self.media.id,
        }
        response = self.client.post(self.detail_url, data)

        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertTrue(json_data["success"])
        self.assertEqual(ProblemReportMedia.objects.count(), 0)

    def test_delete_media_wrong_report(self):
        """Cannot delete media from another problem report."""
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        other_report = create_problem_report(
            machine=self.machine,
            description="Other problem",
        )

        # Create a valid image file for other_media
        img = Image.new("RGB", (100, 100), color="blue")
        img_io = BytesIO()
        img.save(img_io, format="PNG")
        img_io.seek(0)

        other_media = ProblemReportMedia.objects.create(
            problem_report=other_report,
            media_type=ProblemReportMedia.TYPE_PHOTO,
            file=SimpleUploadedFile("other.png", img_io.read(), content_type="image/png"),
        )

        self.client.force_login(self.staff_user)

        # Try to delete other_media from this report's detail page
        data = {
            "action": "delete_media",
            "media_id": other_media.id,
        }
        response = self.client.post(self.detail_url, data)

        self.assertEqual(response.status_code, 404)
        # other_media should still exist
        self.assertTrue(ProblemReportMedia.objects.filter(pk=other_media.pk).exists())


@tag("views", "media")
class ProblemReportDetailMediaDisplayTests(TemporaryMediaMixin, TestDataMixin, TestCase):
    """Tests for media display on problem report detail page."""

    def setUp(self):
        super().setUp()
        self.report = create_problem_report(
            machine=self.machine,
            description="Test problem",
        )
        self.detail_url = reverse("problem-report-detail", kwargs={"pk": self.report.pk})

    def test_detail_shows_media_section(self):
        """Detail page should show Media section."""
        self.client.force_login(self.staff_user)
        response = self.client.get(self.detail_url)

        self.assertContains(response, "Media")
        self.assertContains(response, "Upload Photos")

    def test_detail_shows_no_media_message(self):
        """Detail page should show 'No media' when there are no uploads."""
        self.client.force_login(self.staff_user)
        response = self.client.get(self.detail_url)

        self.assertContains(response, "No media.")

    def test_detail_shows_uploaded_media(self):
        """Detail page should display uploaded media."""
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        # Create a valid image file for the media record
        img = Image.new("RGB", (100, 100), color="red")
        img_io = BytesIO()
        img.save(img_io, format="PNG")
        img_io.seek(0)

        ProblemReportMedia.objects.create(
            problem_report=self.report,
            media_type=ProblemReportMedia.TYPE_PHOTO,
            file=SimpleUploadedFile("test.png", img_io.read(), content_type="image/png"),
        )

        self.client.force_login(self.staff_user)
        response = self.client.get(self.detail_url)

        self.assertContains(response, "media-grid__item")
        self.assertNotContains(response, "No media.")


@tag("views")
class ProblemReportAutocompleteViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for the problem report autocomplete API."""

    def setUp(self):
        super().setUp()
        from the_flip.apps.core.test_utils import create_machine

        self.other_machine = create_machine(slug="other-machine")
        self.report1 = create_problem_report(
            machine=self.machine,
            description="First problem on main machine",
        )
        self.report2 = create_problem_report(
            machine=self.machine,
            description="Second problem on main machine",
        )
        self.report3 = create_problem_report(
            machine=self.other_machine,
            description="Problem on other machine",
        )
        self.api_url = reverse("api-problem-report-autocomplete")

    def test_requires_authentication(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get(self.api_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_returns_json_response(self):
        """API returns JSON with groups structure."""
        self.client.force_login(self.staff_user)
        response = self.client.get(self.api_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

        data = response.json()
        self.assertIn("groups", data)
        self.assertIsInstance(data["groups"], list)

    def test_groups_by_machine(self):
        """Reports are grouped by machine."""
        self.client.force_login(self.staff_user)
        response = self.client.get(self.api_url)

        data = response.json()
        machine_names = [g["machine_name"] for g in data["groups"]]
        self.assertIn(self.machine.display_name, machine_names)
        self.assertIn(self.other_machine.display_name, machine_names)

    def test_current_machine_appears_first(self):
        """When current_machine is specified, that machine's group appears first."""
        self.client.force_login(self.staff_user)
        response = self.client.get(self.api_url, {"current_machine": self.other_machine.slug})

        data = response.json()
        # Current machine group appears first with "(current)" suffix
        first_group_name = data["groups"][0]["machine_name"]
        self.assertIn(self.other_machine.display_name, first_group_name)
        self.assertIn("(current)", first_group_name)

    def test_includes_report_details(self):
        """Each report includes id, summary, and machine_name."""
        self.client.force_login(self.staff_user)
        response = self.client.get(self.api_url)

        data = response.json()
        # Find a report in the response
        all_reports = []
        for group in data["groups"]:
            all_reports.extend(group["reports"])

        report_ids = [r["id"] for r in all_reports]
        self.assertIn(self.report1.pk, report_ids)

        # Check structure of a report
        report = next(r for r in all_reports if r["id"] == self.report1.pk)
        self.assertIn("summary", report)
        self.assertIn("machine_name", report)

    def test_excludes_closed_reports(self):
        """Closed problem reports are not included in autocomplete."""
        # Close one of the reports
        self.report1.status = ProblemReport.STATUS_CLOSED
        self.report1.save()

        self.client.force_login(self.staff_user)
        response = self.client.get(self.api_url)

        data = response.json()
        all_report_ids = []
        for group in data["groups"]:
            all_report_ids.extend(r["id"] for r in group["reports"])

        self.assertNotIn(self.report1.pk, all_report_ids)
        self.assertIn(self.report2.pk, all_report_ids)  # Still open
        self.assertIn(self.report3.pk, all_report_ids)  # Still open

    def test_requires_maintainer_permission(self):
        """Regular users (non-maintainers) cannot access autocomplete API."""
        self.client.force_login(self.regular_user)
        response = self.client.get(self.api_url)
        self.assertEqual(response.status_code, 403)


@tag("views")
class ProblemReportListSearchTests(TestDataMixin, TestCase):
    """Tests for global problem report list search functionality."""

    def setUp(self):
        super().setUp()
        self.list_url = reverse("problem-report-list")

    def test_search_finds_report_by_reported_by_user(self):
        """Search should find problem reports by the submitting user's name."""
        # Create a report submitted by a logged-in user
        submitter = create_maintainer_user(
            username="submitter",
            first_name="Submitting",
            last_name="Sam",
        )
        create_problem_report(
            machine=self.machine,
            description="Flipper not working",
            reported_by_user=submitter,
        )

        self.client.force_login(self.staff_user)
        response = self.client.get(self.list_url, {"q": "Submitting"})

        self.assertContains(response, "Flipper not working")
