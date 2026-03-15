"""Tests for machine list views."""

from django.test import TestCase, tag
from django.urls import reverse

from flipfix.apps.catalog.models import Location, MachineInstance
from flipfix.apps.core.test_utils import (
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

    def test_non_maintainer_can_browse_public_route(self):
        """Non-maintainer users can browse public routes (read-only)."""
        self.client.force_login(self.regular_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)

    def test_list_view_accessible_to_maintainer(self):
        """Maintainer users should be able to access the list page."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)


@tag("views")
class MachineListFilterTests(TestCase):
    """Tests for machine list filtering by status and location."""

    def setUp(self):
        self.user = create_maintainer_user()
        self.client.force_login(self.user)
        self.url = reverse("maintainer-machine-list")

        self.floor, _ = Location.objects.get_or_create(slug="floor", defaults={"name": "Floor"})
        self.workshop, _ = Location.objects.get_or_create(
            slug="workshop", defaults={"name": "Workshop"}
        )

        self.good_floor = create_machine(
            slug="good-floor",
            operational_status=MachineInstance.OperationalStatus.GOOD,
        )
        self.good_floor.location = self.floor
        self.good_floor.save()

        self.fixing_floor = create_machine(
            slug="fixing-floor",
            operational_status=MachineInstance.OperationalStatus.FIXING,
        )
        self.fixing_floor.location = self.floor
        self.fixing_floor.save()

        self.broken_workshop = create_machine(
            slug="broken-workshop",
            operational_status=MachineInstance.OperationalStatus.BROKEN,
        )
        self.broken_workshop.location = self.workshop
        self.broken_workshop.save()

    def test_filter_by_status(self):
        """?status=fixing shows only fixing machines."""
        response = self.client.get(self.url + "?status=fixing")
        machines = list(response.context["machines"])
        self.assertEqual(len(machines), 1)
        self.assertEqual(machines[0].slug, "fixing-floor")

    def test_filter_by_location(self):
        """?location=floor shows only floor machines."""
        response = self.client.get(self.url + "?location=floor")
        machines = list(response.context["machines"])
        self.assertEqual(len(machines), 2)
        slugs = {m.slug for m in machines}
        self.assertEqual(slugs, {"good-floor", "fixing-floor"})

    def test_filter_by_status_and_location(self):
        """Both params combined narrow results."""
        response = self.client.get(self.url + "?status=good&location=floor")
        machines = list(response.context["machines"])
        self.assertEqual(len(machines), 1)
        self.assertEqual(machines[0].slug, "good-floor")

    def test_invalid_filter_ignored(self):
        """?status=bogus shows all machines."""
        response = self.client.get(self.url + "?status=bogus")
        machines = list(response.context["machines"])
        self.assertEqual(len(machines), 3)

    def test_stats_show_unfiltered_counts(self):
        """Stat values reflect unfiltered totals even when filtered."""
        response = self.client.get(self.url + "?status=fixing")
        status_stats = response.context["status_stats"]
        # "All" stat should show total count, not filtered count
        all_stat = next(s for s in status_stats if s["label"] == "All")
        self.assertEqual(all_stat["value"], 3)

    def test_active_stat_highlighted(self):
        """The active filter stat has active=True."""
        response = self.client.get(self.url + "?status=fixing")
        status_stats = response.context["status_stats"]
        fixing_stat = next(s for s in status_stats if s["label"] == "Fixing")
        all_stat = next(s for s in status_stats if s["label"] == "All")
        self.assertTrue(fixing_stat["active"])
        self.assertFalse(all_stat["active"])

    def test_stat_links_present(self):
        """Stat grid contains filter URLs."""
        response = self.client.get(self.url)
        status_stats = response.context["status_stats"]
        fixing_stat = next(s for s in status_stats if s["label"] == "Fixing")
        self.assertIn("status=fixing", fixing_stat["url"])

    def test_all_link_clears_filter(self):
        """'All' stat links to unfiltered view."""
        response = self.client.get(self.url + "?status=fixing")
        status_stats = response.context["status_stats"]
        all_stat = next(s for s in status_stats if s["label"] == "All")
        self.assertNotIn("status=", all_stat["url"])
