"""Tests for the global problem report list view (/problems/).

Machine-scoped problem report tests are in catalog/tests/test_machine_feed.py.
"""

from datetime import timedelta

from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from the_flip.apps.catalog.models import Location
from the_flip.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TestDataMixin,
    create_log_entry,
    create_machine,
    create_maintainer_user,
    create_problem_report,
)
from the_flip.apps.maintenance.models import ProblemReport


@tag("views")
class ProblemReportListViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for the global problem report list view."""

    def setUp(self):
        super().setUp()
        self.report = create_problem_report(machine=self.machine, description="Test problem")
        self.list_url = reverse("problem-report-list")

    def test_list_view_requires_authentication(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_list_view_requires_staff_permission(self):
        """Non-staff users should be denied access (403)."""
        self.client.force_login(self.regular_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    def test_list_view_accessible_to_staff(self):
        """Staff users should be able to access the list page."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "maintenance/problem_report_list.html")

    def test_list_view_contains_link_to_detail(self):
        """List view should contain links to detail pages."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url)

        detail_url = reverse("problem-report-detail", kwargs={"pk": self.report.pk})
        self.assertContains(response, detail_url)

    def test_list_view_pagination(self):
        """List view should paginate results."""
        self.client.force_login(self.maintainer_user)
        for i in range(15):
            create_problem_report(machine=self.machine, description=f"Problem {i}")

        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["reports"]), 10)
        self.assertTrue(response.context["page_obj"].has_next())

    def test_list_view_search_by_description(self):
        """List view should filter by description text."""
        self.client.force_login(self.maintainer_user)
        create_problem_report(machine=self.machine, description="Unique flippers broken")

        response = self.client.get(self.list_url, {"q": "flippers"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["reports"]), 1)
        self.assertContains(response, "Unique flippers broken")

    def test_list_view_search_by_machine_name(self):
        """List view should filter by machine model name."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url, {"q": "Test Machine"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["reports"]), 1)

    def test_list_view_search_no_results(self):
        """List view should show empty message when search has no results."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url, {"q": "nonexistent"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["reports"]), 0)
        self.assertContains(response, "No problem reports match your search")

    def test_list_view_search_matches_log_entry_text(self):
        """List search should include attached log entry text."""
        create_log_entry(machine=self.machine, problem_report=self.report, text="Fixed coil stop")
        other_report = create_problem_report(machine=self.machine, description="Other issue")
        create_log_entry(machine=self.machine, problem_report=other_report, text="Different work")

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url, {"q": "coil stop"})

        self.assertContains(response, self.report.description)
        self.assertNotContains(response, other_report.description)

    def test_list_view_search_matches_reporter_name(self):
        """List search should include free-text reporter name."""
        # Create report with free-text reporter name
        create_problem_report(
            machine=self.machine,
            description="Flickering lights",
            reported_by_name="Wandering Willie",
        )
        create_problem_report(machine=self.machine, description="Other issue")

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url, {"q": "Wandering"})

        self.assertContains(response, "Flickering lights")
        self.assertNotContains(response, "Other issue")

    def test_list_view_search_matches_log_entry_maintainer_names(self):
        """List search should include free-text log entry maintainer names."""
        # Create report with log entry that has free-text maintainer name
        report_with_log = create_problem_report(
            machine=self.machine, description="Flickering lights"
        )
        create_log_entry(
            machine=self.machine,
            problem_report=report_with_log,
            text="Investigated issue",
            maintainer_names="Wandering Willie",
        )
        create_problem_report(machine=self.machine, description="Other issue")

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url, {"q": "Wandering"})

        self.assertContains(response, "Flickering lights")
        self.assertNotContains(response, "Other issue")


@tag("views")
class ProblemReportListPartialViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for the problem report list AJAX endpoint."""

    def setUp(self):
        super().setUp()
        self.entries_url = reverse("problem-report-list-entries")

    def test_partial_view_returns_json(self):
        """AJAX endpoint should return JSON response."""
        self.client.force_login(self.maintainer_user)
        create_problem_report(machine=self.machine, description="Test problem")

        response = self.client.get(self.entries_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

        data = response.json()
        self.assertIn("items", data)
        self.assertIn("has_next", data)
        self.assertIn("next_page", data)

    def test_partial_view_pagination(self):
        """AJAX endpoint should paginate and return correct metadata."""
        self.client.force_login(self.maintainer_user)
        for i in range(15):
            create_problem_report(machine=self.machine, description=f"Problem {i}")

        response = self.client.get(self.entries_url, {"page": 1})
        data = response.json()
        self.assertTrue(data["has_next"])
        self.assertEqual(data["next_page"], 2)

        response = self.client.get(self.entries_url, {"page": 2})
        data = response.json()
        self.assertFalse(data["has_next"])
        self.assertIsNone(data["next_page"])

    def test_partial_view_search(self):
        """AJAX endpoint should respect search query."""
        self.client.force_login(self.maintainer_user)
        create_problem_report(machine=self.machine, description="Flipper issue")
        create_problem_report(machine=self.machine, description="Display broken")

        response = self.client.get(self.entries_url, {"q": "Flipper"})
        data = response.json()
        self.assertIn("Flipper issue", data["items"])
        self.assertNotIn("Display broken", data["items"])

    def test_partial_view_search_matches_log_entry_text(self):
        """AJAX endpoint search should include attached log entry text."""
        self.client.force_login(self.maintainer_user)
        report_with_match = create_problem_report(machine=self.machine, description="Has match")
        create_log_entry(
            machine=self.machine, problem_report=report_with_match, text="Investigated coil stop"
        )
        report_no_match = create_problem_report(machine=self.machine, description="No match")
        create_log_entry(
            machine=self.machine, problem_report=report_no_match, text="Different work"
        )

        response = self.client.get(self.entries_url, {"q": "coil stop"})
        data = response.json()

        self.assertIn("Has match", data["items"])
        self.assertNotIn("No match", data["items"])

    def test_partial_view_requires_staff(self):
        """AJAX endpoint should require staff permission."""
        self.client.force_login(self.regular_user)
        response = self.client.get(self.entries_url)
        self.assertEqual(response.status_code, 403)


@tag("views")
class ProblemReportListSearchTests(TestDataMixin, TestCase):
    """Tests for global problem report list search functionality."""

    def setUp(self):
        super().setUp()
        self.list_url = reverse("problem-report-list")

    def test_search_finds_report_by_reported_by_user(self):
        """Search should find problem reports by the submitting user's name."""
        # Create a report submitted by a logged-in user
        submitter = create_maintainer_user(
            username="submitter",
            first_name="Submitting",
            last_name="Sam",
        )
        create_problem_report(
            machine=self.machine,
            description="Flipper not working",
            reported_by_user=submitter,
        )

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url, {"q": "Submitting"})

        self.assertContains(response, "Flipper not working")

    def test_search_by_priority_label(self):
        """Search should find reports by priority label text."""
        create_problem_report(
            machine=self.machine,
            description="Critical failure",
            priority=ProblemReport.Priority.UNPLAYABLE,
        )
        create_problem_report(
            machine=self.machine,
            description="Minor scratch",
            priority=ProblemReport.Priority.MINOR,
        )

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url, {"q": "unplayable"})

        self.assertContains(response, "Critical failure")
        self.assertNotContains(response, "Minor scratch")


