"""Tests for the backfill_maintenance_tasks management command."""

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, tag

from flipfix.apps.core.test_utils import (
    create_log_entry,
    create_machine,
    create_problem_report,
)
from flipfix.apps.maintenance.models import LogEntry, MaintenanceTaskType, ProblemReport

INTAKE_MARKER = "Intake completed"
INTAKE_DESC = (
    "The Flip's machine acquisition evaluation checklist\n\n"
    "## Checklist\n"
    "- [x] outside\n"
    "- [x] inside backbox\n"
    "- [x] while playing\n"
    "- [x] playfield\n"
)


def run(**kwargs):
    out = StringIO()
    call_command("backfill_maintenance_tasks", stdout=out, stderr=out, **kwargs)
    return out.getvalue()


@tag("commands")
class BackfillWorkLogTests(TestCase):
    def setUp(self):
        self.machine = create_machine()
        self.clean = MaintenanceTaskType.objects.get(slug="clean-playfield")

    def test_dry_run_makes_no_changes(self):
        entry = create_log_entry(machine=self.machine, text="Cleaned the playfield thoroughly")
        run()
        self.assertEqual(entry.maintenance_tasks.count(), 0)

    def test_apply_tags_matching_entry(self):
        entry = create_log_entry(machine=self.machine, text="Cleaned the playfield thoroughly")
        run(apply=True)
        self.assertIn(self.clean, entry.maintenance_tasks.all())

    def test_apply_is_idempotent(self):
        entry = create_log_entry(machine=self.machine, text="cleaned playfield")
        run(apply=True)
        run(apply=True)
        self.assertEqual(entry.maintenance_tasks.filter(slug="clean-playfield").count(), 1)

    def test_non_matching_entry_untouched(self):
        entry = create_log_entry(machine=self.machine, text="Adjusted the flippers")
        run(apply=True)
        self.assertEqual(entry.maintenance_tasks.count(), 0)

    def test_invalid_threshold_raises(self):
        with self.assertRaises(CommandError):
            run(intake_threshold=1.5)

    def test_unknown_task_slug_raises(self):
        with self.assertRaises(CommandError):
            run(task="bogus-task")


@tag("commands")
class BackfillIntakeTests(TestCase):
    def setUp(self):
        self.machine = create_machine()

    def _seed_tasks(self):
        return set(
            MaintenanceTaskType.objects.filter(
                slug__in=["clean-playfield", "replace-balls", "replace-rubbers"]
            )
        )

    def _intake(self, status=ProblemReport.Status.CLOSED, description=INTAKE_DESC):
        return create_problem_report(machine=self.machine, status=status, description=description)

    def test_closed_completed_intake_credits_all_three(self):
        report = self._intake()
        run(apply=True)
        entry = LogEntry.objects.filter(problem_report=report).first()
        self.assertIsNotNone(entry)
        self.assertEqual(set(entry.maintenance_tasks.all()), self._seed_tasks())
        self.assertTrue(entry.maintainer_names)

    def test_open_intake_skipped(self):
        self._intake(status=ProblemReport.Status.OPEN)
        run(apply=True)
        self.assertFalse(LogEntry.objects.filter(text__startswith=INTAKE_MARKER).exists())

    def test_under_threshold_skipped(self):
        desc = "acquisition evaluation checklist\n- [x] a\n- [ ] b\n- [ ] c\n- [ ] d\n"
        self._intake(description=desc)
        run(apply=True)
        self.assertFalse(LogEntry.objects.filter(text__startswith=INTAKE_MARKER).exists())

    def test_zero_checkbox_intake_skipped_without_error(self):
        self._intake(description="acquisition evaluation checklist, no checkboxes here")
        run(apply=True)  # must not raise ZeroDivisionError
        self.assertFalse(LogEntry.objects.filter(text__startswith=INTAKE_MARKER).exists())

    def test_apply_is_idempotent(self):
        self._intake()
        run(apply=True)
        run(apply=True)
        self.assertEqual(LogEntry.objects.filter(text__startswith=INTAKE_MARKER).count(), 1)
