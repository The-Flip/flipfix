"""Ensure the app's recurring django-q schedules exist.

Idempotent — run at deploy time alongside ``migrate``. The existing ``qcluster``
worker runs the schedules; no extra process is needed. Currently registers the
daily maintenance report post.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django_q.models import Schedule

DAILY_REPORT_NAME = "daily-maintenance-report"
DAILY_REPORT_FUNC = "flipfix.apps.discord.tasks.post_daily_maintenance_report"
DAILY_REPORT_HOUR = 8  # local time


def _next_run_at(hour: int):
    """The next occurrence of ``hour``:00 local time (today if still ahead, else tomorrow)."""
    now = timezone.localtime()
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


class Command(BaseCommand):
    help = "Create or update the app's recurring django-q schedules (idempotent)."

    def handle(self, *args: object, **options: object) -> None:
        schedule, created = Schedule.objects.get_or_create(
            name=DAILY_REPORT_NAME,
            defaults={
                "func": DAILY_REPORT_FUNC,
                "schedule_type": Schedule.DAILY,
                "next_run": _next_run_at(DAILY_REPORT_HOUR),
            },
        )
        if not created:
            # Keep the existing next_run (don't reset the cadence on every deploy);
            # only correct the func / type / a missing next_run.
            changed = False
            if schedule.func != DAILY_REPORT_FUNC:
                schedule.func = DAILY_REPORT_FUNC
                changed = True
            if schedule.schedule_type != Schedule.DAILY:
                schedule.schedule_type = Schedule.DAILY
                changed = True
            if schedule.next_run is None:
                schedule.next_run = _next_run_at(DAILY_REPORT_HOUR)
                changed = True
            if changed:
                schedule.save()

        verb = "Created" if created else "Ensured"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} schedule '{schedule.name}' (next run {schedule.next_run:%Y-%m-%d %H:%M})"
            )
        )
