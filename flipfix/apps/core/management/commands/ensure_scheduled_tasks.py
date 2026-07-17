"""Ensure the app's recurring django-q schedules exist.

Idempotent — run at deploy time alongside ``migrate``. The existing ``qcluster``
worker runs the schedules; no extra process is needed. Registers:

* the daily maintenance report post, and
* the once-a-minute flush of coalesced Discord notifications.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django_q.models import Schedule

DAILY_REPORT_NAME = "daily-maintenance-report"
DAILY_REPORT_FUNC = "flipfix.apps.discord.tasks.post_daily_maintenance_report"
DAILY_REPORT_HOUR = 8  # local time

FLUSH_NAME = "flush-discord-notifications"
FLUSH_FUNC = "flipfix.apps.discord.tasks.flush_pending_notifications"
FLUSH_EVERY_MINUTES = 1


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
        daily = self._ensure(
            name=DAILY_REPORT_NAME,
            func=DAILY_REPORT_FUNC,
            schedule_type=Schedule.DAILY,
            next_run=_next_run_at(DAILY_REPORT_HOUR),
        )
        flush = self._ensure(
            name=FLUSH_NAME,
            func=FLUSH_FUNC,
            schedule_type=Schedule.MINUTES,
            minutes=FLUSH_EVERY_MINUTES,
            next_run=timezone.now(),
        )
        for schedule in (daily, flush):
            self.stdout.write(
                self.style.SUCCESS(
                    f"Ensured schedule '{schedule.name}' (next run {schedule.next_run:%Y-%m-%d %H:%M})"
                )
            )

    def _ensure(
        self,
        *,
        name: str,
        func: str,
        schedule_type: str,
        next_run,
        minutes: int | None = None,
    ) -> Schedule:
        """Create the named schedule, or correct drift on an existing one.

        Preserves an existing ``next_run`` so redeploys don't reset the cadence;
        only the func, type, interval, and a missing ``next_run`` are corrected.
        """
        defaults: dict[str, object] = {
            "func": func,
            "schedule_type": schedule_type,
            "next_run": next_run,
        }
        if minutes is not None:
            defaults["minutes"] = minutes

        schedule, created = Schedule.objects.get_or_create(name=name, defaults=defaults)
        if created:
            return schedule

        changed = False
        cadence_changed = False
        if schedule.func != func:
            schedule.func = func
            changed = True
        if schedule.schedule_type != schedule_type:
            schedule.schedule_type = schedule_type
            changed = True
            cadence_changed = True
        if minutes is not None and schedule.minutes != minutes:
            schedule.minutes = minutes
            changed = True
            cadence_changed = True
        # A cadence change invalidates the old next_run (it may sit far in the
        # future on the previous schedule), so recompute it; otherwise preserve it.
        if schedule.next_run is None or cadence_changed:
            schedule.next_run = next_run
            changed = True
        if changed:
            schedule.save()
        return schedule
