"""Tests for maintenance app views and functionality."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from the_flip.apps.catalog.models import MachineInstance, MachineModel
from the_flip.apps.maintenance.models import ProblemReport

User = get_user_model()


class ProblemReportDetailViewTests(TestCase):
    """Tests for the problem report detail view."""

    def setUp(self):
        """Set up test data for problem report detail view tests."""
        # Create a machine model first
        self.machine_model = MachineModel.objects.create(
            name="Test Machine",
            manufacturer="Test Mfg",
            year=2020,
            era=MachineModel.ERA_SS,
        )

        # Create a machine instance
        self.machine = MachineInstance.objects.create(
            model=self.machine_model,
            slug="test-machine",
            location=MachineInstance.LOCATION_FLOOR,
            operational_status=MachineInstance.STATUS_GOOD,
        )

        # Create a problem report
        self.report = ProblemReport.objects.create(
            machine=self.machine,
            status=ProblemReport.STATUS_OPEN,
            problem_type=ProblemReport.PROBLEM_STUCK_BALL,
            description="Ball is stuck in the upper playfield",
            reported_by_name="John Doe",
            reported_by_contact="john@example.com",
            device_info="iPhone 12",
            ip_address="192.168.1.1",
        )

        # Create staff user (maintainer)
        self.staff_user = User.objects.create_user(
            username="staffuser",
            password="testpass123",
            is_staff=True,
        )

        # Create regular user (non-staff)
        self.regular_user = User.objects.create_user(
            username="regularuser",
            password="testpass123",
            is_staff=False,
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
        """Detail page should display all report information."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.detail_url)

        self.assertContains(response, self.machine.display_name)
        self.assertContains(response, "Stuck Ball")
        self.assertContains(response, "Ball is stuck in the upper playfield")
        self.assertContains(response, "John Doe")
        self.assertContains(response, "john@example.com")
        self.assertContains(response, "iPhone 12")
        self.assertContains(response, "192.168.1.1")
        self.assertContains(response, "Open")

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

        # Verify status was not changed
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, ProblemReport.STATUS_OPEN)

    def test_status_toggle_from_open_to_closed(self):
        """Staff users should be able to close an open report."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.post(self.detail_url)

        # Should redirect back to detail page
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.detail_url)

        # Verify status was toggled to closed
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, ProblemReport.STATUS_CLOSED)

    def test_status_toggle_from_closed_to_open(self):
        """Staff users should be able to re-open a closed report."""
        self.report.status = ProblemReport.STATUS_CLOSED
        self.report.save()

        self.client.login(username="staffuser", password="testpass123")
        response = self.client.post(self.detail_url)

        # Should redirect back to detail page
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.detail_url)

        # Verify status was toggled to open
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, ProblemReport.STATUS_OPEN)

    def test_status_toggle_shows_close_message(self):
        """Closing a report should show appropriate success message."""
        self.client.login(username="staffuser", password="testpass123")

        # Close the report
        response = self.client.post(self.detail_url, follow=True)
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), "Problem report closed.")

    def test_status_toggle_shows_reopen_message(self):
        """Re-opening a report should show appropriate success message."""
        self.report.status = ProblemReport.STATUS_CLOSED
        self.report.save()

        self.client.login(username="staffuser", password="testpass123")

        # Re-open the report
        response = self.client.post(self.detail_url, follow=True)
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), "Problem report re-opened.")


class ProblemReportListViewTests(TestCase):
    """Tests for the global problem report list view."""

    def setUp(self):
        """Set up test data for list view tests."""
        # Create a machine model first
        self.machine_model = MachineModel.objects.create(
            name="Test Machine",
            manufacturer="Test Mfg",
            year=2020,
            era=MachineModel.ERA_SS,
        )

        # Create a machine instance
        self.machine = MachineInstance.objects.create(
            model=self.machine_model,
            slug="test-machine",
            location=MachineInstance.LOCATION_FLOOR,
            operational_status=MachineInstance.STATUS_GOOD,
        )

        self.report = ProblemReport.objects.create(
            machine=self.machine,
            status=ProblemReport.STATUS_OPEN,
            problem_type=ProblemReport.PROBLEM_OTHER,
            description="Test problem",
        )

        self.staff_user = User.objects.create_user(
            username="staffuser",
            password="testpass123",
            is_staff=True,
        )

        self.regular_user = User.objects.create_user(
            username="regularuser",
            password="testpass123",
            is_staff=False,
        )

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


class MachineProblemReportListViewTests(TestCase):
    """Tests for the machine-specific problem report list view."""

    def setUp(self):
        """Set up test data for machine problem report list view tests."""
        # Create a machine model first
        self.machine_model = MachineModel.objects.create(
            name="Test Machine",
            manufacturer="Test Mfg",
            year=2020,
            era=MachineModel.ERA_SS,
        )

        # Create a machine instance
        self.machine = MachineInstance.objects.create(
            model=self.machine_model,
            slug="test-machine",
            location=MachineInstance.LOCATION_FLOOR,
            operational_status=MachineInstance.STATUS_GOOD,
        )

        self.report = ProblemReport.objects.create(
            machine=self.machine,
            status=ProblemReport.STATUS_OPEN,
            problem_type=ProblemReport.PROBLEM_OTHER,
            description="Test problem",
        )

        self.staff_user = User.objects.create_user(
            username="staffuser",
            password="testpass123",
            is_staff=True,
        )

        self.machine_list_url = reverse("machine-problem-reports", kwargs={"slug": self.machine.slug})

    def test_machine_list_view_contains_link_to_detail(self):
        """Machine-specific list view should contain links to detail pages."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.machine_list_url)

        detail_url = reverse("problem-report-detail", kwargs={"pk": self.report.pk})
        self.assertContains(response, detail_url)
