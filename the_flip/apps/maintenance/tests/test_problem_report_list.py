"""Tests for the global problem report column board (/problem-reports/).

Machine-scoped problem report tests are in catalog/tests/test_machine_feed.py.
"""

from datetime import timedelta

from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from the_flip.apps.catalog.models import Location
from the_flip.apps.core.columns import Column, build_location_columns
from the_flip.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TestDataMixin,
    create_machine,
    create_problem_report,
)
from the_flip.apps.maintenance.models import ProblemReport


@tag("views")
class ProblemReportListViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for the global problem report column board."""

    def setUp(self):
        super().setUp()
        self.report = create_problem_report(machine=self.machine, description="Test problem")
        self.list_url = reverse("problem-report-list")

    def test_requires_authentication(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_requires_staff_permission(self):
        """Non-staff users should be denied access (403)."""
        self.client.force_login(self.regular_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    def test_accessible_to_staff(self):
        """Staff users should be able to access the column board."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "maintenance/problem_report_list.html")

    def test_contains_link_to_detail(self):
        """Column board should contain links to detail pages."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url)

        detail_url = reverse("problem-report-detail", kwargs={"pk": self.report.pk})
        self.assertContains(response, detail_url)

    def test_context_has_columns(self):
        """View should provide columns as Column objects."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url)

        columns = response.context["columns"]
        self.assertIsInstance(columns, list)
        self.assertGreaterEqual(len(columns), 1)
        self.assertIsInstance(columns[0], Column)
        self.assertIsInstance(columns[0].label, str)
        self.assertIsInstance(columns[0].overflow_count, int)

    def test_only_open_reports_shown(self):
        """Column board should only show open reports, not closed."""
        create_problem_report(
            machine=self.machine,
            description="Closed report",
            status=ProblemReport.Status.CLOSED,
        )
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url)

        self.assertContains(response, "Test problem")
        self.assertNotContains(response, "Closed report")

    def test_columns_grouped_by_location(self):
        """Reports should appear under their machine's location column."""
        loc_a = Location.objects.create(name="Room A", slug="room-a", sort_order=1)
        loc_b = Location.objects.create(name="Room B", slug="room-b", sort_order=2)
        machine_a = create_machine(slug="machine-a", location=loc_a)
        machine_b = create_machine(slug="machine-b", location=loc_b)
        report_a = create_problem_report(machine=machine_a, description="In Room A")
        report_b = create_problem_report(machine=machine_b, description="In Room B")

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url)

        columns = response.context["columns"]
        by_label = {col.label: col.items for col in columns}

        self.assertIn("Room A", by_label)
        self.assertIn("Room B", by_label)
        self.assertIn(report_a, by_label["Room A"])
        self.assertIn(report_b, by_label["Room B"])

    def test_empty_locations_hidden(self):
        """Locations with no open reports should not appear as columns."""
        Location.objects.create(name="Empty Room", slug="empty-room", sort_order=99)

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url)

        self.assertNotContains(response, "Empty Room")

    def test_columns_ordered_by_location_sort_order(self):
        """Columns should appear in Location.sort_order, not alphabetical."""
        # "Zebra Room" sorts alphabetically last but has sort_order=1 (first)
        loc_z = Location.objects.create(name="Zebra Room", slug="zebra-room", sort_order=1)
        # "Alpha Room" sorts alphabetically first but has sort_order=2 (second)
        loc_a = Location.objects.create(name="Alpha Room", slug="alpha-room", sort_order=2)
        # Each location needs a report to appear (empty locations are hidden)
        create_problem_report(machine=create_machine(slug="z-m", location=loc_z))
        create_problem_report(machine=create_machine(slug="a-m", location=loc_a))

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url)

        columns = response.context["columns"]
        labels = [col.label for col in columns]
        self.assertLess(labels.index("Zebra Room"), labels.index("Alpha Room"))


