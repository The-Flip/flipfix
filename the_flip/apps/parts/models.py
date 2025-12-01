"""Parts management models."""

from __future__ import annotations

from uuid import uuid4

from django.db import models

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.core.models import TimeStampedModel
from the_flip.apps.maintenance.utils import THUMB_IMAGE_DIMENSION, resize_image_file


class PartRequestQuerySet(models.QuerySet):
    """Custom queryset for PartRequest model."""

    def active(self):
        """Return part requests that are not cancelled."""
        return self.exclude(status=PartRequest.STATUS_CANCELLED)

    def pending(self):
        """Return part requests that are requested or ordered (not yet received)."""
        return self.filter(status__in=[PartRequest.STATUS_REQUESTED, PartRequest.STATUS_ORDERED])


class PartRequest(TimeStampedModel):
    """A request for a part needed for maintenance."""

    STATUS_REQUESTED = "requested"
    STATUS_ORDERED = "ordered"
    STATUS_RECEIVED = "received"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_REQUESTED, "Requested"),
        (STATUS_ORDERED, "Ordered"),
        (STATUS_RECEIVED, "Received"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    text = models.TextField(
        help_text="Description of the part needed and why.",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_REQUESTED,
        db_index=True,
    )
    requested_by = models.ForeignKey(
        Maintainer,
        on_delete=models.PROTECT,
        related_name="part_requests",
        help_text="The maintainer who requested this part.",
    )
    machine = models.ForeignKey(
        MachineInstance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="part_requests",
        help_text="Optional: the machine this part is for.",
    )

    objects = PartRequestQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        preview = self.text[:50] + "..." if len(self.text) > 50 else self.text
        return f"Part Request #{self.pk}: {preview}"

    @property
    def status_display_class(self) -> str:
        """Return CSS class for status badge styling."""
        return {
            self.STATUS_REQUESTED: "requested",
            self.STATUS_ORDERED: "ordered",
            self.STATUS_RECEIVED: "received",
            self.STATUS_CANCELLED: "cancelled",
        }.get(self.status, "")


def part_request_media_upload_to(instance: PartRequestMedia, filename: str) -> str:
    """Generate upload path for part request media."""
    return f"part_requests/{instance.part_request_id}/{uuid4()}-{filename}"


class PartRequestMedia(TimeStampedModel):
    """Media files attached to a part request."""

    TYPE_PHOTO = "photo"
    TYPE_VIDEO = "video"
    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_READY = "ready"
    STATUS_FAILED = "failed"
    MEDIA_CHOICES = [
        (TYPE_PHOTO, "Photo"),
        (TYPE_VIDEO, "Video"),
    ]
    TRANSCODE_STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_READY, "Ready"),
        (STATUS_FAILED, "Failed"),
    ]

    part_request = models.ForeignKey(
        PartRequest,
        on_delete=models.CASCADE,
        related_name="media",
    )
    media_type = models.CharField(max_length=20, choices=MEDIA_CHOICES)
    file = models.FileField(upload_to=part_request_media_upload_to)
    thumbnail_file = models.FileField(upload_to=part_request_media_upload_to, blank=True)
    transcoded_file = models.FileField(
        upload_to=part_request_media_upload_to, blank=True, null=True
    )
    poster_file = models.ImageField(upload_to=part_request_media_upload_to, blank=True, null=True)
    transcode_status = models.CharField(
        max_length=20,
        choices=TRANSCODE_STATUS_CHOICES,
        blank=True,
        default=STATUS_PENDING,
    )
    duration = models.IntegerField(null=True, blank=True, help_text="Duration in seconds")
    display_order = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["display_order", "created_at"]
        verbose_name = "Part request media"
        verbose_name_plural = "Part request media"

    def __str__(self) -> str:
        return f"{self.get_media_type_display()} for part request {self.part_request_id}"

    def save(self, *args, **kwargs):
        if self.media_type == self.TYPE_PHOTO and self.file:
            from django.core.files.uploadedfile import UploadedFile

            is_fresh_upload = hasattr(self.file, "file") and isinstance(
                self.file.file, UploadedFile
            )
            if is_fresh_upload:
                try:
                    original = self.file
                    if not self.thumbnail_file:
                        self.thumbnail_file = resize_image_file(
                            original, max_dimension=THUMB_IMAGE_DIMENSION
                        )
                        try:
                            original.seek(0)
                        except (OSError, AttributeError):
                            pass
                    self.file = resize_image_file(original)
                except Exception:
                    import logging

                    logging.getLogger(__name__).warning(
                        "Could not resize uploaded photo %s", self.file, exc_info=True
                    )
        super().save(*args, **kwargs)


