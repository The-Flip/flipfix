"""Tests for the global activity feed (GlobalActivityFeedView).

The global feed shows all activity across all machines and is the home page
for maintainers.
"""

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.core.test_utils import (
    TestDataMixin,
    create_log_entry,
    create_machine,
    create_machine_model,
    create_maintainer_user,
    create_problem_report,
    create_user,
)
from the_flip.apps.parts.models import PartRequest


@tag("views")
class GlobalFeedAccessControlTests(TestCase):
    """Tests for global feed access control."""

    def setUp(self):
        self.maintainer_user = create_maintainer_user()
        self.regular_user = create_user()
        self.home_url = reverse("home")

    def test_shows_public_home_for_anonymous(self):
        """Anonymous users see public home page."""
        response = self.client.get(self.home_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home.html")

    def test_shows_public_home_for_non_maintainer(self):
        """Non-maintainer users see public home page."""
        self.client.force_login(self.regular_user)
        response = self.client.get(self.home_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home.html")

    def test_shows_feed_for_maintainer(self):
        """Maintainers see global activity feed."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.home_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/global_activity_feed.html")


@tag("views")
class GlobalFeedContentTests(TestDataMixin, TestCase):
    """Tests for global feed content display."""

    def setUp(self):
        super().setUp()
        self.home_url = reverse("home")

        # Create entries on different machines
        self.machine2 = create_machine(slug="machine-two")
        self.log = create_log_entry(machine=self.machine, text="Fixed the flipper")
        self.problem = create_problem_report(
            machine=self.machine2, description="Ball stuck in drain"
        )
        self.part_request = PartRequest.objects.create(
            machine=self.machine, text="Need new rubber rings"
        )

    def test_feed_shows_entries_from_multiple_machines(self):
        """Global feed should show entries from all machines."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.home_url)

        self.assertContains(response, "Fixed the flipper")
        self.assertContains(response, "Ball stuck in drain")
        self.assertContains(response, "Need new rubber rings")

    def test_feed_shows_machine_names(self):
        """Global feed entries should display their machine names."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.home_url)

        # Both machine names should appear
        self.assertContains(response, self.machine.short_display_name)
        self.assertContains(response, self.machine2.short_display_name)


@tag("views")
class GlobalFeedSearchTests(TestDataMixin, TestCase):
    """Tests for global feed search functionality."""

    def setUp(self):
        super().setUp()
        self.home_url = reverse("home")

        # Create entries with searchable content
        self.log = create_log_entry(machine=self.machine, text="Replaced flipper coil")
        self.problem = create_problem_report(machine=self.machine, description="Display flickering")

    def test_search_finds_log_by_text(self):
        """Search should find log entries by text content."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.home_url, {"q": "flipper"})

        self.assertContains(response, "Replaced flipper coil")
        self.assertNotContains(response, "Display flickering")

    def test_search_finds_problem_by_description(self):
        """Search should find problem reports by description."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.home_url, {"q": "flickering"})

        self.assertNotContains(response, "Replaced flipper coil")
        self.assertContains(response, "Display flickering")

    def test_search_finds_entries_by_machine_name(self):
        """Global search should find entries by machine name."""
        unique_model = create_machine_model(name="Medieval Madness 1997")
        unique_machine = create_machine(slug="medieval-madness", model=unique_model)
        create_log_entry(machine=unique_machine, text="Adjusted castle targets")

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.home_url, {"q": "Medieval"})

        self.assertContains(response, "Adjusted castle targets")


@tag("views")
class GlobalFeedStatsTests(TestDataMixin, TestCase):
    """Tests for global feed sidebar statistics."""

    def setUp(self):
        super().setUp()
        self.home_url = reverse("home")

    def test_stats_show_open_problems_count(self):
        """Stats should show count of open problem reports."""
        create_problem_report(machine=self.machine, description="Problem 1")
        create_problem_report(machine=self.machine, description="Problem 2")

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.home_url)

        self.assertContains(response, "Open Problems")
        # The count should appear in the stats grid
        self.assertContains(response, ">2<")

    def test_stats_show_parts_reqd(self):
        """Parts Req'd stat should appear in sidebar."""
        PartRequest.objects.create(
            machine=self.machine,
            text="Need flipper",
            status=PartRequest.Status.REQUESTED,
        )

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.home_url)

        self.assertContains(response, "Parts Req&#x27;d")


@tag("views")
class GlobalFeedPartialViewTests(TestDataMixin, TestCase):
    """Tests for the AJAX pagination endpoint."""

    def setUp(self):
        super().setUp()
        self.partial_url = reverse("global-activity-feed-entries")

        # Create some entries for pagination
        for i in range(5):
            create_log_entry(machine=self.machine, text=f"Log entry {i}")

    def test_partial_requires_authentication(self):
        """Partial view should redirect anonymous users to login."""
        response = self.client.get(self.partial_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_partial_requires_maintainer_access(self):
        """Partial view should deny access to non-maintainers."""
        regular_user = create_user()
        self.client.force_login(regular_user)
        with self.assertLogs("django.request", level="WARNING"):
            response = self.client.get(self.partial_url)
        self.assertEqual(response.status_code, 403)

    def test_partial_returns_json(self):
        """Partial view should return JSON response."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.partial_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

    def test_partial_returns_items_html(self):
        """Partial view should return rendered HTML in items field."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.partial_url)

        data = response.json()
        self.assertIn("items", data)
        self.assertIn("Log entry", data["items"])

    def test_partial_returns_pagination_info(self):
        """Partial view should return has_next and next_page fields."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.partial_url)

        data = response.json()
        self.assertIn("has_next", data)
        self.assertIn("next_page", data)

    def test_partial_respects_page_param(self):
        """Partial view should respect the page query parameter."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.partial_url, {"page": 2})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Page 2 with default page size should work
        self.assertIsInstance(data["items"], str)
