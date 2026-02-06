"""Tests for the unified machine feed view (MachineFeedView).

This view handles four URL patterns via query params:
- /machines/slug/ → all activity (default)
- /machines/slug/?f=logs → log entries only
- /machines/slug/?f=problems → problem reports only
- /machines/slug/?f=parts → parts requests and updates only
"""

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.views_inline import MachineInlineUpdateView
from the_flip.apps.core.test_utils import (
    AccessControlTestCase,
    TestDataMixin,
    create_log_entry,
    create_machine,
    create_machine_model,
    create_maintainer_user,
    create_problem_report,
    create_user,
)
from the_flip.apps.maintenance.models import LogEntryMedia
from the_flip.apps.parts.models import PartRequest, PartRequestUpdate


@tag("views")
class MachineFeedAccessControlTests(AccessControlTestCase):
    """Tests for machine feed view access control."""

    def setUp(self):
        self.maintainer_user = create_maintainer_user()
        self.regular_user = create_user()
        self.machine = create_machine(slug="test-machine")
        self.feed_url = reverse("maintainer-machine-detail", kwargs={"slug": self.machine.slug})

    def test_requires_authentication(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get(self.feed_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_requires_maintainer_access(self):
        """Non-maintainer users should be denied access (403)."""
        self.client.force_login(self.regular_user)
        response = self.client.get(self.feed_url)
        self.assertEqual(response.status_code, 403)

    def test_accessible_to_maintainer(self):
        """Maintainer users should be able to access the feed."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.feed_url)
        self.assertEqual(response.status_code, 200)


@tag("views")
class MachineFeedFilterTests(TestDataMixin, TestCase):
    """Tests for feed filter switching via query params."""

    def setUp(self):
        super().setUp()
        self.feed_url = reverse("maintainer-machine-detail", kwargs={"slug": self.machine.slug})

        # Create one of each entry type
        self.log = create_log_entry(machine=self.machine, text="Test log entry")
        self.problem = create_problem_report(machine=self.machine, description="Test problem")
        self.part_request = PartRequest.objects.create(
            machine=self.machine, text="Test part request"
        )

    def test_all_filter_shows_all_entry_types(self):
        """Default filter (all) should show logs, problems, and parts."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.feed_url)

        self.assertContains(response, "Test log entry")
        self.assertContains(response, "Test problem")
        self.assertContains(response, "Test part request")

    def test_logs_filter_shows_only_logs(self):
        """Logs filter should show only log entries."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.feed_url, {"f": "logs"})

        self.assertContains(response, "Test log entry")
        self.assertNotContains(response, "Test problem")
        self.assertNotContains(response, "Test part request")

    def test_problems_filter_shows_only_problems(self):
        """Problems filter should show only problem reports."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.feed_url, {"f": "problems"})

        self.assertNotContains(response, "Test log entry")
        self.assertContains(response, "Test problem")
        self.assertNotContains(response, "Test part request")

    def test_parts_filter_shows_only_parts(self):
        """Parts filter should show only parts requests and updates."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.feed_url, {"f": "parts"})

        self.assertNotContains(response, "Test log entry")
        self.assertNotContains(response, "Test problem")
        self.assertContains(response, "Test part request")

    def test_invalid_filter_defaults_to_all(self):
        """Invalid filter value should default to showing all entries."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.feed_url, {"f": "invalid"})

        self.assertContains(response, "Test log entry")
        self.assertContains(response, "Test problem")
        self.assertContains(response, "Test part request")


@tag("views")
class MachineFeedSearchTests(TestDataMixin, TestCase):
    """Tests for machine feed search across all entry types."""

    def setUp(self):
        super().setUp()
        self.feed_url = reverse("maintainer-machine-detail", kwargs={"slug": self.machine.slug})

    def test_search_finds_log_by_text(self):
        """Search should find log entries by text content."""
        create_log_entry(machine=self.machine, text="Replaced flipper coil")
        create_log_entry(machine=self.machine, text="Adjusted targets")

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.feed_url, {"q": "flipper"})

        self.assertContains(response, "Replaced flipper coil")
        self.assertNotContains(response, "Adjusted targets")

    def test_search_finds_log_by_maintainer_names(self):
        """Search should find log entries by free-text maintainer names."""
        create_log_entry(
            machine=self.machine,
            text="Replaced flipper",
            maintainer_names="Wandering Willie",
        )

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.feed_url, {"q": "Wandering"})

        self.assertContains(response, "Replaced flipper")

    def test_search_finds_log_by_maintainer_fk(self):
        """Search should find log entries by FK maintainer name."""
        maintainer = Maintainer.objects.get(user=self.maintainer_user)
        log = create_log_entry(machine=self.machine, text="Fixed the flipper")
        log.maintainers.add(maintainer)

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.feed_url, {"q": self.maintainer_user.first_name})

        self.assertContains(response, "Fixed the flipper")

    def test_search_finds_problem_by_description(self):
        """Search should find problem reports by description."""
        create_problem_report(machine=self.machine, description="Lights flickering badly")
        create_problem_report(machine=self.machine, description="Ball stuck")

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.feed_url, {"q": "flickering"})

        self.assertContains(response, "Lights flickering badly")
        self.assertNotContains(response, "Ball stuck")

    def test_search_finds_problem_by_reporter_name(self):
        """Search should find problem reports by free-text reporter name."""
        create_problem_report(
            machine=self.machine,
            description="Lights flickering",
            reported_by_name="Visiting Vera",
        )

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.feed_url, {"q": "Visiting"})

        self.assertContains(response, "Lights flickering")

    def test_search_finds_problem_by_log_entry_maintainer_names(self):
        """Search should find problem reports by their log entry's maintainer names."""
        report = create_problem_report(machine=self.machine, description="Ball stuck in gutter")
        create_log_entry(
            machine=self.machine,
            problem_report=report,
            text="Cleared the ball",
            maintainer_names="Wandering Willie",
        )

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.feed_url, {"q": "Wandering"})

        self.assertContains(response, "Ball stuck in gutter")

    def test_search_finds_part_request_by_requester_name(self):
        """Search should find part requests by free-text requester name."""
        PartRequest.objects.create(
            machine=self.machine,
            text="Need new rubber rings",
            requested_by_name="Requisitioning Ralph",
        )

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.feed_url, {"q": "Requisitioning"})

        self.assertContains(response, "Need new rubber rings")

    def test_search_finds_part_update_by_poster_name(self):
        """Search should find part request updates by free-text poster name."""
        part_request = PartRequest.objects.create(machine=self.machine, text="Flipper coil")
        PartRequestUpdate.objects.create(
            part_request=part_request,
            text="Ordered from Marco",
            posted_by_name="Updating Ursula",
        )

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.feed_url, {"q": "Updating"})

        self.assertContains(response, "Ordered from Marco")

    def test_search_does_not_match_machine_name(self):
        """Machine-scoped search should NOT match the machine name.

        Since the user is already viewing a specific machine's feed, searching
        for the machine name would be redundant and confusing.
        """
        unique_model = create_machine_model(name="Medieval Madness 1997")
        unique_machine = create_machine(slug="medieval-madness", model=unique_model)
        create_log_entry(machine=unique_machine, text="Replaced flipper coil")
        create_problem_report(machine=unique_machine, description="Display problem")

        self.client.force_login(self.maintainer_user)
        feed_url = reverse("maintainer-machine-detail", kwargs={"slug": unique_machine.slug})
        response = self.client.get(feed_url, {"q": "Medieval Madness"})

        # Neither entry should appear because machine name is not a search field
        self.assertNotContains(response, "Replaced flipper coil")
        self.assertNotContains(response, "Display problem")


