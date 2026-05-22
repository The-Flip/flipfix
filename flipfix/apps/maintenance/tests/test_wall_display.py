"""Tests for the wall display setup and board pages."""

from constance.test import override_config
from django.test import TestCase, tag
from django.urls import reverse

from flipfix.apps.catalog.models import Location, MachineInstance
from flipfix.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TestDataMixin,
    create_machine,
    create_problem_report,
)
from flipfix.apps.maintenance.models import ProblemReport, ProblemReportMedia


@tag("views")
class WallDisplaySetupViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for the wall display setup page (/wall/)."""

    def setUp(self):
        super().setUp()
        self.url = reverse("wall-display-setup")

    @override_config(PUBLIC_ACCESS_ENABLED=True)
    def test_accessible_to_guests_when_public_access_enabled(self):
        """Guests can view the setup page when public access is on."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    @override_config(PUBLIC_ACCESS_ENABLED=False)
    def test_redirects_to_login_when_public_access_disabled(self):
        """Guests are redirected to login when public access is off."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_accessible_to_maintainers(self):
        """Logged-in maintainers can view the setup page."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "maintenance/wall_display_setup.html")

    def test_lists_all_locations(self):
        """All locations appear on the setup page for selection."""
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

    def test_mode_dropdown_renders_both_options(self):
        """The setup page exposes both display modes in a dropdown."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.url)
        self.assertContains(response, 'name="mode"')
        self.assertContains(response, 'value="workshop"')
        self.assertContains(response, 'value="now-playing"')

    def test_mode_selection_preserved_in_dropdown(self):
        """The dropdown re-renders with the requested mode pre-selected."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.url, {"mode": "now-playing"})
        self.assertContains(response, 'value="now-playing" selected')

    def test_workshop_is_default_mode(self):
        """When no mode is given, the workshop option is selected."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.url)
        self.assertContains(response, 'value="workshop" selected')


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

    @override_config(PUBLIC_ACCESS_ENABLED=True)
    def test_accessible_to_guests_when_public_access_enabled(self):
        """Guests can view the board when public access is on."""
        response = self.client.get(self.board_url, {"location": ["floor"]})
        self.assertEqual(response.status_code, 200)

    @override_config(PUBLIC_ACCESS_ENABLED=False)
    def test_redirects_to_login_when_public_access_disabled(self):
        """Guests are redirected to login when public access is off."""
        response = self.client.get(self.board_url, {"location": ["floor"]})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_shows_error_when_no_locations(self):
        """Board shows an error message when no location params are provided."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No locations specified.")

    def test_shows_error_for_invalid_location(self):
        """Board shows an error naming the invalid location slug."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url, {"location": ["does-not-exist"]})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "does-not-exist")

    def test_shows_error_when_mix_of_valid_and_invalid_locations(self):
        """Board rejects the request when any location slug is invalid."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url, {"location": ["floor", "bogus"]})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "bogus")

    def test_renders_with_valid_locations(self):
        """Board renders successfully with valid location params."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url, {"location": ["floor"]})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "maintenance/wall_display_board.html")

    def test_shows_only_open_problems(self):
        """Closed problems are excluded from the board."""
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
        """Only problems at the requested locations appear."""
        create_problem_report(machine=self.floor_machine, description="Floor issue")
        create_problem_report(machine=self.workshop_machine, description="Workshop issue")
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url, {"location": ["floor"]})
        self.assertContains(response, "Floor issue")
        self.assertNotContains(response, "Workshop issue")

    def test_multiple_locations_as_columns(self):
        """Each requested location renders as its own column."""
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
        """A valid refresh param adds a meta refresh tag."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url, {"location": ["floor"], "refresh": "30"})
        self.assertContains(response, '<meta http-equiv="refresh" content="30">')

    def test_no_refresh_meta_tag_when_not_set(self):
        """No meta refresh tag when the refresh param is absent."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url, {"location": ["floor"]})
        self.assertNotContains(response, "http-equiv")

    def test_refresh_below_minimum_is_ignored(self):
        """Refresh values below the minimum threshold are silently ignored."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url, {"location": ["floor"], "refresh": "5"})
        self.assertNotContains(response, "http-equiv")

    def test_refresh_invalid_value_is_ignored(self):
        """Non-numeric refresh values are silently ignored."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url, {"location": ["floor"], "refresh": "abc"})
        self.assertNotContains(response, "http-equiv")

    def test_groups_problems_by_machine(self):
        """Multiple problems on one machine appear under a single machine header."""
        create_problem_report(machine=self.floor_machine, description="First problem")
        create_problem_report(machine=self.floor_machine, description="Second problem")
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url, {"location": ["floor"]})
        content = response.content.decode()
        # Machine name header should appear exactly once
        machine_name = self.floor_machine.short_display_name
        self.assertEqual(content.count(f'wall-card__header">{machine_name}'), 1)
        # Both problem descriptions should be present
        self.assertContains(response, "First problem")
        self.assertContains(response, "Second problem")

    def test_groups_sorted_by_most_severe_report(self):
        """Machine groups are ordered by the severity of their worst report."""
        machine_a = create_machine(slug="machine-a", location=self.floor)
        machine_b = create_machine(slug="machine-b", location=self.floor)
        create_problem_report(
            machine=machine_a,
            priority=ProblemReport.Priority.MINOR,
            description="Minor on A",
        )
        create_problem_report(
            machine=machine_b,
            priority=ProblemReport.Priority.UNPLAYABLE,
            description="Unplayable on B",
        )
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url, {"location": ["floor"]})
        content = response.content.decode()
        # Machine B (unplayable) should appear before Machine A (minor)
        b_pos = content.index(machine_b.short_display_name)
        a_pos = content.index(machine_a.short_display_name)
        self.assertLess(b_pos, a_pos)

    def test_overflow_summary_when_more_than_four_reports(self):
        """When a machine has >4 reports, only 4 rows show with an overflow summary."""
        for i in range(4):
            create_problem_report(
                machine=self.floor_machine,
                priority=ProblemReport.Priority.UNPLAYABLE,
                description=f"Visible {i}",
            )
        for _ in range(3):
            create_problem_report(
                machine=self.floor_machine,
                priority=ProblemReport.Priority.MINOR,
            )
        for _ in range(2):
            create_problem_report(
                machine=self.floor_machine,
                priority=ProblemReport.Priority.TASK,
            )
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url, {"location": ["floor"]})
        content = response.content.decode()
        # Only 4 rows should be rendered, not 9
        self.assertEqual(content.count("wall-card__row"), 4)
        # First 4 reports should be visible
        for i in range(4):
            self.assertContains(response, f"Visible {i}")
        # Overflow summary should mention the hidden reports
        self.assertContains(response, "plus 3 minor and 2 task")

    def test_overflow_summary_uses_oxford_comma_for_three_or_more_types(self):
        """Overflow with 3+ priority types uses Oxford comma formatting."""
        for i in range(4):
            create_problem_report(
                machine=self.floor_machine,
                priority=ProblemReport.Priority.UNTRIAGED,
                description=f"Visible {i}",
            )
        create_problem_report(
            machine=self.floor_machine,
            priority=ProblemReport.Priority.MAJOR,
        )
        for _ in range(3):
            create_problem_report(
                machine=self.floor_machine,
                priority=ProblemReport.Priority.MINOR,
            )
        for _ in range(2):
            create_problem_report(
                machine=self.floor_machine,
                priority=ProblemReport.Priority.TASK,
            )
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url, {"location": ["floor"]})
        self.assertContains(response, "plus 1 major, 3 minor, and 2 task")

    def test_machine_header_links_to_machine_detail(self):
        """The machine name in each wall card links to the machine detail page."""
        create_problem_report(machine=self.floor_machine, description="Some issue")
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url, {"location": ["floor"]})
        expected_url = reverse(
            "maintainer-machine-detail", kwargs={"slug": self.floor_machine.slug}
        )
        self.assertContains(response, f'href="{expected_url}"')
        self.assertContains(response, "wall-card__header")

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
        """Empty locations show a friendly no-problems message."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.board_url, {"location": ["floor"]})
        self.assertContains(response, "No open problems 🥳")


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
        """Closed reports are excluded from the queryset."""
        open_report = create_problem_report(machine=self.floor_machine)
        closed_report = create_problem_report(
            machine=self.floor_machine, status=ProblemReport.Status.CLOSED
        )
        qs = ProblemReport.objects.for_wall_display(["floor"])
        self.assertIn(open_report, qs)
        self.assertNotIn(closed_report, qs)

    def test_filters_by_location(self):
        """Only reports at the specified locations are returned."""
        floor_report = create_problem_report(machine=self.floor_machine)
        workshop_report = create_problem_report(machine=self.workshop_machine)
        qs = ProblemReport.objects.for_wall_display(["floor"])
        self.assertIn(floor_report, qs)
        self.assertNotIn(workshop_report, qs)

    def test_orders_by_priority(self):
        """Reports are ordered by priority severity, most severe first."""
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
        """Each report is annotated with its media attachment count."""
        report = create_problem_report(machine=self.floor_machine)
        ProblemReportMedia.objects.create(problem_report=report, file="a.jpg")
        ProblemReportMedia.objects.create(problem_report=report, file="b.jpg")
        qs = ProblemReport.objects.for_wall_display(["floor"])
        self.assertEqual(qs.first().media_count, 2)


