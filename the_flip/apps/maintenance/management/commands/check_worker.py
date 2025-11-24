"""Check django-q2 worker health and queue status."""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django_q.models import Failure, OrmQ, Success

from the_flip.apps.maintenance.models import LogEntryMedia


class Command(BaseCommand):
    help = "Check django-q2 worker health and queue status"

    def handle(self, *args, **options):
        self._recent_success()
        self._recent_failures()
        self._queue_status()
        self._stuck_videos()

    def _recent_success(self):
        recent_success = Success.objects.filter(
            stopped__gte=timezone.now() - timedelta(hours=24)
        ).count()
        self.stdout.write(f"Recent successful tasks (24h): {recent_success}")

    def _recent_failures(self):
        recent_failures = Failure.objects.filter(
            stopped__gte=timezone.now() - timedelta(hours=24)
        ).count()
        if recent_failures:
            self.stdout.write(self.style.WARNING(f"⚠ Recent failed tasks (24h): {recent_failures}"))
            latest_failure = Failure.objects.order_by("-stopped").first()
            if latest_failure:
                self.stdout.write(f"Latest failure: {latest_failure.func}")
                self.stdout.write(f"Error: {latest_failure.result}")
        else:
            self.stdout.write(self.style.SUCCESS("✓ No recent failures"))

    def _queue_status(self):
        queued = OrmQ.objects.count()
        if queued:
            self.stdout.write(f"Tasks in queue: {queued}")
            oldest = OrmQ.objects.order_by("lock").first()
            if oldest and oldest.lock:
                age = (timezone.now() - oldest.lock).total_seconds()
                if age > 600:
                    self.stdout.write(
                        self.style.ERROR(
                            f"✗ Oldest queued task is {age/60:.1f} minutes old - worker may be stuck!"
                        )
                    )
                else:
                    self.stdout.write(f"Oldest queued task: {age:.0f}s old")
        else:
            self.stdout.write(self.style.SUCCESS("✓ Queue is empty"))

    def _stuck_videos(self):
        stuck_videos = LogEntryMedia.objects.filter(
            media_type=LogEntryMedia.TYPE_VIDEO,
            transcode_status__in=[LogEntryMedia.STATUS_PENDING, LogEntryMedia.STATUS_PROCESSING],
            created__lt=timezone.now() - timedelta(minutes=15),
        ).count()
        if stuck_videos:
            self.stdout.write(
                self.style.ERROR(f"✗ {stuck_videos} video(s) stuck in processing for >15 minutes")
            )
        else:
            self.stdout.write(self.style.SUCCESS("✓ No stuck video transcodes"))
