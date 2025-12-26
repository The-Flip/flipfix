"""Maintenance domain models."""

from __future__ import annotations

from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from simple_history.models import HistoricalRecords

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.core.models import AbstractMedia, TimeStampedMixin


class ProblemReportQuerySet(models.QuerySet):
    """Custom queryset for ProblemReport with common filters."""

    def open(self):
        """Return only open problem reports."""
        return self.filter(status=ProblemReport.Status.OPEN)

    def _build_description_and_reporter_q(self, query: str) -> Q:
        """Build Q object for searching description and reporter fields.

        This is the core search pattern shared across all problem report search
        contexts. It matches:
        - Problem description
        - Reporter name (free-text field)
        - Reporter user's username, first name, last name (via FK)
        """
        return (
            Q(description__icontains=query)
            | Q(reported_by_name__icontains=query)
            | Q(reported_by_user__username__icontains=query)
            | Q(reported_by_user__first_name__icontains=query)
            | Q(reported_by_user__last_name__icontains=query)
        )

    def _build_log_entry_q(self, query: str) -> Q:
        """Build Q object for searching linked log entry fields.

        Matches log entry text and maintainer names.
        """
        return (
            Q(log_entries__text__icontains=query)
            | Q(log_entries__maintainers__user__username__icontains=query)
            | Q(log_entries__maintainers__user__first_name__icontains=query)
            | Q(log_entries__maintainers__user__last_name__icontains=query)
            | Q(log_entries__maintainer_names__icontains=query)
        )

    def search(self, query: str = ""):
        """
        Global search across multiple fields.

        Searches: description, machine name, reporter name/username,
        and linked log entry text/maintainers.

        Returns unfiltered queryset if query is empty/whitespace.
        Caller is responsible for ordering.
        """
        query = (query or "").strip()
        if not query:
            return self

        return self.filter(
            self._build_description_and_reporter_q(query)
            | Q(machine__model__name__icontains=query)
            | Q(machine__name__icontains=query)
            | self._build_log_entry_q(query)
        ).distinct()

    def search_for_machine(self, query: str = ""):
        """
        Machine-scoped search: excludes machine name.

        When viewing a specific machine's problem reports, machine name is
        redundant to search.

        Returns unfiltered queryset if query is empty/whitespace.
        Caller is responsible for ordering.
        """
        query = (query or "").strip()
        if not query:
            return self

        return self.filter(
            self._build_description_and_reporter_q(query) | self._build_log_entry_q(query)
        ).distinct()


class ProblemReport(TimeStampedMixin):
    """Visitor-submitted problem report about a machine."""

    class Status(models.TextChoices):
        """Whether a problem report is still active or resolved."""

        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    class ProblemType(models.TextChoices):
        """Categories of problems visitors can report."""

        STUCK_BALL = "stuck_ball", "Stuck Ball"
        NO_CREDITS = "no_credits", "No Credits"
        OTHER = "other", "Other"

    machine = models.ForeignKey(
        MachineInstance,
        on_delete=models.CASCADE,
        related_name="problem_reports",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
        db_index=True,
    )
    problem_type = models.CharField(
        max_length=50,
        choices=ProblemType.choices,
        default=ProblemType.OTHER,
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
        return f"{self.machine.name} – {self.get_problem_type_display()}"

    def get_admin_history_url(self) -> str:
        """Return URL to this report's Django admin change history."""
        return reverse("admin:maintenance_problemreport_history", args=[self.pk])

    @property
    def reporter_display(self) -> str:
        """Return the best available name for who reported this problem."""
        # Prefer typed-in name (e.g., from shared terminal account)
        if self.reported_by_name:
            return self.reported_by_name
        if self.reported_by_user:
            return self.reported_by_user.get_full_name() or self.reported_by_user.get_username()
        if self.reported_by_contact:
            return self.reported_by_contact
        return "Anonymous"


class LogEntryQuerySet(models.QuerySet):
    """Custom queryset for LogEntry with common filters."""

    def _build_text_and_maintainer_q(self, query: str) -> Q:
        """Build Q object for searching text and maintainer fields.

        This is the core search pattern shared across all log entry search
        contexts. It matches:
        - Log entry text
        - Maintainer usernames, first names, last names (via FK)
        - Free-text maintainer_names field
        """
        return (
            Q(text__icontains=query)
            | Q(maintainers__user__username__icontains=query)
            | Q(maintainers__user__first_name__icontains=query)
            | Q(maintainers__user__last_name__icontains=query)
            | Q(maintainer_names__icontains=query)
        )

    def search(self, query: str = ""):
        """
        Global search across multiple fields.

        Searches: text, machine name, maintainer names/usernames,
        and linked problem report description.

        Returns unfiltered queryset if query is empty/whitespace.
        Caller is responsible for ordering.
        """
        query = (query or "").strip()
        if not query:
            return self

        return self.filter(
            self._build_text_and_maintainer_q(query)
            | Q(machine__model__name__icontains=query)
            | Q(machine__name__icontains=query)
            | Q(problem_report__description__icontains=query)
        ).distinct()

    def search_for_machine(self, query: str = ""):
        """
        Machine-scoped search: excludes machine name, includes problem report fields.

        When viewing a specific machine's logs, machine name is redundant to search.
        But we do want to find logs by their linked problem report's description
        or reporter name.

        Returns unfiltered queryset if query is empty/whitespace.
        Caller is responsible for ordering.
        """
        query = (query or "").strip()
        if not query:
            return self

        return self.filter(
            self._build_text_and_maintainer_q(query)
            | Q(problem_report__description__icontains=query)
            | Q(problem_report__reported_by_name__icontains=query)
        ).distinct()

    def search_for_problem_report(self, query: str = ""):
        """
        Problem-report-scoped search: only text and maintainers.

        When viewing a specific problem report's logs, both the machine name
        and the problem report's own fields are redundant to search.

        Returns unfiltered queryset if query is empty/whitespace.
        Caller is responsible for ordering.
        """
        query = (query or "").strip()
        if not query:
            return self

        return self.filter(self._build_text_and_maintainer_q(query)).distinct()


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

    objects = LogEntryQuerySet.as_manager()
    history = HistoricalRecords()

    class Meta:
        ordering = ["-work_date"]
        verbose_name = "Log entry"
        verbose_name_plural = "Log entries"

    def __str__(self) -> str:
        return f"Log entry for {self.machine.name}"

    def get_admin_history_url(self) -> str:
        """Return URL to this entry's Django admin change history."""
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
    """Generate upload path for log entry media files."""
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
    thumbnail_file = models.FileField(upload_to=log_media_upload_to, blank=True, null=True)
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
        """Return URL to this media's Django admin change history."""
        return reverse("admin:maintenance_logentrymedia_history", args=[self.pk])


def problem_report_media_upload_to(instance: ProblemReportMedia, filename: str) -> str:
    """Generate upload path for problem report media files."""
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
    thumbnail_file = models.FileField(
        upload_to=problem_report_media_upload_to, blank=True, null=True
    )
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
        """Return URL to this media's Django admin change history."""
        return reverse("admin:maintenance_problemreportmedia_history", args=[self.pk])