@tag("views")
class MachineFeedFilteredSearchTests(TestDataMixin, TestCase):
    """Tests for search within a specific filter (e.g., ?f=logs&q=...)."""

    def setUp(self):
        super().setUp()
        self.feed_url = reverse("maintainer-machine-detail", kwargs={"slug": self.machine.slug})

    def test_logs_filter_search_includes_problem_report_description(self):
        """Logs filter search should match attached problem report description."""
        report = create_problem_report(machine=self.machine, description="Coil stop broken")
        log_with_report = create_log_entry(
            machine=self.machine,
            text="Investigated noisy coil",
            problem_report=report,
        )
        create_log_entry(machine=self.machine, text="Adjusted flipper alignment")

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.feed_url, {"f": "logs", "q": "coil stop"})

        self.assertContains(response, log_with_report.text)
        self.assertNotContains(response, "Adjusted flipper alignment")

    def test_logs_filter_search_includes_problem_report_reporter_name(self):
        """Logs filter search should match problem report's reporter name."""
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

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.feed_url, {"f": "logs", "q": "Visiting"})

        self.assertContains(response, log_with_report.text)
        self.assertNotContains(response, "Adjusted flipper alignment")

    def test_logs_filter_search_does_not_match_machine_name(self):
        """Logs filter search should NOT match the machine name."""
        unique_model = create_machine_model(name="Twilight Zone 1993")
        unique_machine = create_machine(slug="twilight-zone", model=unique_model)
        create_log_entry(machine=unique_machine, text="Replaced flipper coil")
        create_log_entry(machine=unique_machine, text="Adjusted targets")

        self.client.force_login(self.maintainer_user)
        feed_url = reverse("maintainer-machine-detail", kwargs={"slug": unique_machine.slug})
        response = self.client.get(feed_url, {"f": "logs", "q": "Twilight Zone"})

        self.assertNotContains(response, "Replaced flipper coil")
        self.assertNotContains(response, "Adjusted targets")

    def test_problems_filter_search_does_not_match_machine_name(self):
        """Problems filter search should NOT match the machine name."""
        unique_model = create_machine_model(name="Medieval Madness 1997")
        unique_machine = create_machine(slug="medieval-madness", model=unique_model)
        create_problem_report(machine=unique_machine, description="Flipper issue")
        create_problem_report(machine=unique_machine, description="Display problem")

        self.client.force_login(self.maintainer_user)
        feed_url = reverse("maintainer-machine-detail", kwargs={"slug": unique_machine.slug})
        response = self.client.get(feed_url, {"f": "problems", "q": "Medieval Madness"})

        self.assertNotContains(response, "Flipper issue")
        self.assertNotContains(response, "Display problem")


