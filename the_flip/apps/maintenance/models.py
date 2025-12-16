"""Maintenance domain models."""

from __future__ import annotations

from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone
from simple_history.models import HistoricalRecords

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.core.models import AbstractMedia, TimeStampedMixin


class ProblemReportQuerySet(models.QuerySet):
    def open(self):
        return self.filter(status=ProblemReport.STATUS_OPEN)


class ProblemReport(TimeStampedMixin):
    """Visitor-submitted problem report about a machine."""

    STATUS_OPEN = "open"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_CLOSED, "Closed"),
    ]

    PROBLEM_STUCK_BALL = "stuck_ball"
    PROBLEM_NO_CREDITS = "no_credits"
    PROBLEM_OTHER = "other"
    PROBLEM_TYPE_CHOICES = [
        (PROBLEM_STUCK_BALL, "Stuck Ball"),
        (PROBLEM_NO_CREDITS, "No Credits"),
        (PROBLEM_OTHER, "Other"),
    ]

    machine = models.ForeignKey(
        MachineInstance,
        on_delete=models.CASCADE,
        related_name="problem_reports",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_OPEN,
        db_index=True,
    )
    problem_type = models.CharField(
        max_length=50,
        choices=PROBLEM_TYPE_CHOICES,
        default=PROBLEM_OTHER,
        db_index=True,
    )
    description = models.TextField(blank=True)
    reported_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="problem_reports_created",
    )
    reported_by_name = models.CharField(max_length=200, blank=True)
    reported_by_contact = models.CharField(max_length=200, blank=True)
    device_info = models.CharField(max_length=200, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    objects = ProblemReportQuerySet.as_manager()
    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"{self.machine.display_name} – {self.get_problem_type_display()}"

    def get_admin_history_url(self) -> str:
        return reverse("admin:maintenance_problemreport_history", args=[self.pk])

    @property
    def reporter_display(self) -> str:
        # Prefer typed-in name (e.g., from shared terminal account)
        if self.reported_by_name:
            return self.reported_by_name
        if self.reported_by_user:
            return self.reported_by_user.get_full_name() or self.reported_by_user.get_username()
        if self.reported_by_contact:
            return self.reported_by_contact
        return "Anonymous"


class LogEntry(TimeStampedMixin):
    """Maintainer log entry documenting work on a machine."""

    machine = models.ForeignKey(
        MachineInstance,
        on_delete=models.CASCADE,
        related_name="log_entries",
    )
    problem_report = models.ForeignKey(
        ProblemReport,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="log_entries",
        help_text="Optional link to a problem report this log entry addresses.",
    )
    maintainers = models.ManyToManyField(Maintainer, blank=True, related_name="log_entries")
    maintainer_names = models.CharField(
        max_length=120,
        blank=True,
        help_text="Comma-separated names when maintainers are not in the system.",
    )
    text = models.TextField()
    work_date = models.DateTimeField(
        default=timezone.now,
        help_text="When the work was performed. Defaults to now if not specified.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="log_entries_created",
        help_text="The user who created this log entry (for audit trail).",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["-work_date"]
        verbose_name = "Log entry"
        verbose_name_plural = "Log entries"

    def __str__(self) -> str:
        return f"Log entry for {self.machine.display_name}"

    def get_admin_history_url(self) -> str:
        return reverse("admin:maintenance_logentry_history", args=[self.pk])

    def clean(self):
        super().clean()
        has_maintainer_names = bool((self.maintainer_names or "").strip())
        pending_maintainers = getattr(self, "_pending_maintainers", None)

        try:
            has_saved_maintainers = self.pk and self.maintainers.exists()
        except ValueError:
            has_saved_maintainers = False

        has_any_maintainer = has_saved_maintainers or bool(pending_maintainers)

        if not has_any_maintainer and not has_maintainer_names:
            raise ValidationError("Provide at least one maintainer or maintainer name.")


def log_media_upload_to(instance: LogEntryMedia, filename: str) -> str:
    return f"log_entries/{instance.log_entry_id}/{uuid4()}-{filename}"


class LogEntryMedia(AbstractMedia):
    """Media files attached to a log entry."""

    parent_field_name = "log_entry"

    log_entry = models.ForeignKey(
        LogEntry,
        on_delete=models.CASCADE,
        related_name="media",
    )
    file = models.FileField(upload_to=log_media_upload_to)
    thumbnail_file = models.FileField(upload_to=log_media_upload_to, blank=True)
    transcoded_file = models.FileField(upload_to=log_media_upload_to, blank=True, null=True)
    poster_file = models.ImageField(upload_to=log_media_upload_to, blank=True, null=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["display_order", "created_at"]
        verbose_name = "Log entry media"
        verbose_name_plural = "Log entry media"

    def __str__(self) -> str:
        return f"{self.get_media_type_display()} for log entry {self.log_entry_id}"

    def get_admin_history_url(self) -> str:
        return reverse("admin:maintenance_logentrymedia_history", args=[self.pk])


def problem_report_media_upload_to(instance: ProblemReportMedia, filename: str) -> str:
    return f"problem_reports/{instance.problem_report_id}/{uuid4()}-{filename}"


class ProblemReportMedia(AbstractMedia):
    """Media files attached to a problem report."""

    parent_field_name = "problem_report"

    problem_report = models.ForeignKey(
        ProblemReport,
        on_delete=models.CASCADE,
        related_name="media",
    )
    file = models.FileField(upload_to=problem_report_media_upload_to)
    thumbnail_file = models.FileField(upload_to=problem_report_media_upload_to, blank=True)
    transcoded_file = models.FileField(
        upload_to=problem_report_media_upload_to, blank=True, null=True
    )
    poster_file = models.ImageField(upload_to=problem_report_media_upload_to, blank=True, null=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["display_order", "created_at"]
        verbose_name = "Problem report media"
        verbose_name_plural = "Problem report media"

    def __str__(self) -> str:
        return f"{self.get_media_type_display()} for problem report {self.problem_report_id}"

    def get_admin_history_url(self) -> str:
        return reverse("admin:maintenance_problemreportmedia_history", args=[self.pk])
