"""Tests for model manager methods."""

from django.test import TestCase, tag

from the_flip.apps.core.test_utils import (
    TestDataMixin,
    create_log_entry,
    create_maintainer_user,
    create_problem_report,
)
from the_flip.apps.maintenance.models import LogEntry, ProblemReport


@tag("models")
class ProblemReportSearchTests(TestDataMixin, TestCase):
    """Tests for ProblemReport.objects.search() method."""

    def test_empty_query_returns_all_ordered(self):
        """Empty query returns all reports, ordered by status then date descending."""
        report1 = create_problem_report(machine=self.machine, description="First report")
        report2 = create_problem_report(
            machine=self.machine,
            description="Second report",
            status=ProblemReport.Status.CLOSED,
        )

        results = list(ProblemReport.objects.search(""))

        # Open reports first, then closed, each group by date descending
        self.assertEqual(results[0], report1)  # Open, newer
        self.assertEqual(results[1], report2)  # Closed

    def test_whitespace_query_returns_all(self):
        """Whitespace-only query is treated as empty, returns all."""
        report = create_problem_report(machine=self.machine, description="Test")

        results = list(ProblemReport.objects.search("   "))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], report)

    def test_search_matches_description(self):
        """Search matches problem description (case-insensitive)."""
        matching = create_problem_report(machine=self.machine, description="Flipper is broken")
        create_problem_report(machine=self.machine, description="No credits")

        results = list(ProblemReport.objects.search("flipper"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], matching)

    def test_search_matches_machine_model_name(self):
        """Search matches machine model name."""
        from the_flip.apps.catalog.models import MachineModel
        from the_flip.apps.core.test_utils import create_machine

        # Create a machine with a unique model name
        unique_model = MachineModel.objects.create(name="Unique Pinball 3000")
        unique_machine = create_machine(slug="unique", model=unique_model)
        matching = create_problem_report(machine=unique_machine, description="Some issue")

        # Create another report on the default machine (different model)
        create_problem_report(machine=self.machine, description="Some issue")

        # Search for the unique model name
        results = list(ProblemReport.objects.search("Unique Pinball 3000"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], matching)

    def test_search_matches_reporter_name(self):
        """Search matches reported_by_name field."""
        matching = create_problem_report(
            machine=self.machine,
            description="Issue",
            reported_by_name="Visiting Victor",
        )
        create_problem_report(machine=self.machine, description="Other issue")

        results = list(ProblemReport.objects.search("Victor"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], matching)

    def test_search_matches_reporter_username(self):
        """Search matches reported_by_user username."""
        matching = create_problem_report(
            machine=self.machine,
            description="Issue",
            reported_by_user=self.staff_user,
        )
        create_problem_report(machine=self.machine, description="Other issue")

        results = list(ProblemReport.objects.search(self.staff_user.username))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], matching)

    def test_search_matches_linked_log_entry_text(self):
        """Search matches text in linked log entries."""
        report = create_problem_report(machine=self.machine, description="Ball stuck")
        create_log_entry(
            machine=self.machine,
            text="Replaced the coil stop",
            problem_report=report,
        )
        create_problem_report(machine=self.machine, description="Other issue")

        results = list(ProblemReport.objects.search("coil stop"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], report)

    def test_search_matches_log_entry_maintainer_name(self):
        """Search matches maintainer names on linked log entries."""
        maintainer_user = create_maintainer_user(
            username="fixit", first_name="Fix", last_name="McGee"
        )
        report = create_problem_report(machine=self.machine, description="Problem")
        log = create_log_entry(machine=self.machine, text="Fixed", problem_report=report)
        log.maintainers.add(maintainer_user.maintainer)

        create_problem_report(machine=self.machine, description="Other")

        results = list(ProblemReport.objects.search("McGee"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], report)

    def test_search_returns_distinct_results(self):
        """Search returns distinct results even with multiple matches."""
        report = create_problem_report(machine=self.machine, description="Test problem")
        # Create two log entries that both match "test"
        create_log_entry(machine=self.machine, text="Test fix 1", problem_report=report)
        create_log_entry(machine=self.machine, text="Test fix 2", problem_report=report)

        results = list(ProblemReport.objects.search("test"))

        # Should only return the report once, not duplicated
        self.assertEqual(len(results), 1)

    def test_search_is_chainable(self):
        """Search returns a queryset that can be chained."""
        create_problem_report(machine=self.machine, description="Open problem")
        create_problem_report(
            machine=self.machine,
            description="Closed problem",
            status=ProblemReport.Status.CLOSED,
        )

        # Chain with .open() filter
        results = ProblemReport.objects.search("problem").open()

        self.assertEqual(results.count(), 1)


