"""Tests for problem report autocomplete API."""

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TestDataMixin,
    create_machine,
    create_problem_report,
)
from the_flip.apps.maintenance.models import ProblemReport


@tag("views")
class ProblemReportAutocompleteViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for the problem report autocomplete API."""

    def setUp(self):
        super().setUp()
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
        self.report1.status = ProblemReport.Status.CLOSED
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