@tag("views")
class MachineFeedBreadcrumbTests(TestDataMixin, TestCase):
    """Tests for feed breadcrumb and title rendering."""

    def setUp(self):
        super().setUp()
        self.feed_url = reverse("maintainer-machine-detail", kwargs={"slug": self.machine.slug})

    def test_all_filter_has_no_breadcrumb_suffix(self):
        """Default (all) filter should not add a breadcrumb suffix."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.feed_url)

        # Machine name is last breadcrumb (no suffix)
        self.assertContains(response, f"<span>{self.machine.short_display_name}</span>")

    def test_logs_filter_has_logs_breadcrumb(self):
        """Logs filter should show 'Logs' breadcrumb."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.feed_url, {"f": "logs"})

        self.assertContains(response, "<span>Logs</span>")

    def test_problems_filter_has_problems_breadcrumb(self):
        """Problems filter should show 'Problems' breadcrumb."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.feed_url, {"f": "problems"})

        self.assertContains(response, "<span>Problems</span>")

    def test_parts_filter_has_parts_breadcrumb(self):
        """Parts filter should show 'Parts' breadcrumb."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.feed_url, {"f": "parts"})

        self.assertContains(response, "<span>Parts</span>")


@tag("views")
class RenderLatestLogEntryQueryTests(TestDataMixin, TestCase):
    """Tests for N+1 query prevention in _render_latest_log_entry.

    Ensures the inline update view uses select_related/prefetch_related
    to prevent N+1 queries when rendering log entry HTML for live injection.
    """

    def setUp(self):
        super().setUp()
        self.view = MachineInlineUpdateView()

        # Create a log entry with related objects that would trigger N+1 queries
        self.log_entry = create_log_entry(machine=self.machine, text="Test work")

        # Add maintainers (accessed via maintainers.all() in template)
        self.log_entry.maintainers.add(self.maintainer)

        # Add a problem report (accessed via select_related in template)
        self.problem_report = create_problem_report(
            machine=self.machine, description="Test problem"
        )
        self.log_entry.problem_report = self.problem_report
        self.log_entry.save()

        # Add media (accessed via media.all in template)
        LogEntryMedia.objects.create(
            log_entry=self.log_entry,
            file="test.jpg",
            media_type="image",
        )

    def test_render_uses_optimal_queries(self):
        """Rendering log entry HTML should use a fixed number of queries.

        Without select_related/prefetch_related, rendering would cause:
        - 1 query for the log entry
        - 1 query for problem_report (FK)
        - 1 query for maintainers.exists()
        - 1 query for maintainers.all()
        - 1 query for each maintainer's user (N+1!)
        - 1 query for media.all

        With proper optimization, we expect:
        - 1 query for log entry + problem_report (select_related)
        - 1 query for maintainers (prefetch_related)
        - 1 query for maintainers' users (prefetch_related maintainers__user)
        - 1 query for media (prefetch_related)
        """
        # 4 queries: log+problem_report, maintainers, users, media
        with self.assertNumQueries(4):
            html = self.view._render_latest_log_entry(self.machine)

        # Verify the HTML contains expected content
        self.assertIn("Test work", html)
        self.assertIn(self.maintainer_user.first_name, html)

    def test_render_without_related_objects(self):
        """Rendering a log entry without related objects uses minimal queries."""
        # Create a simple log entry with no relations (will be newest)
        create_log_entry(machine=self.machine, text="Simple work")

        # 3 queries: log+problem_report, maintainers (empty), media (empty)
        # The user query is skipped because there are no maintainers to fetch users for
        with self.assertNumQueries(3):
            html = self.view._render_latest_log_entry(self.machine)

        self.assertIn("Simple work", html)

    def test_render_no_log_entries(self):
        """Rendering when no log entries exist should use 1 query."""
        # Delete all log entries
        self.machine.log_entries.all().delete()

        # Just 1 query to check for log entry (returns None)
        with self.assertNumQueries(1):
            html = self.view._render_latest_log_entry(self.machine)

        self.assertEqual(html, "")