@tag("views")
class ProblemReportColumnOrderTests(TestDataMixin, TestCase):
    """Tests for priority ordering within location columns."""

    def setUp(self):
        super().setUp()
        self.location = Location.objects.create(name="Test Floor", slug="test-floor", sort_order=1)
        self.machine.location = self.location
        self.machine.save(update_fields=["location"])
        self.list_url = reverse("problem-report-list")
        self.client.force_login(self.maintainer_user)

    def _find_column(self, columns, label):
        """Return the Column with the given label, or None."""
        for col in columns:
            if col.label == label:
                return col
        return None

    def test_priority_ordering_within_column(self):
        """Reports within a column sort by priority: untriaged, unplayable, major, minor, task."""
        now = timezone.now()
        task = create_problem_report(
            machine=self.machine,
            description="Task report",
            priority=ProblemReport.Priority.TASK,
            occurred_at=now,
        )
        unplayable = create_problem_report(
            machine=self.machine,
            description="Unplayable report",
            priority=ProblemReport.Priority.UNPLAYABLE,
            occurred_at=now,
        )
        untriaged = create_problem_report(
            machine=self.machine,
            description="Untriaged report",
            priority=ProblemReport.Priority.UNTRIAGED,
            occurred_at=now,
        )
        minor = create_problem_report(
            machine=self.machine,
            description="Minor report",
            priority=ProblemReport.Priority.MINOR,
            occurred_at=now,
        )
        major = create_problem_report(
            machine=self.machine,
            description="Major report",
            priority=ProblemReport.Priority.MAJOR,
            occurred_at=now,
        )

        response = self.client.get(self.list_url)
        columns = response.context["columns"]

        col = self._find_column(columns, self.machine.location.name)
        self.assertIsNotNone(col)
        pks = [r.pk for r in col.items]
        self.assertEqual(
            pks,
            [untriaged.pk, unplayable.pk, major.pk, minor.pk, task.pk],
        )

    def test_newest_first_within_same_priority(self):
        """Reports with the same priority sort by occurred_at newest first."""
        now = timezone.now()
        older = create_problem_report(
            machine=self.machine,
            description="Older",
            priority=ProblemReport.Priority.MAJOR,
            occurred_at=now - timedelta(days=5),
        )
        newer = create_problem_report(
            machine=self.machine,
            description="Newer",
            priority=ProblemReport.Priority.MAJOR,
            occurred_at=now,
        )

        response = self.client.get(self.list_url)
        columns = response.context["columns"]

        col = self._find_column(columns, self.machine.location.name)
        self.assertIsNotNone(col)
        pks = [r.pk for r in col.items]
        self.assertLess(pks.index(newer.pk), pks.index(older.pk))


@tag("views")
class ProblemReportListSearchTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for search on the global problem report column board."""

    def setUp(self):
        super().setUp()
        self.list_url = reverse("problem-report-list")
        self.client.force_login(self.maintainer_user)

    def test_search_filters_by_description(self):
        """Search should filter reports by description text."""
        create_problem_report(machine=self.machine, description="Broken flipper")
        create_problem_report(machine=self.machine, description="Stuck ball")

        response = self.client.get(self.list_url, {"q": "flipper"})

        self.assertContains(response, "Broken flipper")
        self.assertNotContains(response, "Stuck ball")

    def test_search_filters_by_machine_name(self):
        """Search should match against the machine's name."""
        loc = Location.objects.create(name="Search Floor", slug="search-floor", sort_order=1)
        target = create_machine(slug="target-pin", name="Medieval Madness", location=loc)
        other = create_machine(slug="other-pin", name="Twilight Zone", location=loc)
        create_problem_report(machine=target, description="Issue A")
        create_problem_report(machine=other, description="Issue B")

        response = self.client.get(self.list_url, {"q": "Medieval"})

        self.assertContains(response, "Issue A")
        self.assertNotContains(response, "Issue B")

    def test_empty_search_returns_all(self):
        """An empty search query should return all open reports."""
        create_problem_report(machine=self.machine, description="Report one")
        create_problem_report(machine=self.machine, description="Report two")

        response = self.client.get(self.list_url, {"q": ""})

        self.assertContains(response, "Report one")
        self.assertContains(response, "Report two")

    def test_no_results_shows_search_message(self):
        """When search yields no results, show search-specific empty message."""
        create_problem_report(machine=self.machine, description="Something")

        response = self.client.get(self.list_url, {"q": "nonexistent"})

        self.assertContains(response, "No open problems match your search.")
        self.assertNotContains(response, "🥳")

    def test_no_problems_without_search_shows_celebration(self):
        """When there are genuinely no problems, show the celebration message."""
        response = self.client.get(self.list_url)

        self.assertContains(response, "🥳")

    def test_search_preserves_query_in_form(self):
        """The search input should retain the query after submission."""
        create_problem_report(machine=self.machine, description="Test")

        response = self.client.get(self.list_url, {"q": "flipper"})

        self.assertContains(response, 'value="flipper"')