@tag("models")
class LogEntrySearchTests(TestDataMixin, TestCase):
    """Tests for LogEntry.objects.search() method."""

    def test_empty_query_returns_all_ordered(self):
        """Empty query returns all entries, ordered by work_date descending."""
        from datetime import timedelta

        from django.utils import timezone

        older = create_log_entry(
            machine=self.machine,
            text="Older entry",
            work_date=timezone.now() - timedelta(days=5),
        )
        newer = create_log_entry(machine=self.machine, text="Newer entry")

        results = list(LogEntry.objects.search(""))

        self.assertEqual(results[0], newer)
        self.assertEqual(results[1], older)

    def test_whitespace_query_returns_all(self):
        """Whitespace-only query is treated as empty, returns all."""
        entry = create_log_entry(machine=self.machine, text="Test work")

        results = list(LogEntry.objects.search("   "))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], entry)

    def test_search_matches_text(self):
        """Search matches log entry text (case-insensitive)."""
        matching = create_log_entry(machine=self.machine, text="Replaced the flipper coil")
        create_log_entry(machine=self.machine, text="Adjusted targets")

        results = list(LogEntry.objects.search("flipper"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], matching)

    def test_search_matches_machine_model_name(self):
        """Search matches machine model name."""
        from the_flip.apps.catalog.models import MachineModel
        from the_flip.apps.core.test_utils import create_machine

        # Create a machine with a unique model name
        unique_model = MachineModel.objects.create(name="Special Pinball 2000")
        unique_machine = create_machine(slug="special", model=unique_model)
        matching = create_log_entry(machine=unique_machine, text="Fixed it")

        # Create another entry on the default machine
        create_log_entry(machine=self.machine, text="Fixed it too")

        # Search for the unique model name
        results = list(LogEntry.objects.search("Special Pinball 2000"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], matching)

    def test_search_matches_maintainer_username(self):
        """Search matches maintainer user's username."""
        maintainer_user = create_maintainer_user(username="fixerman")
        matching = create_log_entry(machine=self.machine, text="Maintenance work")
        matching.maintainers.add(maintainer_user.maintainer)

        create_log_entry(machine=self.machine, text="Other work")

        results = list(LogEntry.objects.search("fixerman"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], matching)

    def test_search_matches_maintainer_first_name(self):
        """Search matches maintainer user's first name."""
        maintainer_user = create_maintainer_user(
            username="user1", first_name="Wanda", last_name="Worker"
        )
        matching = create_log_entry(machine=self.machine, text="Work done")
        matching.maintainers.add(maintainer_user.maintainer)

        create_log_entry(machine=self.machine, text="Other work")

        results = list(LogEntry.objects.search("Wanda"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], matching)

    def test_search_matches_maintainer_names_field(self):
        """Search matches free-text maintainer_names field."""
        matching = create_log_entry(
            machine=self.machine,
            text="Work done",
            maintainer_names="Wandering Willie",
        )
        create_log_entry(machine=self.machine, text="Other work")

        results = list(LogEntry.objects.search("Wandering"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], matching)

    def test_search_matches_problem_report_description(self):
        """Search matches linked problem report's description."""
        report = create_problem_report(machine=self.machine, description="Coil stop broken")
        matching = create_log_entry(
            machine=self.machine,
            text="Fixed it",
            problem_report=report,
        )
        create_log_entry(machine=self.machine, text="Unrelated work")

        results = list(LogEntry.objects.search("coil stop"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], matching)

    def test_search_returns_distinct_results(self):
        """Search returns distinct results even when multiple maintainers match."""
        m1 = create_maintainer_user(username="alice", first_name="Alice", last_name="Smith")
        m2 = create_maintainer_user(username="bob", first_name="Bob", last_name="Smith")

        entry = create_log_entry(machine=self.machine, text="Team work")
        entry.maintainers.add(m1.maintainer, m2.maintainer)

        results = list(LogEntry.objects.search("Smith"))

        # Should return entry once, not twice
        self.assertEqual(len(results), 1)

    def test_search_is_chainable(self):
        """Search returns a queryset that can be chained."""
        log1 = create_log_entry(machine=self.machine, text="Test work")
        create_log_entry(machine=self.machine, text="Other test work")

        # Chain with .filter()
        results = LogEntry.objects.search("test").filter(pk=log1.pk)

        self.assertEqual(results.count(), 1)
        self.assertEqual(results.first(), log1)
