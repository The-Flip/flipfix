"""Parts management models."""

from __future__ import annotations

from uuid import uuid4

from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone
from simple_history.models import HistoricalRecords

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.core.models import AbstractMedia, TimeStampedMixin


class PartRequestQuerySet(models.QuerySet):
    """Custom queryset for PartRequest model."""

    def active(self):
        """Return part requests that are not cancelled."""
        return self.exclude(status=PartRequest.Status.CANCELLED)

    def pending(self):
        """Return part requests that are requested or ordered (not yet received)."""
        return self.filter(status__in=[PartRequest.Status.REQUESTED, PartRequest.Status.ORDERED])

    def _build_text_and_requester_q(self, query: str):
        """Build Q object for text and requester name search."""
        return (
            models.Q(text__icontains=query)
            | models.Q(status__icontains=query)
            | models.Q(requested_by__user__username__icontains=query)
            | models.Q(requested_by__user__first_name__icontains=query)
            | models.Q(requested_by__user__last_name__icontains=query)
            | models.Q(requested_by_name__icontains=query)
        )

    def _build_update_q(self, query: str):
        """Build Q object for searching linked updates."""
        return (
            models.Q(updates__text__icontains=query)
            | models.Q(updates__posted_by__user__username__icontains=query)
            | models.Q(updates__posted_by__user__first_name__icontains=query)
            | models.Q(updates__posted_by__user__last_name__icontains=query)
            | models.Q(updates__posted_by_name__icontains=query)
        )

    def search(self, query: str = ""):
        """
        Global search across multiple fields.

        Searches: text, status, machine name, requester name/username,
        and linked update text/poster names.

        Returns unfiltered queryset if query is empty/whitespace.
        Caller is responsible for ordering.
        """
        query = (query or "").strip()
        if not query:
            return self

        return self.filter(
            self._build_text_and_requester_q(query)
            | models.Q(machine__model__name__icontains=query)
            | models.Q(machine__name__icontains=query)
            | self._build_update_q(query)
        ).distinct()

    def search_for_machine(self, query: str = ""):
        """
        Machine-scoped search: excludes machine name, includes linked updates.

        When viewing a specific machine's part requests, machine name is
        redundant to search. But we do want to find part requests by their
        linked updates' text or poster names.

        Returns unfiltered queryset if query is empty/whitespace.
        Caller is responsible for ordering.
        """
        query = (query or "").strip()
        if not query:
            return self

        return self.filter(
            self._build_text_and_requester_q(query) | self._build_update_q(query)
        ).distinct()


