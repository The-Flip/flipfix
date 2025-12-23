"""Tests for log entry list views and search."""

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.catalog.models import MachineModel
from the_flip.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TestDataMixin,
    create_log_entry,
    create_machine,
    create_problem_report,
)


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

    def test_search_does_not_match_machine_name(self):
        """Machine-scoped search should NOT match the machine name.

        Since the user is already viewing a specific machine's logs, searching
        for the machine name would be redundant and confusing - it would match
        all logs on that machine rather than filtering by content.
        """
        # Create a machine with a distinctive name
        unique_model = MachineModel.objects.create(name="Twilight Zone 1993")
        unique_machine = create_machine(slug="twilight-zone", model=unique_model)

        # Create log entries on this machine
        create_log_entry(machine=unique_machine, text="Replaced flipper coil")
        create_log_entry(machine=unique_machine, text="Adjusted targets")

        self.client.force_login(self.staff_user)
        list_url = reverse("log-machine", kwargs={"slug": unique_machine.slug})

        # Search for machine name should NOT return results
        response = self.client.get(list_url, {"q": "Twilight Zone"})

        # Neither log entry should appear because machine name is not a search field
        self.assertNotContains(response, "Replaced flipper coil")
        self.assertNotContains(response, "Adjusted targets")


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
