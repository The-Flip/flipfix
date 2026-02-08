"""Tests for the wall display setup and board pages."""

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.catalog.models import Location
from the_flip.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TestDataMixin,
    create_machine,
    create_problem_report,
)
from the_flip.apps.maintenance.models import ProblemReport


@tag("views")
class WallDisplaySetupViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for the wall display setup page (/wall/)."""

    def setUp(self):
        super().setUp()
        self.url = reverse("wall-display-setup")

    def test_requires_authentication(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_requires_maintainer_access(self):
        self.client.force_login(self.regular_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_accessible_to_maintainers(self):
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "maintenance/wall_display_setup.html")

    def test_lists_all_locations(self):
        floor, _ = Location.objects.get_or_create(
            slug="floor", defaults={"name": "Floor", "sort_order": 1}
        )
        workshop, _ = Location.objects.get_or_create(
            slug="workshop", defaults={"name": "Workshop", "sort_order": 2}
        )
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.url)
        self.assertContains(response, floor.name)
        self.assertContains(response, workshop.name)


@tag("views")
class WallDisplayBoardViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for the wall display board page (/wall/board/)."""

    def setUp(self):
        super().setUp()
        self.floor, _ = Location.objects.get_or_create(
            slug="floor", defaults={"name": "Floor", "sort_order": 1}
        )
        self.workshop, _ = Location.objects.get_or_create(
            slug="workshop", defaults={"name": "Workshop", "sort_order": 2}
        )
        self.floor_machine = create_machine(slug="floor-machine", location=self.floor)
        self.workshop_machine = create_machine(slug="workshop-machine", location=self.workshop)
        self.board_url = reverse("wall-display-board")

    def test_requires_authentication(self):
        response = self.client.get(self.board_url, {"location": ["floor"]})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_requires_maintainer_access(self):
        self.client.force_login(self.regular_user)
        response = self.client.get(self.board_url, {"location": ["floor"]})
        self.assertEqual(response.status_code, 403)

    def test_shows_error_when_no_locations(self):
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No locations specified.")

    def test_shows_error_for_invalid_location(self):
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url, {"location": ["does-not-exist"]})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "does-not-exist")

    def test_shows_error_when_mix_of_valid_and_invalid_locations(self):
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url, {"location": ["floor", "bogus"]})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "bogus")

    def test_renders_with_valid_locations(self):
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url, {"location": ["floor"]})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "maintenance/wall_display_board.html")

    def test_shows_only_open_problems(self):
        create_problem_report(machine=self.floor_machine, description="Open problem")
        create_problem_report(
            machine=self.floor_machine,
            status=ProblemReport.Status.CLOSED,
            description="Closed problem",
        )
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url, {"location": ["floor"]})
        self.assertContains(response, "Open problem")
        self.assertNotContains(response, "Closed problem")

    def test_filters_by_selected_locations(self):
        create_problem_report(machine=self.floor_machine, description="Floor issue")
        create_problem_report(machine=self.workshop_machine, description="Workshop issue")
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url, {"location": ["floor"]})
        self.assertContains(response, "Floor issue")
        self.assertNotContains(response, "Workshop issue")

    def test_multiple_locations_as_columns(self):
        create_problem_report(machine=self.floor_machine, description="Floor issue")
        create_problem_report(machine=self.workshop_machine, description="Workshop issue")
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url, {"location": ["floor", "workshop"]})
        self.assertContains(response, "Floor issue")
        self.assertContains(response, "Workshop issue")
        self.assertContains(response, "Floor")
        self.assertContains(response, "Workshop")

    def test_sorts_by_priority_within_location(self):
        """Higher priority problems should appear before lower priority ones."""
        create_problem_report(
            machine=self.floor_machine,
            priority=ProblemReport.Priority.MINOR,
            description="Minor issue",
        )
        create_problem_report(
            machine=self.floor_machine,
            priority=ProblemReport.Priority.UNPLAYABLE,
            description="Unplayable issue",
        )
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url, {"location": ["floor"]})
        content = response.content.decode()
        unplayable_pos = content.index("Unplayable issue")
        minor_pos = content.index("Minor issue")
        self.assertLess(unplayable_pos, minor_pos)

    def test_refresh_meta_tag_present_when_set(self):
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url, {"location": ["floor"], "refresh": "30"})
        self.assertContains(response, '<meta http-equiv="refresh" content="30">')

    def test_no_refresh_meta_tag_when_not_set(self):
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url, {"location": ["floor"]})
        self.assertNotContains(response, "http-equiv")

    def test_refresh_below_minimum_is_ignored(self):
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url, {"location": ["floor"], "refresh": "5"})
        self.assertNotContains(response, "http-equiv")

    def test_refresh_invalid_value_is_ignored(self):
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url, {"location": ["floor"], "refresh": "abc"})
        self.assertNotContains(response, "http-equiv")

    def test_shows_media_count(self):
        report = create_problem_report(machine=self.floor_machine, description="Has photos")
        # Create media items via the model
        from the_flip.apps.maintenance.models import ProblemReportMedia

        ProblemReportMedia.objects.create(problem_report=report, file="test1.jpg")
        ProblemReportMedia.objects.create(problem_report=report, file="test2.jpg")
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url, {"location": ["floor"]})
        self.assertContains(response, "2 photos")

    def test_columns_respect_url_param_order(self):
        """Columns should appear in the order specified by URL params, not DB order."""
        create_problem_report(machine=self.floor_machine, description="Floor issue")
        create_problem_report(machine=self.workshop_machine, description="Workshop issue")
        self.client.force_login(self.maintainer_user)
        # Request workshop before floor (opposite of DB sort_order)
        response = self.client.get(self.board_url, {"location": ["workshop", "floor"]})
        content = response.content.decode()
        workshop_pos = content.index("Workshop")
        floor_pos = content.index("Floor")
        self.assertLess(workshop_pos, floor_pos)

    def test_empty_location_shows_no_problems_message(self):
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url, {"location": ["floor"]})
        self.assertContains(response, "No open problems.")


