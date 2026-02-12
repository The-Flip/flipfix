"""Tests for machine list views."""

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.core.test_utils import (
    AccessControlTestCase,
    create_machine,
    create_maintainer_user,
    create_user,
)


@tag("views")
class MaintainerMachineListViewTests(AccessControlTestCase):
    """Tests for maintainer machine list view access control."""

    def setUp(self):
        """Set up test data."""
        self.maintainer_user = create_maintainer_user()
        self.regular_user = create_user()
        self.machine = create_machine(slug="test-machine")

        self.list_url = reverse("maintainer-machine-list")

    def test_list_view_requires_authentication(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_list_view_requires_maintainer_access(self):
        """Non-maintainer users should be denied access (403)."""
        self.client.force_login(self.regular_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    def test_list_view_accessible_to_maintainer(self):
        """Maintainer users should be able to access the list page."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)


@tag("views")
class PublicMachineListViewTests(TestCase):
    """Tests for public-facing machine list view."""

    def setUp(self):
        """Set up test data for public views."""
        self.machine = create_machine(slug="public-machine")
        self.list_url = reverse("public-machine-list")

    def test_public_list_view_accessible(self):
        """Public list view should be accessible to anonymous users."""
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "catalog/machine_list_public.html")

    def test_public_list_view_displays_machine(self):
        """Public list view should display visible machines."""
        response = self.client.get(self.list_url)
        self.assertContains(response, self.machine.name)


@tag("views")
class MaintainerMachineListEdgeCaseTests(TestCase):
    """Edge case tests for maintainer machine list view."""

    def setUp(self):
        """Set up test data."""
        self.maintainer_user = create_maintainer_user()
        self.superuser = create_user(username="admin", is_superuser=True, is_staff=True)
        self.list_url = reverse("maintainer-machine-list")

    def test_new_machine_button_visible_for_superuser(self):
        """New Machine button should be visible only for superusers."""
        self.client.force_login(self.superuser)
        response = self.client.get(self.list_url)
        create_url = reverse("machine-create-landing")
        self.assertContains(response, create_url)
        self.assertContains(response, "New Machine")

    def test_new_machine_button_hidden_for_maintainer(self):
        """New Machine button should be hidden for non-superuser maintainers."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url)
        create_url = reverse("machine-create-landing")
        self.assertNotContains(response, create_url)

    def test_empty_machine_list(self):
        """Should show empty state when no machines exist."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url)
        self.assertContains(response, "No machines yet")

    def test_machine_list_with_multiple_machines(self):
        """Should display multiple machines in the list."""
        machine1 = create_machine(slug="machine-1")
        machine2 = create_machine(slug="machine-2")
        machine3 = create_machine(slug="machine-3")

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url)
        self.assertContains(response, machine1.name)
        self.assertContains(response, machine2.name)
        self.assertContains(response, machine3.name)

    def test_machine_list_search_box_present(self):
        """Machine list should have a search input."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url)
        self.assertContains(response, 'id="machine-search"')
        self.assertContains(response, 'placeholder="Search machines..."')

    def test_machine_list_card_partial_included(self):
        """Machine list should include machine card partial for each machine."""
        machine = create_machine(slug="test-machine")
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url)
        # Should render the machine card with machine name
        self.assertContains(response, machine.name)