@tag("unit")
class BuildLocationColumnsTests(TestCase):
    """Unit tests for the build_location_columns utility."""

    def test_groups_by_location(self):
        """Reports are grouped into the correct location columns."""
        loc_a = Location.objects.create(name="Room A", slug="room-a", sort_order=1)
        loc_b = Location.objects.create(name="Room B", slug="room-b", sort_order=2)
        machine_a = create_machine(slug="col-machine-a", location=loc_a)
        machine_b = create_machine(slug="col-machine-b", location=loc_b)
        report_a = create_problem_report(machine=machine_a, description="In A")
        report_b = create_problem_report(machine=machine_b, description="In B")

        columns = build_location_columns([report_a, report_b], [loc_a, loc_b])

        self.assertEqual(len(columns), 2)
        self.assertEqual(columns[0], Column("Room A", [report_a]))
        self.assertEqual(columns[1], Column("Room B", [report_b]))

    def test_empty_locations_included_by_default(self):
        """Locations with no reports appear as empty columns by default."""
        loc = Location.objects.create(name="Empty", slug="empty", sort_order=1)

        columns = build_location_columns([], [loc])

        self.assertEqual(columns, [Column("Empty", [])])

    def test_empty_locations_excluded_when_requested(self):
        """Locations with no reports are omitted when include_empty_columns=False."""
        loc_empty = Location.objects.create(name="Empty", slug="empty", sort_order=1)
        loc_full = Location.objects.create(name="Full", slug="full", sort_order=2)
        machine = create_machine(slug="col-machine", location=loc_full)
        report = create_problem_report(machine=machine, description="Here")

        columns = build_location_columns(
            [report], [loc_empty, loc_full], include_empty_columns=False
        )

        self.assertEqual(columns, [Column("Full", [report])])

    def test_preserves_location_order(self):
        """Column order follows the provided locations order."""
        loc_z = Location.objects.create(name="Zulu", slug="zulu", sort_order=1)
        loc_a = Location.objects.create(name="Alpha", slug="alpha", sort_order=2)

        columns = build_location_columns([], [loc_z, loc_a])

        self.assertEqual([col.label for col in columns], ["Zulu", "Alpha"])

    def test_unassigned_column_at_end(self):
        """Reports with no location go into an 'Unassigned' column at the end."""
        loc = Location.objects.create(name="Room", slug="room", sort_order=1)
        machine_no_loc = create_machine(slug="no-loc-machine", location=None)
        report = create_problem_report(machine=machine_no_loc, description="Homeless")

        columns = build_location_columns([report], [loc])

        self.assertEqual(len(columns), 2)
        self.assertEqual(columns[0], Column("Room", []))
        self.assertEqual(columns[1], Column("Unassigned", [report]))

    def test_no_unassigned_column_when_all_located(self):
        """No 'Unassigned' column when all reports have locations."""
        loc = Location.objects.create(name="Room", slug="room", sort_order=1)
        machine = create_machine(slug="loc-machine", location=loc)
        report = create_problem_report(machine=machine, description="Located")

        columns = build_location_columns([report], [loc])

        self.assertEqual(len(columns), 1)
        self.assertEqual(columns[0], Column("Room", [report]))

    def test_max_results_per_column_truncates(self):
        """Columns are truncated to max_results_per_column with correct overflow count."""
        loc = Location.objects.create(name="Room", slug="room", sort_order=1)
        machine = create_machine(slug="trunc-machine", location=loc)
        reports = [
            create_problem_report(machine=machine, description=f"Report {i}") for i in range(5)
        ]

        columns = build_location_columns(reports, [loc], max_results_per_column=3)

        col = columns[0]
        self.assertEqual(col.label, "Room")
        self.assertEqual(len(col.items), 3)
        self.assertEqual(col.overflow_count, 2)

    def test_max_results_per_column_no_truncation_when_under_limit(self):
        """No truncation when column has fewer items than the limit."""
        loc = Location.objects.create(name="Room", slug="room", sort_order=1)
        machine = create_machine(slug="small-machine", location=loc)
        report = create_problem_report(machine=machine, description="Only one")

        columns = build_location_columns([report], [loc], max_results_per_column=10)

        self.assertEqual(columns[0], Column("Room", [report]))
