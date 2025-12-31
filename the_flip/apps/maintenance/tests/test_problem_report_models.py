"""Tests for ProblemReport model behavior."""

from datetime import timedelta

from django.test import TestCase, tag
from django.utils import timezone

from the_flip.apps.core.test_utils import (
    TestDataMixin,
    create_problem_report,
)
from the_flip.apps.maintenance.models import ProblemReport


@tag("models")
class ProblemReportOccurredAtTests(TestDataMixin, TestCase):
    """Tests for ProblemReport occurred_at field."""

    def test_occurred_at_defaults_to_now(self):
        """occurred_at defaults to current time when not specified."""
        before = timezone.now()
        report = create_problem_report(machine=self.machine, description="Test report")
        after = timezone.now()

        self.assertIsNotNone(report.occurred_at)
        self.assertGreaterEqual(report.occurred_at, before)
        self.assertLessEqual(report.occurred_at, after)

    def test_occurred_at_can_be_set_explicitly(self):
        """occurred_at can be set to a specific datetime."""
        specific_date = timezone.now() - timedelta(days=5)
        report = create_problem_report(
            machine=self.machine,
            description="Historical report",
            occurred_at=specific_date,
        )
        self.assertEqual(report.occurred_at, specific_date)

    def test_problem_reports_ordered_by_occurred_at_descending(self):
        """Problem reports are ordered by occurred_at descending by default.

        Creates records where created_at order differs from occurred_at order
        to ensure we're actually sorting by occurred_at, not created_at.
        """
        now = timezone.now()

        # Create in this order: middle, oldest, newest
        # If sorting by created_at, we'd get: middle, oldest, newest
        # If sorting by occurred_at desc, we should get: newest, middle, oldest
        middle = create_problem_report(
            machine=self.machine,
            description="Middle report",
            occurred_at=now - timedelta(days=5),
        )
        oldest = create_problem_report(
            machine=self.machine,
            description="Oldest report",
            occurred_at=now - timedelta(days=10),
        )
        newest = create_problem_report(
            machine=self.machine,
            description="Newest report",
            occurred_at=now,
        )

        reports = list(ProblemReport.objects.all())
        self.assertEqual(reports, [newest, middle, oldest])
