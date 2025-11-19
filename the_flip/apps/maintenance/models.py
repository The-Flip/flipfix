"""Maintenance domain models."""
from __future__ import annotations

from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.core.models import TimeStampedModel


class ProblemReportQuerySet(models.QuerySet):
    def open(self):
        return self.filter(status=ProblemReport.STATUS_OPEN)


class ProblemReport(TimeStampedModel):
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

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"{self.machine.display_name} – {self.get_problem_type_display()}"

    @property
    def reporter_display(self) -> str:
        if self.reported_by_user:
            return self.reported_by_user.get_full_name() or self.reported_by_user.get_username()
        if self.reported_by_name:
            return self.reported_by_name
        if self.reported_by_contact:
            return self.reported_by_contact
        return ""


class LogEntry(TimeStampedModel):
    """Maintainer log entry documenting work on a machine."""

    machine = models.ForeignKey(
        MachineInstance,
        on_delete=models.CASCADE,
        related_name="log_entries",
    )
    maintainers = models.ManyToManyField(Maintainer, blank=True, related_name="log_entries")
    maintainer_names = models.CharField(
        max_length=120,
        blank=True,
        help_text="Comma-separated names when maintainers are not in the system.",
    )
    text = models.TextField()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Log entry for {self.machine.display_name}"

    def clean(self):
        super().clean()
        if not self.pk and not self.maintainers.exists() and not self.maintainer_names:
            raise ValidationError("Provide at least one maintainer or maintainer name.")


def log_media_upload_to(instance: "LogEntryMedia", filename: str) -> str:
    return f"log_entries/{instance.log_entry_id}/{uuid4()}-{filename}"


class LogEntryMedia(TimeStampedModel):
    """Media files attached to a log entry."""

    TYPE_PHOTO = "photo"
    TYPE_VIDEO = "video"
    MEDIA_CHOICES = [
        (TYPE_PHOTO, "Photo"),
        (TYPE_VIDEO, "Video"),
    ]

    log_entry = models.ForeignKey(
        LogEntry,
        on_delete=models.CASCADE,
        related_name="media",
    )
    media_type = models.CharField(max_length=20, choices=MEDIA_CHOICES)
    file = models.FileField(upload_to=log_media_upload_to)
    thumbnail_file = models.FileField(upload_to=log_media_upload_to, blank=True)
    display_order = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["display_order", "created_at"]

    def __str__(self) -> str:
        return f"{self.get_media_type_display()} for log entry {self.log_entry_id}"
