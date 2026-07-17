"""Tests for the ensure_scheduled_tasks management command."""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase, tag
from django_q.models import Schedule

from flipfix.apps.core.management.commands.ensure_scheduled_tasks import (
    DAILY_REPORT_FUNC,
    DAILY_REPORT_NAME,
    FLUSH_EVERY_MINUTES,
    FLUSH_FUNC,
    FLUSH_NAME,
)


@tag("commands")
class EnsureScheduledTasksTests(TestCase):
    def _run(self):
        call_command("ensure_scheduled_tasks", stdout=StringIO())

    def test_creates_daily_report_schedule(self):
        self._run()
        schedule = Schedule.objects.get(name=DAILY_REPORT_NAME)
        self.assertEqual(schedule.func, DAILY_REPORT_FUNC)
        self.assertEqual(schedule.schedule_type, Schedule.DAILY)
        self.assertIsNotNone(schedule.next_run)

    def test_creates_flush_schedule(self):
        self._run()
        schedule = Schedule.objects.get(name=FLUSH_NAME)
        self.assertEqual(schedule.func, FLUSH_FUNC)
        self.assertEqual(schedule.schedule_type, Schedule.MINUTES)
        self.assertEqual(schedule.minutes, FLUSH_EVERY_MINUTES)
        self.assertIsNotNone(schedule.next_run)

    def test_is_idempotent(self):
        self._run()
        self._run()
        self.assertEqual(Schedule.objects.filter(name=DAILY_REPORT_NAME).count(), 1)
        self.assertEqual(Schedule.objects.filter(name=FLUSH_NAME).count(), 1)

    def test_preserves_next_run_across_runs(self):
        self._run()
        original = Schedule.objects.get(name=DAILY_REPORT_NAME).next_run
        self._run()
        self.assertEqual(Schedule.objects.get(name=DAILY_REPORT_NAME).next_run, original)
