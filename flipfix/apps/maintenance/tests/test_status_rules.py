"""Tests for the Unplayable → Broken machine-status coupling.

Covers the runtime helpers in
:mod:`flipfix.apps.maintenance.status_rules` and the one-time backfill in
:mod:`flipfix.apps.maintenance.reconcile_machine_status`.
"""

from __future__ import annotations

from django.apps import apps
from django.test import TestCase, tag

from flipfix.apps.catalog.models import MachineInstance
from flipfix.apps.core.test_utils import (
    TestDataMixin,
    create_machine,
    create_problem_report,
)
from flipfix.apps.maintenance.models import LogEntry, ProblemReport
from flipfix.apps.maintenance.reconcile_machine_status import (
    reconcile_unplayable_machine_status,
)
from flipfix.apps.maintenance.status_rules import (
    enforce_unplayable_breaks_machine,
    machine_status_downgrade_prompt,
)

Status = ProblemReport.Status
Priority = ProblemReport.Priority
OperationalStatus = MachineInstance.OperationalStatus


@tag("models")
class EnforceUnplayableBreaksMachineTests(TestDataMixin, TestCase):
    """`enforce_unplayable_breaks_machine` sets Broken, one-directionally."""

    def test_open_unplayable_marks_machine_broken(self):
        report = create_problem_report(
            machine=self.machine, status=Status.OPEN, priority=Priority.UNPLAYABLE
        )

        changed = enforce_unplayable_breaks_machine(report)

        self.assertTrue(changed)
        self.machine.refresh_from_db()
        self.assertEqual(self.machine.operational_status, OperationalStatus.BROKEN)

    def test_no_change_when_report_closed(self):
        report = create_problem_report(
            machine=self.machine, status=Status.CLOSED, priority=Priority.UNPLAYABLE
        )

        self.assertFalse(enforce_unplayable_breaks_machine(report))
        self.machine.refresh_from_db()
        self.assertEqual(self.machine.operational_status, OperationalStatus.GOOD)

    def test_no_change_when_not_unplayable(self):
        report = create_problem_report(
            machine=self.machine, status=Status.OPEN, priority=Priority.MAJOR
        )

        self.assertFalse(enforce_unplayable_breaks_machine(report))
        self.machine.refresh_from_db()
        self.assertEqual(self.machine.operational_status, OperationalStatus.GOOD)

    def test_idempotent_when_already_broken(self):
        machine = create_machine(operational_status=OperationalStatus.BROKEN)
        report = create_problem_report(
            machine=machine, status=Status.OPEN, priority=Priority.UNPLAYABLE
        )

        self.assertFalse(enforce_unplayable_breaks_machine(report))
        machine.refresh_from_db()
        self.assertEqual(machine.operational_status, OperationalStatus.BROKEN)

    def test_actor_is_recorded_and_auto_log_attributed(self):
        create_problem_report(
            machine=self.machine, status=Status.OPEN, priority=Priority.UNPLAYABLE
        )
        # Reload so the machine has no `_skip_auto_log` flag (set by the factory)
        # and the status-change auto-log signal fires.
        report = ProblemReport.objects.select_related("machine").get(machine=self.machine)

        changed = enforce_unplayable_breaks_machine(report, actor=self.maintainer_user)

        self.assertTrue(changed)
        machine = report.machine
        self.assertEqual(machine.operational_status, OperationalStatus.BROKEN)
        self.assertEqual(machine.updated_by, self.maintainer_user)
        auto_log = LogEntry.objects.filter(machine=machine, text__startswith="Status changed")
        self.assertTrue(auto_log.exists())
        self.assertEqual(auto_log.first().created_by, self.maintainer_user)