class PartRequest(TimeStampedMixin):
    """A request for a part needed for maintenance."""

    class Status(models.TextChoices):
        """Lifecycle state of a part request."""

        REQUESTED = "requested", "Requested"
        ORDERED = "ordered", "Ordered"
        RECEIVED = "received", "Received"
        CANCELLED = "cancelled", "Cancelled"

    text = models.TextField(
        help_text="Description of the part needed and why.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.REQUESTED,
        db_index=True,
    )
    requested_by = models.ForeignKey(
        Maintainer,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="part_requests",
        help_text="The maintainer who requested this part.",
    )
    requested_by_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Name when requester is not in the system.",
    )
    machine = models.ForeignKey(
        MachineInstance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="part_requests",
        help_text="Optional: the machine this part is for.",
    )
    occurred_at = models.DateTimeField(
        default=timezone.now,
        help_text="When the part was requested. Defaults to now if not specified.",
    )

    objects = PartRequestQuerySet.as_manager()
    history = HistoricalRecords()

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["occurred_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        preview = self.text[:50] + "..." if len(self.text) > 50 else self.text
        return f"Parts Request #{self.pk}: {preview}"

    @property
    def status_display_class(self) -> str:
        """Return CSS class for status badge styling."""
        return {
            self.Status.REQUESTED.value: "requested",
            self.Status.ORDERED.value: "ordered",
            self.Status.RECEIVED.value: "received",
            self.Status.CANCELLED.value: "cancelled",
        }.get(self.status, "")

    @property
    def requester_display(self) -> str:
        """Return display name for who requested the part."""
        if self.requested_by:
            return str(self.requested_by)
        return self.requested_by_name

    def get_admin_history_url(self) -> str:
        """Return URL to this part request's Django admin change history."""
        return reverse("admin:parts_partrequest_history", args=[self.pk])


def part_request_media_upload_to(instance: PartRequestMedia, filename: str) -> str:
    """Generate upload path for part request media."""
    return f"part_requests/{instance.part_request_id}/{uuid4()}-{filename}"


class PartRequestMedia(AbstractMedia):
    """Media files attached to a part request."""

    parent_field_name = "part_request"

    part_request = models.ForeignKey(
        PartRequest,
        on_delete=models.CASCADE,
        related_name="media",
    )
    file = models.FileField(upload_to=part_request_media_upload_to)
    thumbnail_file = models.FileField(upload_to=part_request_media_upload_to, blank=True, null=True)
    transcoded_file = models.FileField(
        upload_to=part_request_media_upload_to, blank=True, null=True
    )
    poster_file = models.ImageField(upload_to=part_request_media_upload_to, blank=True, null=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["display_order", "created_at"]
        verbose_name = "Part request media"
        verbose_name_plural = "Part request media"

    def __str__(self) -> str:
        return f"{self.get_media_type_display()} for part request {self.part_request_id}"

    def get_admin_history_url(self) -> str:
        """Return URL to this media's Django admin change history."""
        return reverse("admin:parts_partrequestmedia_history", args=[self.pk])


class PartRequestUpdateQuerySet(models.QuerySet):
    """Custom queryset for PartRequestUpdate model."""

    def _build_text_and_poster_q(self, query: str):
        """Build Q object for text and poster name search."""
        return (
            models.Q(text__icontains=query)
            | models.Q(posted_by__user__username__icontains=query)
            | models.Q(posted_by__user__first_name__icontains=query)
            | models.Q(posted_by__user__last_name__icontains=query)
            | models.Q(posted_by_name__icontains=query)
        )

    def _build_part_request_q(self, query: str):
        """Build Q object for searching linked part request fields.

        Matches part request text and requester name fields.
        """
        return (
            models.Q(part_request__text__icontains=query)
            | models.Q(part_request__requested_by__user__username__icontains=query)
            | models.Q(part_request__requested_by__user__first_name__icontains=query)
            | models.Q(part_request__requested_by__user__last_name__icontains=query)
            | models.Q(part_request__requested_by_name__icontains=query)
        )

    def search_for_machine(self, query: str = ""):
        """
        Machine-scoped search: text, poster name, and linked part request fields.

        When viewing a specific machine's part request updates, searches
        update text and poster names, plus linked part request text and
        requester names.

        Returns unfiltered queryset if query is empty/whitespace.
        Caller is responsible for ordering.
        """
        query = (query or "").strip()
        if not query:
            return self

        return self.filter(
            self._build_text_and_poster_q(query) | self._build_part_request_q(query)
        ).distinct()

    def search_for_part_request(self, query: str = ""):
        """
        Part-request-scoped search: only text and poster name.

        When viewing a specific part request's updates, the part request's
        own fields are redundant to search.

        Returns unfiltered queryset if query is empty/whitespace.
        Caller is responsible for ordering.
        """
        query = (query or "").strip()
        if not query:
            return self

        return self.filter(self._build_text_and_poster_q(query)).distinct()

    def search(self, query: str = ""):
        """
        Global search: text, poster name, part request fields, and machine name.

        Used in global activity feed where machine context is not implied.

        Returns unfiltered queryset if query is empty/whitespace.
        Caller is responsible for ordering.
        """
        query = (query or "").strip()
        if not query:
            return self

        machine_q = models.Q(part_request__machine__name__icontains=query) | models.Q(
            part_request__machine__short_name__icontains=query
        )

        return self.filter(
            self._build_text_and_poster_q(query) | self._build_part_request_q(query) | machine_q
        ).distinct()


class PartRequestUpdate(TimeStampedMixin):
    """An update or comment on a part request."""

    part_request = models.ForeignKey(
        PartRequest,
        on_delete=models.CASCADE,
        related_name="updates",
    )
    posted_by = models.ForeignKey(
        Maintainer,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="part_request_updates",
        help_text="The maintainer who posted this update.",
    )
    posted_by_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Name when poster is not in the system.",
    )
    text = models.TextField(
        help_text="Update text or comment.",
    )
    new_status = models.CharField(
        max_length=20,
        choices=PartRequest.Status.choices,
        blank=True,
        help_text="If set, this update changed the part request status.",
    )
    occurred_at = models.DateTimeField(
        default=timezone.now,
        help_text="When the update was posted. Defaults to now if not specified.",
    )

    objects = PartRequestUpdateQuerySet.as_manager()
    history = HistoricalRecords()

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["occurred_at"]),
        ]
        verbose_name = "Part request update"
        verbose_name_plural = "Part request updates"

    def __str__(self) -> str:
        return f"Update on part request {self.part_request_id} by {self.poster_display}"

    @property
    def poster_display(self) -> str:
        """Return display name for who posted the update."""
        if self.posted_by:
            return str(self.posted_by)
        return self.posted_by_name

    def get_admin_history_url(self) -> str:
        """Return URL to this update's Django admin change history."""
        return reverse("admin:parts_partrequestupdate_history", args=[self.pk])

    def save(self, *args, **kwargs):
        # If new_status is set, also update the parent part request status.
        # Wrap in transaction so both saves succeed or both roll back.
        with transaction.atomic():
            if self.new_status and self.part_request.status != self.new_status:
                self.part_request.status = self.new_status
                self.part_request.save(update_fields=["status", "updated_at"])
            super().save(*args, **kwargs)


def part_request_update_media_upload_to(instance: PartRequestUpdateMedia, filename: str) -> str:
    """Generate upload path for part request update media."""
    return f"part_request_updates/{instance.update_id}/{uuid4()}-{filename}"


class PartRequestUpdateMedia(AbstractMedia):
    """Media files attached to a part request update."""

    parent_field_name = "update"

    update = models.ForeignKey(
        PartRequestUpdate,
        on_delete=models.CASCADE,
        related_name="media",
    )
    file = models.FileField(upload_to=part_request_update_media_upload_to)
    thumbnail_file = models.FileField(
        upload_to=part_request_update_media_upload_to, blank=True, null=True
    )
    transcoded_file = models.FileField(
        upload_to=part_request_update_media_upload_to, blank=True, null=True
    )
    poster_file = models.ImageField(
        upload_to=part_request_update_media_upload_to, blank=True, null=True
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["display_order", "created_at"]
        verbose_name = "Part request update media"
        verbose_name_plural = "Part request update media"

    def __str__(self) -> str:
        return f"{self.get_media_type_display()} for update {self.update_id}"

    def get_admin_history_url(self) -> str:
        """Return URL to this media's Django admin change history."""
        return reverse("admin:parts_partrequestupdatemedia_history", args=[self.pk])
