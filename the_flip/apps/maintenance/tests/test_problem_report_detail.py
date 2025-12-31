"""Tests for problem report detail views and actions."""

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TestDataMixin,
    create_log_entry,
    create_machine,
    create_maintainer_user,
    create_problem_report,
)
from the_flip.apps.maintenance.models import LogEntry, ProblemReport


@tag("views")
class ProblemReportDetailViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for the problem report detail view."""

    def setUp(self):
        super().setUp()
        self.report = create_problem_report(
            machine=self.machine,
            problem_type=ProblemReport.ProblemType.STUCK_BALL,
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
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "maintenance/problem_report_detail.html")

    def test_detail_view_displays_report_information(self):
        """Detail page should display core report information with reporter when available."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.detail_url)

        self.assertContains(response, self.machine.name)
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

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.detail_url)

        self.assertContains(response, "by Report Submitter")
        self.assertNotContains(response, "john@example.com")
        self.assertNotContains(response, "iPhone 12")
        self.assertNotContains(response, "192.168.1.1")

    def test_detail_view_shows_anonymous_for_anonymous_submission(self):
        """Anonymous submissions should show 'Anonymous' as reporter."""
        self.report.reported_by_user = None
        self.report.reported_by_name = ""
        self.report.reported_by_contact = ""
        self.report.device_info = ""
        self.report.ip_address = None
        self.report.save()

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.detail_url)

        self.assertContains(response, "by Anonymous")

    def test_detail_view_shows_close_button_for_open_report(self):
        """Detail page should show 'Close Problem' button for open reports."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.detail_url)

        self.assertContains(response, "Close Problem")
        self.assertNotContains(response, "Re-Open Problem")

    def test_detail_view_shows_reopen_button_for_closed_report(self):
        """Detail page should show 'Re-Open Problem' button for closed reports."""
        self.report.status = ProblemReport.Status.CLOSED
        self.report.save()

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.detail_url)

        self.assertContains(response, "Re-Open Problem")
        self.assertNotContains(response, "Close Problem")

    def test_status_toggle_requires_staff(self):
        """Non-staff users should not be able to toggle status."""
        self.client.force_login(self.regular_user)
        response = self.client.post(self.detail_url)
        self.assertEqual(response.status_code, 403)

        self.report.refresh_from_db()
        self.assertEqual(self.report.status, ProblemReport.Status.OPEN)

    def test_status_toggle_from_open_to_closed(self):
        """Staff users should be able to close an open report."""
        self.client.force_login(self.maintainer_user)
        response = self.client.post(self.detail_url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.detail_url)

        self.report.refresh_from_db()
        self.assertEqual(self.report.status, ProblemReport.Status.CLOSED)
        log_entry = LogEntry.objects.latest("occurred_at")
        self.assertEqual(log_entry.text, "Closed problem report")
        self.assertEqual(log_entry.problem_report, self.report)
        self.assertEqual(log_entry.machine, self.machine)
        self.assertEqual(log_entry.created_by, self.maintainer_user)
        self.assertTrue(log_entry.maintainers.filter(user=self.maintainer_user).exists())

    def test_status_toggle_from_closed_to_open(self):
        """Staff users should be able to re-open a closed report."""
        self.report.status = ProblemReport.Status.CLOSED
        self.report.save()

        self.client.force_login(self.maintainer_user)
        response = self.client.post(self.detail_url)

        self.assertEqual(response.status_code, 302)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, ProblemReport.Status.OPEN)
        log_entry = LogEntry.objects.latest("occurred_at")
        self.assertEqual(log_entry.text, "Re-opened problem report")
        self.assertEqual(log_entry.problem_report, self.report)
        self.assertEqual(log_entry.machine, self.machine)
        self.assertEqual(log_entry.created_by, self.maintainer_user)
        self.assertTrue(log_entry.maintainers.filter(user=self.maintainer_user).exists())

    def test_status_toggle_shows_close_message(self):
        """Closing a report should show appropriate success message."""
        self.client.force_login(self.maintainer_user)
        response = self.client.post(self.detail_url, follow=True)

        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("closed", str(messages[0]))

    def test_status_toggle_shows_reopen_message(self):
        """Re-opening a report should show appropriate success message."""
        self.report.status = ProblemReport.Status.CLOSED
        self.report.save()

        self.client.force_login(self.maintainer_user)
        response = self.client.post(self.detail_url, follow=True)

        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("re-opened", str(messages[0]))

    def test_unrecognized_action_does_not_toggle_status(self):
        """POST with unrecognized action should NOT toggle status.

        This is a regression test for a bug where any POST with an unrecognized
        action would fall through to the status toggle code, inadvertently
        changing the problem report status.
        """
        initial_status = self.report.status
        initial_log_count = LogEntry.objects.count()

        self.client.force_login(self.maintainer_user)
        response = self.client.post(
            self.detail_url,
            {"action": "invalid_action_xyz"},
        )

        # Status should NOT have changed
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, initial_status)

        # No new log entry should have been created
        self.assertEqual(LogEntry.objects.count(), initial_log_count)

        # Should return 400 Bad Request for unrecognized action
        self.assertEqual(response.status_code, 400)

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

        self.client.force_login(self.maintainer_user)
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

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.detail_url, {"q": "Tech"})

        self.assertContains(response, "Investigated coil stop issue")
        self.assertNotContains(response, "Adjusted flipper alignment")

    def test_detail_view_search_does_not_match_problem_report_description(self):
        """Problem-report-scoped log entry search should NOT match the report's description.

        Since the user is already viewing a specific problem report's log entries,
        searching for the report's description would be redundant and confusing -
        it would match all log entries linked to this report rather than filtering
        by log entry content.
        """
        # Report already has description "Ball is stuck in the upper playfield"
        create_log_entry(
            machine=self.machine,
            problem_report=self.report,
            text="Investigated the issue",
        )
        create_log_entry(
            machine=self.machine,
            problem_report=self.report,
            text="Replaced a component",
        )

        self.client.force_login(self.maintainer_user)

        # Search for the problem report's description text
        response = self.client.get(self.detail_url, {"q": "stuck in the upper playfield"})

        # Neither log entry should appear because problem report description
        # is not a search field in this scoped context
        self.assertNotContains(response, "Investigated the issue")
        self.assertNotContains(response, "Replaced a component")


@tag("views")
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
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.detail_url,
            {"action": "update_text", "text": "Updated description"},
        )

        self.assertEqual(response.status_code, 200)
        self.report.refresh_from_db()
        self.assertEqual(self.report.description, "Updated description")

    def test_update_text_empty(self):
        """AJAX endpoint allows empty description."""
        self.client.force_login(self.maintainer_user)

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
        self.report = create_problem_report(
            machine=self.machine,
            description="Test problem",
        )
        self.other_machine = create_machine(slug="other-machine")
        self.detail_url = reverse("problem-report-detail", kwargs={"pk": self.report.pk})

    def test_update_machine_success(self):
        """Successfully update problem report machine."""
        self.client.force_login(self.maintainer_user)

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

        self.client.force_login(self.maintainer_user)
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
        self.client.force_login(self.maintainer_user)

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
        self.client.force_login(self.maintainer_user)

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
class ProblemReportDetailLogEntriesTests(TestDataMixin, TestCase):
    """Tests for log entries display on problem report detail page."""

    def setUp(self):
        super().setUp()
        self.problem_report = create_problem_report(
            machine=self.machine,
            problem_type=ProblemReport.ProblemType.STUCK_BALL,
            description="Ball stuck",
        )
        self.detail_url = reverse("problem-report-detail", kwargs={"pk": self.problem_report.pk})

    def test_detail_page_shows_add_log_entry_button(self):
        """Problem report detail should have Add Log button."""
        self.client.force_login(self.maintainer_user)
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

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.detail_url)

        self.assertContains(response, "Investigated the issue")

    def test_detail_page_shows_no_log_entries_message(self):
        """Problem report detail should show message when no log entries exist."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.detail_url)

        self.assertContains(response, "No log entries yet")


@tag("views")
class ProblemReportLogEntriesPartialViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for the log entries AJAX endpoint on problem report detail."""

    def setUp(self):
        super().setUp()
        self.problem_report = create_problem_report(
            machine=self.machine,
            problem_type=ProblemReport.ProblemType.STUCK_BALL,
            description="Ball stuck",
        )
        self.entries_url = reverse(
            "problem-report-log-entries", kwargs={"pk": self.problem_report.pk}
        )

    def test_returns_json(self):
        """AJAX endpoint should return JSON response."""
        self.client.force_login(self.maintainer_user)
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

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.entries_url)

        data = response.json()
        self.assertIn("Linked entry", data["items"])
        self.assertNotIn("Unlinked entry", data["items"])

    def test_pagination(self):
        """AJAX endpoint should paginate results."""
        self.client.force_login(self.maintainer_user)
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
