"""Tests for machine detail views."""

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.core.test_utils import (
    AccessControlTestCase,
    create_machine,
    create_maintainer_user,
    create_user,
)


@tag("views")
class MaintainerMachineDetailViewTests(AccessControlTestCase):
    """Tests for maintainer machine detail view access control."""

    def setUp(self):
        """Set up test data."""
        self.maintainer_user = create_maintainer_user()
        self.regular_user = create_user()
        self.machine = create_machine(slug="test-machine")

        self.detail_url = reverse("maintainer-machine-detail", kwargs={"slug": self.machine.slug})

    def test_detail_view_requires_authentication(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_detail_view_requires_maintainer_access(self):
        """Non-maintainer users should be denied access (403)."""
        self.client.force_login(self.regular_user)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 403)

    def test_detail_view_accessible_to_maintainer(self):
        """Maintainer users should be able to access the detail page."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)


@tag("views")
class PublicMachineDetailViewTests(TestCase):
    """Tests for public-facing machine detail view."""

    def setUp(self):
        """Set up test data for public views."""
        self.machine = create_machine(slug="public-machine")
        self.detail_url = reverse("public-machine-detail", kwargs={"slug": self.machine.slug})

    def test_public_detail_view_accessible(self):
        """Public detail view should be accessible to anonymous users."""
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "catalog/machine_detail_public.html")

    def test_public_detail_view_displays_machine_details(self):
        """Public detail view should display machine-specific details."""
        response = self.client.get(self.detail_url)
        self.assertContains(response, self.machine.name)
        self.assertContains(response, self.machine.model.manufacturer)


@tag("views")
class MachineActivitySearchTests(TestCase):
    """Tests for machine activity feed search including free-text name fields."""

    def setUp(self):
        self.maintainer_user = create_maintainer_user()
        self.machine = create_machine(slug="test-machine")
        self.detail_url = reverse("maintainer-machine-detail", kwargs={"slug": self.machine.slug})

    def test_search_finds_log_entry_by_maintainer_names(self):
        """Activity search should find log entries by free-text maintainer names."""
        from the_flip.apps.core.test_utils import create_log_entry

        create_log_entry(
            machine=self.machine,
            text="Replaced flipper",
            maintainer_names="Wandering Willie",
        )

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.detail_url, {"q": "Wandering"})

        self.assertContains(response, "Replaced flipper")

    def test_search_finds_problem_report_by_reporter_name(self):
        """Activity search should find problem reports by free-text reporter name."""
        from the_flip.apps.core.test_utils import create_problem_report

        create_problem_report(
            machine=self.machine,
            description="Lights flickering",
            reported_by_name="Visiting Vera",
        )

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.detail_url, {"q": "Visiting"})

        self.assertContains(response, "Lights flickering")

    def test_search_finds_part_request_by_requester_name(self):
        """Activity search should find part requests by free-text requester name."""
        from constance.test import override_config

        from the_flip.apps.parts.models import PartRequest

        PartRequest.objects.create(
            machine=self.machine,
            text="Need new rubber rings",
            requested_by_name="Requisitioning Ralph",
        )

        self.client.force_login(self.maintainer_user)
        with override_config(PARTS_ENABLED=True):
            response = self.client.get(self.detail_url, {"q": "Requisitioning"})

        self.assertContains(response, "Need new rubber rings")

    def test_search_finds_part_update_by_poster_name(self):
        """Activity search should find part request updates by free-text poster name."""
        from constance.test import override_config

        from the_flip.apps.parts.models import PartRequest, PartRequestUpdate

        part_request = PartRequest.objects.create(
            machine=self.machine,
            text="Flipper coil",
        )
        PartRequestUpdate.objects.create(
            part_request=part_request,
            text="Ordered from Marco",
            posted_by_name="Updating Ursula",
        )

        self.client.force_login(self.maintainer_user)
        with override_config(PARTS_ENABLED=True):
            response = self.client.get(self.detail_url, {"q": "Updating"})

        self.assertContains(response, "Ordered from Marco")

    def test_search_finds_problem_report_by_log_entry_maintainer_names(self):
        """Activity search should find problem reports by their log entry's free-text maintainer names."""
        from the_flip.apps.core.test_utils import create_log_entry, create_problem_report

        report = create_problem_report(
            machine=self.machine,
            description="Ball stuck in gutter",
        )
        create_log_entry(
            machine=self.machine,
            problem_report=report,
            text="Cleared the ball",
            maintainer_names="Wandering Willie",
        )

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.detail_url, {"q": "Wandering"})

        self.assertContains(response, "Ball stuck in gutter")

    def test_search_finds_log_entry_by_maintainer_fk(self):
        """Activity search should find log entries by FK maintainer name."""
        from the_flip.apps.accounts.models import Maintainer
        from the_flip.apps.core.test_utils import create_log_entry

        maintainer = Maintainer.objects.get(user=self.maintainer_user)
        log = create_log_entry(
            machine=self.machine,
            text="Fixed the flipper",
        )
        log.maintainers.add(maintainer)

        self.client.force_login(self.maintainer_user)
        # Search by maintainer's first name
        response = self.client.get(self.detail_url, {"q": self.maintainer_user.first_name})

        self.assertContains(response, "Fixed the flipper")