@tag("views")
class WallDisplayBoardNowPlayingTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for the now-playing mode of the wall display board."""

    def setUp(self):
        super().setUp()
        self.floor, _ = Location.objects.get_or_create(
            slug="floor", defaults={"name": "Floor", "sort_order": 1}
        )
        self.workshop, _ = Location.objects.get_or_create(
            slug="workshop", defaults={"name": "Workshop", "sort_order": 2}
        )
        self.board_url = reverse("wall-display-board")
        self.client.force_login(self.maintainer_user)

    def _make_model(self, name, manufacturer="Williams", year=1994):
        from flipfix.apps.catalog.models import MachineModel

        return MachineModel.objects.create(name=name, manufacturer=manufacturer, year=year)

    def test_unknown_mode_falls_back_to_workshop(self):
        """An unknown mode value renders the workshop board, not an error."""
        create_machine(slug="m1", location=self.floor, name="Visible Machine")
        create_problem_report(
            machine=create_machine(slug="m2", location=self.floor),
            description="Workshop problem",
        )
        response = self.client.get(self.board_url, {"mode": "bogus", "location": ["floor"]})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Workshop problem")

    def test_now_playing_shows_only_working_machines(self):
        """Only machines with operational_status=GOOD appear in now-playing."""
        good = create_machine(
            slug="good-machine",
            name="Good Machine",
            location=self.floor,
            operational_status=MachineInstance.OperationalStatus.GOOD,
        )
        for status, slug, label in [
            (MachineInstance.OperationalStatus.BROKEN, "broken-m", "Broken Machine"),
            (MachineInstance.OperationalStatus.FIXING, "fixing-m", "Fixing Machine"),
            (MachineInstance.OperationalStatus.UNKNOWN, "unknown-m", "Unknown Machine"),
        ]:
            create_machine(slug=slug, name=label, location=self.floor, operational_status=status)
        response = self.client.get(self.board_url, {"mode": "now-playing", "location": ["floor"]})
        self.assertContains(response, good.name)
        self.assertNotContains(response, "Broken Machine")
        self.assertNotContains(response, "Fixing Machine")
        self.assertNotContains(response, "Unknown Machine")

    def test_now_playing_filters_by_location(self):
        """Now-playing respects the location filter."""
        create_machine(slug="floor-good", name="Floor Good", location=self.floor)
        create_machine(slug="workshop-good", name="Workshop Good", location=self.workshop)
        response = self.client.get(self.board_url, {"mode": "now-playing", "location": ["floor"]})
        self.assertContains(response, "Floor Good")
        self.assertNotContains(response, "Workshop Good")

    def test_now_playing_sorts_oldest_year_first(self):
        """Machines are ordered by manufacturing year ascending."""
        old_model = self._make_model("Old Model", year=1980)
        new_model = self._make_model("New Model", year=2020)
        create_machine(slug="new-m", name="Newer Game", location=self.floor, model=new_model)
        create_machine(slug="old-m", name="Older Game", location=self.floor, model=old_model)
        response = self.client.get(self.board_url, {"mode": "now-playing", "location": ["floor"]})
        content = response.content.decode()
        self.assertLess(content.index("Older Game"), content.index("Newer Game"))

    def test_now_playing_shows_manufacturer_and_year(self):
        """Each row renders 'Name (Manufacturer, Year)'."""
        model = self._make_model("Addams", manufacturer="Williams", year=1994)
        create_machine(slug="taf", name="The Addams Family", location=self.floor, model=model)
        response = self.client.get(self.board_url, {"mode": "now-playing", "location": ["floor"]})
        self.assertContains(response, "The Addams Family")
        self.assertContains(response, "(1994 Williams)")

    def test_now_playing_omits_parens_when_neither_present(self):
        """No naked parens when both manufacturer and year are blank."""
        from flipfix.apps.catalog.models import MachineModel

        model = MachineModel.objects.create(name="Anon Model", manufacturer="", year=None)
        create_machine(slug="anon", name="Mystery Machine", location=self.floor, model=model)
        response = self.client.get(self.board_url, {"mode": "now-playing", "location": ["floor"]})
        self.assertContains(response, "Mystery Machine")
        self.assertNotContains(response, "()")

    def test_now_playing_shows_empty_message_when_no_working_machines(self):
        """An empty location column shows the now-playing empty message."""
        create_machine(
            slug="broken-only",
            name="Broken Only",
            location=self.floor,
            operational_status=MachineInstance.OperationalStatus.BROKEN,
        )
        response = self.client.get(self.board_url, {"mode": "now-playing", "location": ["floor"]})
        self.assertContains(response, "No machines playing.")
        self.assertNotContains(response, "Broken Only")

    def test_now_playing_page_title(self):
        """The page title reflects the now-playing mode."""
        response = self.client.get(self.board_url, {"mode": "now-playing", "location": ["floor"]})
        self.assertContains(response, "Now Playing · Wall Display")

    def test_now_playing_does_not_show_problem_reports(self):
        """Now-playing renders no problem-report rows, even on working machines."""
        good = create_machine(slug="good-machine", name="Good Machine", location=self.floor)
        create_problem_report(machine=good, description="Stealth problem text")
        response = self.client.get(self.board_url, {"mode": "now-playing", "location": ["floor"]})
        self.assertContains(response, "Good Machine")
        self.assertNotContains(response, "Stealth problem text")

    def test_now_playing_per_column_sets_grid_template(self):
        """The per_column param flows through as a CSS custom property."""
        create_machine(slug="m1", location=self.floor)
        response = self.client.get(
            self.board_url,
            {"mode": "now-playing", "location": ["floor"], "per_column": "5"},
        )
        self.assertContains(response, "grid-template-rows: repeat(5, auto)")

    def test_now_playing_per_column_defaults_to_10(self):
        """Without an explicit per_column, the template uses the default of 10."""
        create_machine(slug="m1", location=self.floor)
        response = self.client.get(self.board_url, {"mode": "now-playing", "location": ["floor"]})
        self.assertContains(response, "grid-template-rows: repeat(10, auto)")

    def test_now_playing_per_column_invalid_falls_back_to_default(self):
        """Non-numeric per_column values fall back to the default."""
        create_machine(slug="m1", location=self.floor)
        response = self.client.get(
            self.board_url,
            {"mode": "now-playing", "location": ["floor"], "per_column": "abc"},
        )
        self.assertContains(response, "grid-template-rows: repeat(10, auto)")

    def test_now_playing_per_column_clamped_to_max(self):
        """Per-column values above the cap are clamped down."""
        create_machine(slug="m1", location=self.floor)
        response = self.client.get(
            self.board_url,
            {"mode": "now-playing", "location": ["floor"], "per_column": "9999"},
        )
        self.assertContains(response, "grid-template-rows: repeat(50, auto)")

    def test_now_playing_location_flex_matches_sub_column_count(self):
        """Locations get flex-grow proportional to the number of sub-columns they need."""
        # 5 machines on floor → 1 sub-column at per_column=10
        for i in range(5):
            create_machine(slug=f"floor-{i}", location=self.floor)
        # 25 machines on workshop → 3 sub-columns at per_column=10 (ceil(25/10))
        for i in range(25):
            create_machine(slug=f"workshop-{i}", location=self.workshop)
        response = self.client.get(
            self.board_url,
            {
                "mode": "now-playing",
                "location": ["floor", "workshop"],
                "per_column": "10",
            },
        )
        content = response.content.decode()
        # Floor wrapper (first location) gets flex-grow: 1
        self.assertIn(":nth-of-type(1)", content)
        self.assertIn("flex-grow: 1;", content)
        # Workshop wrapper (second location) gets flex-grow: 3
        self.assertIn(":nth-of-type(2)", content)
        self.assertIn("flex-grow: 3;", content)

    def test_now_playing_empty_location_still_gets_one_sub_column(self):
        """Locations with no working machines still claim a minimum flex slice."""
        # Workshop has no machines; flex should still be at least 1.
        for i in range(15):
            create_machine(slug=f"floor-{i}", location=self.floor)
        response = self.client.get(
            self.board_url,
            {
                "mode": "now-playing",
                "location": ["floor", "workshop"],
                "per_column": "10",
            },
        )
        content = response.content.decode()
        # Two flex-grow declarations: floor=2 (ceil(15/10)), workshop=1 (min)
        self.assertIn("flex-grow: 2;", content)
        self.assertIn("flex-grow: 1;", content)