@tag("models")
class MachineStatusDowngradePromptTests(TestDataMixin, TestCase):
    """`machine_status_downgrade_prompt` offers a return-to-service only when apt."""

    def setUp(self):
        super().setUp()
        self.machine = create_machine(operational_status=OperationalStatus.BROKEN)

    def _closed_unplayable(self):
        return create_problem_report(
            machine=self.machine, status=Status.CLOSED, priority=Priority.UNPLAYABLE
        )

    def test_prompt_after_last_unplayable_closed(self):
        create_problem_report(machine=self.machine, status=Status.OPEN, priority=Priority.MINOR)
        create_problem_report(machine=self.machine, status=Status.OPEN, priority=Priority.MINOR)
        create_problem_report(machine=self.machine, status=Status.OPEN, priority=Priority.MAJOR)
        closed = self._closed_unplayable()

        prompt = machine_status_downgrade_prompt(closed)

        self.assertIsNotNone(prompt)
        self.assertEqual(prompt["remaining_open"], 3)
        self.assertEqual(prompt["machine_slug"], self.machine.slug)
        # Breakdown is ordered by Priority enum position (Major before Minor).
        self.assertEqual(
            prompt["breakdown"],
            [
                {"priority": Priority.MAJOR, "label": "Major", "count": 1},
                {"priority": Priority.MINOR, "label": "Minor", "count": 2},
            ],
        )
        self.assertIn("Set machine to Good?", prompt["message"])
        self.assertIn("1 Major", prompt["message"])
        self.assertIn("2 Minor", prompt["message"])

    def test_prompt_message_when_no_reports_remain(self):
        closed = self._closed_unplayable()

        prompt = machine_status_downgrade_prompt(closed)

        self.assertIsNotNone(prompt)
        self.assertEqual(prompt["remaining_open"], 0)
        self.assertEqual(prompt["breakdown"], [])
        self.assertIn("No open reports remain", prompt["message"])

    def test_none_when_other_unplayable_still_open(self):
        create_problem_report(
            machine=self.machine, status=Status.OPEN, priority=Priority.UNPLAYABLE
        )
        closed = self._closed_unplayable()

        self.assertIsNone(machine_status_downgrade_prompt(closed))

    def test_none_when_machine_not_broken(self):
        good_machine = create_machine(operational_status=OperationalStatus.GOOD)
        closed = create_problem_report(
            machine=good_machine, status=Status.CLOSED, priority=Priority.UNPLAYABLE
        )

        self.assertIsNone(machine_status_downgrade_prompt(closed))

    def test_none_when_closed_report_not_unplayable(self):
        closed = create_problem_report(
            machine=self.machine, status=Status.CLOSED, priority=Priority.MAJOR
        )

        self.assertIsNone(machine_status_downgrade_prompt(closed))

    def test_none_when_report_still_open(self):
        still_open = create_problem_report(
            machine=self.machine, status=Status.OPEN, priority=Priority.UNPLAYABLE
        )

        self.assertIsNone(machine_status_downgrade_prompt(still_open))


@tag("models")
class ReconcileUnplayableMachineStatusTests(TestDataMixin, TestCase):
    """The one-time backfill fixes drift one-directionally and documents it."""

    @staticmethod
    def _run():
        return reconcile_unplayable_machine_status(apps, log=lambda message: None)

    def test_marks_drifted_machine_broken_and_logs_cleanup(self):
        create_problem_report(
            machine=self.machine, status=Status.OPEN, priority=Priority.UNPLAYABLE
        )

        result = self._run()

        self.assertEqual(result["updated"], 1)
        self.machine.refresh_from_db()
        self.assertEqual(self.machine.operational_status, OperationalStatus.BROKEN)
        self.assertTrue(
            LogEntry.objects.filter(
                machine=self.machine, text__icontains="automated cleanup"
            ).exists()
        )

    def test_skips_machine_already_broken(self):
        machine = create_machine(operational_status=OperationalStatus.BROKEN)
        create_problem_report(machine=machine, status=Status.OPEN, priority=Priority.UNPLAYABLE)

        result = self._run()

        self.assertEqual(result["updated"], 0)
        self.assertFalse(
            LogEntry.objects.filter(machine=machine, text__icontains="automated cleanup").exists()
        )

    def test_skips_machine_without_open_unplayable(self):
        # A closed unplayable report and an open non-unplayable report both leave
        # the machine untouched.
        create_problem_report(
            machine=self.machine, status=Status.CLOSED, priority=Priority.UNPLAYABLE
        )
        create_problem_report(machine=self.machine, status=Status.OPEN, priority=Priority.MINOR)

        result = self._run()

        self.assertEqual(result["updated"], 0)
        self.machine.refresh_from_db()
        self.assertEqual(self.machine.operational_status, OperationalStatus.GOOD)

    def test_does_not_unbreak_machine_without_reports(self):
        machine = create_machine(operational_status=OperationalStatus.BROKEN)

        result = self._run()

        self.assertEqual(result["updated"], 0)
        machine.refresh_from_db()
        self.assertEqual(machine.operational_status, OperationalStatus.BROKEN)