class PartRequestUpdate(TimeStampedModel):
    """An update or comment on a part request."""

    part_request = models.ForeignKey(
        PartRequest,
        on_delete=models.CASCADE,
        related_name="updates",
    )
    posted_by = models.ForeignKey(
        Maintainer,
        on_delete=models.PROTECT,
        related_name="part_request_updates",
        help_text="The maintainer who posted this update.",
    )
    text = models.TextField(
        help_text="Update text or comment.",
    )
    new_status = models.CharField(
        max_length=20,
        choices=PartRequest.STATUS_CHOICES,
        blank=True,
        help_text="If set, this update changed the part request status.",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Part request update"
        verbose_name_plural = "Part request updates"

    def __str__(self) -> str:
        return f"Update on part request {self.part_request_id} by {self.posted_by}"

    def save(self, *args, **kwargs):
        # If new_status is set, also update the parent part request status
        if self.new_status and self.part_request.status != self.new_status:
            self.part_request.status = self.new_status
            self.part_request.save(update_fields=["status", "updated_at"])
        super().save(*args, **kwargs)


def part_request_update_media_upload_to(instance: PartRequestUpdateMedia, filename: str) -> str:
    """Generate upload path for part request update media."""
    return f"part_request_updates/{instance.update_id}/{uuid4()}-{filename}"


class PartRequestUpdateMedia(TimeStampedModel):
    """Media files attached to a part request update."""

    TYPE_PHOTO = "photo"
    TYPE_VIDEO = "video"
    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_READY = "ready"
    STATUS_FAILED = "failed"
    MEDIA_CHOICES = [
        (TYPE_PHOTO, "Photo"),
        (TYPE_VIDEO, "Video"),
    ]
    TRANSCODE_STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_READY, "Ready"),
        (STATUS_FAILED, "Failed"),
    ]

    update = models.ForeignKey(
        PartRequestUpdate,
        on_delete=models.CASCADE,
        related_name="media",
    )
    media_type = models.CharField(max_length=20, choices=MEDIA_CHOICES)
    file = models.FileField(upload_to=part_request_update_media_upload_to)
    thumbnail_file = models.FileField(upload_to=part_request_update_media_upload_to, blank=True)
    transcoded_file = models.FileField(
        upload_to=part_request_update_media_upload_to, blank=True, null=True
    )
    poster_file = models.ImageField(
        upload_to=part_request_update_media_upload_to, blank=True, null=True
    )
    transcode_status = models.CharField(
        max_length=20,
        choices=TRANSCODE_STATUS_CHOICES,
        blank=True,
        default=STATUS_PENDING,
    )
    duration = models.IntegerField(null=True, blank=True, help_text="Duration in seconds")
    display_order = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["display_order", "created_at"]
        verbose_name = "Part request update media"
        verbose_name_plural = "Part request update media"

    def __str__(self) -> str:
        return f"{self.get_media_type_display()} for update {self.update_id}"

    def save(self, *args, **kwargs):
        if self.media_type == self.TYPE_PHOTO and self.file:
            from django.core.files.uploadedfile import UploadedFile

            is_fresh_upload = hasattr(self.file, "file") and isinstance(
                self.file.file, UploadedFile
            )
            if is_fresh_upload:
                try:
                    original = self.file
                    if not self.thumbnail_file:
                        self.thumbnail_file = resize_image_file(
                            original, max_dimension=THUMB_IMAGE_DIMENSION
                        )
                        try:
                            original.seek(0)
                        except (OSError, AttributeError):
                            pass
                    self.file = resize_image_file(original)
                except Exception:
                    import logging

                    logging.getLogger(__name__).warning(
                        "Could not resize uploaded photo %s", self.file, exc_info=True
                    )
        super().save(*args, **kwargs)
