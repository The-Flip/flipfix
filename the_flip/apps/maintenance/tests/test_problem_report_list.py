"""Tests for problem report list views and search functionality."""

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TestDataMixin,
    create_log_entry,
    create_maintainer_user,
    create_problem_report,
)


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
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "maintenance/problem_report_list.html")

    def test_list_view_contains_link_to_detail(self):
        """List view should contain links to detail pages."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url)

        detail_url = reverse("problem-report-detail", kwargs={"pk": self.report.pk})
        self.assertContains(response, detail_url)

    def test_list_view_pagination(self):
        """List view should paginate results."""
        self.client.force_login(self.maintainer_user)
        for i in range(15):
            create_problem_report(machine=self.machine, description=f"Problem {i}")

        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["reports"]), 10)
        self.assertTrue(response.context["page_obj"].has_next())

    def test_list_view_search_by_description(self):
        """List view should filter by description text."""
        self.client.force_login(self.maintainer_user)
        create_problem_report(machine=self.machine, description="Unique flippers broken")

        response = self.client.get(self.list_url, {"q": "flippers"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["reports"]), 1)
        self.assertContains(response, "Unique flippers broken")

    def test_list_view_search_by_machine_name(self):
        """List view should filter by machine model name."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url, {"q": "Test Machine"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["reports"]), 1)

    def test_list_view_search_no_results(self):
        """List view should show empty message when search has no results."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url, {"q": "nonexistent"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["reports"]), 0)
        self.assertContains(response, "No problem reports match your search")

    def test_list_view_search_matches_log_entry_text(self):
        """List search should include attached log entry text."""
        create_log_entry(machine=self.machine, problem_report=self.report, text="Fixed coil stop")
        other_report = create_problem_report(machine=self.machine, description="Other issue")
        create_log_entry(machine=self.machine, problem_report=other_report, text="Different work")

        self.client.force_login(self.maintainer_user)
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

        self.client.force_login(self.maintainer_user)
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

        self.client.force_login(self.maintainer_user)
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
        self.client.force_login(self.maintainer_user)
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
        self.client.force_login(self.maintainer_user)
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
        self.client.force_login(self.maintainer_user)
        create_problem_report(machine=self.machine, description="Flipper issue")
        create_problem_report(machine=self.machine, description="Display broken")

        response = self.client.get(self.entries_url, {"q": "Flipper"})
        data = response.json()
        self.assertIn("Flipper issue", data["items"])
        self.assertNotIn("Display broken", data["items"])

    def test_partial_view_search_matches_log_entry_text(self):
        """AJAX endpoint search should include attached log entry text."""
        self.client.force_login(self.maintainer_user)
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
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.machine_list_url)

        detail_url = reverse("problem-report-detail", kwargs={"pk": self.report.pk})
        self.assertContains(response, detail_url)

    def test_machine_list_search_does_not_match_machine_name(self):
        """Machine-scoped problem report search should NOT match the machine name.

        Since the user is already viewing a specific machine's problem reports,
        searching for the machine name would be redundant and confusing - it would
        match all reports on that machine rather than filtering by content.
        """
        from the_flip.apps.catalog.models import MachineModel
        from the_flip.apps.core.test_utils import create_machine

        # Create a machine with a distinctive name
        unique_model = MachineModel.objects.create(name="Medieval Madness 1997")
        unique_machine = create_machine(slug="medieval-madness", model=unique_model)

        # Create problem reports on this machine
        create_problem_report(machine=unique_machine, description="Flipper issue")
        create_problem_report(machine=unique_machine, description="Display problem")

        self.client.force_login(self.maintainer_user)
        list_url = reverse("machine-problem-reports", kwargs={"slug": unique_machine.slug})

        # Search for machine name should NOT return results
        response = self.client.get(list_url, {"q": "Medieval Madness"})

        # Neither report should appear because machine name is not a search field
        self.assertNotContains(response, "Flipper issue")
        self.assertNotContains(response, "Display problem")


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

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url, {"q": "Submitting"})

        self.assertContains(response, "Flipper not working")