@tag("models")
class WallDisplayQuerySetTests(TestDataMixin, TestCase):
    """Tests for the for_wall_display() queryset method."""

    def setUp(self):
        super().setUp()
        self.floor, _ = Location.objects.get_or_create(
            slug="floor", defaults={"name": "Floor", "sort_order": 1}
        )
        self.workshop, _ = Location.objects.get_or_create(
            slug="workshop", defaults={"name": "Workshop", "sort_order": 2}
        )
        self.floor_machine = create_machine(slug="floor-machine", location=self.floor)
        self.workshop_machine = create_machine(slug="workshop-machine", location=self.workshop)

    def test_returns_only_open_reports(self):
        open_report = create_problem_report(machine=self.floor_machine)
        closed_report = create_problem_report(
            machine=self.floor_machine, status=ProblemReport.Status.CLOSED
        )
        qs = ProblemReport.objects.for_wall_display(["floor"])
        self.assertIn(open_report, qs)
        self.assertNotIn(closed_report, qs)

    def test_filters_by_location(self):
        floor_report = create_problem_report(machine=self.floor_machine)
        workshop_report = create_problem_report(machine=self.workshop_machine)
        qs = ProblemReport.objects.for_wall_display(["floor"])
        self.assertIn(floor_report, qs)
        self.assertNotIn(workshop_report, qs)

    def test_orders_by_priority(self):
        task = create_problem_report(
            machine=self.floor_machine, priority=ProblemReport.Priority.TASK
        )
        untriaged = create_problem_report(
            machine=self.floor_machine, priority=ProblemReport.Priority.UNTRIAGED
        )
        major = create_problem_report(
            machine=self.floor_machine, priority=ProblemReport.Priority.MAJOR
        )
        qs = list(ProblemReport.objects.for_wall_display(["floor"]))
        self.assertEqual(qs[0], untriaged)
        self.assertEqual(qs[1], major)
        self.assertEqual(qs[2], task)

    def test_annotates_media_count(self):
        report = create_problem_report(machine=self.floor_machine)
        from the_flip.apps.maintenance.models import ProblemReportMedia

        ProblemReportMedia.objects.create(problem_report=report, file="a.jpg")
        ProblemReportMedia.objects.create(problem_report=report, file="b.jpg")
        qs = ProblemReport.objects.for_wall_display(["floor"])
        self.assertEqual(qs.first().media_count, 2)