@tag("views")
class ProblemReportListSortOrderTests(TestDataMixin, TestCase):
    """Tests for global problem report list sort ordering.

    Sort order:
    1. Open before closed
    2. Within open: priority order (untriaged > unplayable > big > small > task)
    3. Within same priority: location sort_order
    4. Within same location: occurred_at newest first
    5. Closed: only by occurred_at newest first
    """

    def setUp(self):
        super().setUp()
        self.list_url = reverse("problem-report-list")
        self.client.force_login(self.maintainer_user)

    def test_open_reports_before_closed(self):
        """Open reports should appear before closed reports."""
        now = timezone.now()
        closed = create_problem_report(
            machine=self.machine,
            description="Closed report",
            status=ProblemReport.Status.CLOSED,
            occurred_at=now,
        )
        open_report = create_problem_report(
            machine=self.machine,
            description="Open report",
            status=ProblemReport.Status.OPEN,
            occurred_at=now - timedelta(days=10),
        )

        response = self.client.get(self.list_url)
        reports = list(response.context["reports"])

        self.assertEqual(reports[0].pk, open_report.pk)
        self.assertEqual(reports[1].pk, closed.pk)

    def test_priority_ordering_within_open(self):
        """Open reports sort by priority: untriaged, unplayable, big, small, task."""
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
        small = create_problem_report(
            machine=self.machine,
            description="Small report",
            priority=ProblemReport.Priority.MINOR,
            occurred_at=now,
        )
        big = create_problem_report(
            machine=self.machine,
            description="Big report",
            priority=ProblemReport.Priority.MAJOR,
            occurred_at=now,
        )

        response = self.client.get(self.list_url)
        reports = list(response.context["reports"])
        pks = [r.pk for r in reports]

        self.assertEqual(
            pks,
            [untriaged.pk, unplayable.pk, big.pk, small.pk, task.pk],
        )

    def test_location_ordering_within_same_priority(self):
        """Reports with same priority sort by location sort_order, not name.

        Uses locations where alphabetical order differs from sort_order to
        verify we're sorting by sort_order.
        """
        # "Zebra Room" sorts alphabetically last but has sort_order=1 (first)
        # "Alpha Room" sorts alphabetically first but has sort_order=2 (second)
        zebra_loc = Location.objects.create(name="Zebra Room", slug="zebra-room", sort_order=1)
        alpha_loc = Location.objects.create(name="Alpha Room", slug="alpha-room", sort_order=2)

        zebra_machine = create_machine(slug="zebra-machine", location=zebra_loc)
        alpha_machine = create_machine(slug="alpha-machine", location=alpha_loc)

        now = timezone.now()
        alpha_report = create_problem_report(
            machine=alpha_machine,
            description="Alpha location report",
            priority=ProblemReport.Priority.UNPLAYABLE,
            occurred_at=now,
        )
        zebra_report = create_problem_report(
            machine=zebra_machine,
            description="Zebra location report",
            priority=ProblemReport.Priority.UNPLAYABLE,
            occurred_at=now,
        )

        response = self.client.get(self.list_url)
        reports = list(response.context["reports"])
        pks = [r.pk for r in reports]

        # Zebra Room (sort_order=1) should come before Alpha Room (sort_order=2)
        self.assertLess(pks.index(zebra_report.pk), pks.index(alpha_report.pk))

    def test_closed_reports_ignore_priority_and_location(self):
        """Closed reports should sort only by occurred_at, ignoring priority and location."""
        loc1 = Location.objects.create(name="First Floor", slug="first-floor", sort_order=1)
        loc2 = Location.objects.create(name="Second Floor", slug="second-floor", sort_order=2)

        machine1 = create_machine(slug="machine-floor1", location=loc1)
        machine2 = create_machine(slug="machine-floor2", location=loc2)

        now = timezone.now()
        # Older, higher priority, better location — but should come second
        older_high = create_problem_report(
            machine=machine1,
            description="Older high priority",
            priority=ProblemReport.Priority.UNPLAYABLE,
            status=ProblemReport.Status.CLOSED,
            occurred_at=now - timedelta(days=5),
        )
        # Newer, lower priority, worse location — but should come first
        newer_low = create_problem_report(
            machine=machine2,
            description="Newer low priority",
            priority=ProblemReport.Priority.TASK,
            status=ProblemReport.Status.CLOSED,
            occurred_at=now,
        )

        response = self.client.get(self.list_url)
        reports = list(response.context["reports"])
        pks = [r.pk for r in reports]

        # Newer should come first regardless of priority or location
        self.assertLess(pks.index(newer_low.pk), pks.index(older_high.pk))
