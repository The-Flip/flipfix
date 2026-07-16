"""Unit tests for the daily-report health classifier (pure, no DB)."""

from __future__ import annotations

from datetime import timedelta

from django.test import SimpleTestCase, tag
from django.utils import timezone

from flipfix.apps.catalog.models import MachineInstance
from flipfix.apps.maintenance.models import ProblemReport
from flipfix.apps.maintenance.reports import (
    MachineHealth,
    classify,
    humanize_ago,
    state_date,
)

S = MachineInstance.OperationalStatus
P = ProblemReport.Priority


@tag("models")
class ClassifyTests(SimpleTestCase):
    def test_broken_status_is_down(self):
        self.assertEqual(classify(S.BROKEN, set()), "down")

    def test_open_unplayable_report_is_down_even_if_status_good(self):
        self.assertEqual(classify(S.GOOD, {P.UNPLAYABLE}), "down")

    def test_fixing_status_beats_major_report(self):
        # worst-wins order: fixing is checked before major
        self.assertEqual(classify(S.FIXING, {P.MAJOR}), "fixing")

    def test_major_report(self):
        self.assertEqual(classify(S.GOOD, {P.MAJOR}), "major")

    def test_untriaged_report(self):
        self.assertEqual(classify(S.GOOD, {P.UNTRIAGED}), "untriaged")

    def test_minor_report(self):
        self.assertEqual(classify(S.GOOD, {P.MINOR}), "minor")

    def test_task_priority_never_changes_emoji(self):
        # A task alongside a minor doesn't escalate; a task alone doesn't either.
        self.assertEqual(classify(S.GOOD, {P.MINOR, P.TASK}), "minor")

    def test_only_task_reports_reads_as_good(self):
        self.assertEqual(classify(S.GOOD, {P.TASK}), "good")

    def test_task_only_on_unknown_status_stays_unknown(self):
        # Tasks are invisible, so the machine falls back to its status.
        self.assertEqual(classify(S.UNKNOWN, {P.TASK}), "unknown")

    def test_unknown_status_when_no_reports(self):
        self.assertEqual(classify(S.UNKNOWN, set()), "unknown")

    def test_good_when_no_reports(self):
        self.assertEqual(classify(S.GOOD, set()), "good")


@tag("models")
class StateDateTests(SimpleTestCase):
    def setUp(self):
        self.now = timezone.now()

    def test_down_uses_marked_down(self):
        d = self.now - timedelta(days=5)
        self.assertEqual(state_date(MachineHealth(health="down", marked_down_at=d)), d)

    def test_untriaged_uses_report_date(self):
        d = self.now - timedelta(days=2)
        m = MachineHealth(health="untriaged", report_dates={"untriaged": d})
        self.assertEqual(state_date(m), d)

    def test_major_uses_report_date(self):
        d = self.now - timedelta(days=3)
        m = MachineHealth(health="major", report_dates={"major": d})
        self.assertEqual(state_date(m), d)

    def test_fixing_uses_last_log(self):
        d = self.now - timedelta(days=1)
        self.assertEqual(state_date(MachineHealth(health="fixing", last_worked_at=d)), d)

    def test_missing_date_is_none(self):
        self.assertIsNone(state_date(MachineHealth(health="down")))


@tag("models")
class HumanizeAgoTests(SimpleTestCase):
    def setUp(self):
        self.now = timezone.now()

    def test_none_is_unknown(self):
        self.assertEqual(humanize_ago(None, self.now), "Unknown")

    def test_today(self):
        self.assertEqual(humanize_ago(self.now, self.now), "today")

    def test_hours(self):
        self.assertEqual(humanize_ago(self.now - timedelta(hours=5), self.now), "5h ago")

    def test_yesterday(self):
        self.assertEqual(humanize_ago(self.now - timedelta(days=1), self.now), "yesterday")

    def test_days(self):
        self.assertEqual(humanize_ago(self.now - timedelta(days=9), self.now), "9d ago")

    def test_weeks(self):
        self.assertEqual(humanize_ago(self.now - timedelta(days=21), self.now), "3w ago")

    def test_months(self):
        self.assertEqual(humanize_ago(self.now - timedelta(days=90), self.now), "3mo ago")
