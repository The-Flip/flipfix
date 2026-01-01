from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import models

from the_flip.apps.core.image_processing import (
    THUMB_IMAGE_DIMENSION,
    resize_image_file,
)

if TYPE_CHECKING:
    from typing import ClassVar

logger = logging.getLogger(__name__)


class TimeStampedMixin(models.Model):
    """Mixin providing created_at and updated_at timestamp fields."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# Abstract media model
# ---------------------------------------------------------------------------


class AbstractMedia(TimeStampedMixin):
    """
    Abstract base class for media attachments (photos and videos).

    Subclasses must:
    1. Define a ForeignKey to their parent model with related_name="media"
    2. Set the `parent_field_name` class attribute (e.g., "log_entry", "part_request")
    3. Provide an `upload_to` callable for file fields
    4. Include `history = HistoricalRecords()` for audit trail
    """

    # Subclasses must define this to indicate which FK field points to the parent
    parent_field_name: ClassVar[str]

    class MediaType(models.TextChoices):
        """Type of media attachment."""

        PHOTO = "photo", "Photo"
        VIDEO = "video", "Video"

    class TranscodeStatus(models.TextChoices):
        """Status of video transcoding for web playback."""

        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    media_type = models.CharField(max_length=20, choices=MediaType.choices)
    file = models.FileField()  # upload_to set by subclass
    thumbnail_file = models.FileField(blank=True, null=True)
    transcoded_file = models.FileField(blank=True, null=True)
    poster_file = models.ImageField(blank=True, null=True)
    transcode_status = models.CharField(
        max_length=20,
        choices=TranscodeStatus.choices,
        blank=True,
        default=TranscodeStatus.PENDING,
    )
    duration = models.IntegerField(null=True, blank=True, help_text="Duration in seconds")
    display_order = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        abstract = True
        ordering = ["display_order", "created_at"]

    def save(self, *args, **kwargs):
        """Process photo uploads: generate thumbnail and resize for web."""
        if self.media_type == self.MediaType.PHOTO and self.file:
            from django.core.files.uploadedfile import UploadedFile as DjangoUploadedFile

            is_fresh_upload = hasattr(self.file, "file") and isinstance(
                self.file.file, DjangoUploadedFile
            )
            if is_fresh_upload:
                try:
                    original = self.file
                    # Generate thumbnail from original (before any JPEG compression)
                    if not self.thumbnail_file:
                        self.thumbnail_file = resize_image_file(
                            original, max_dimension=THUMB_IMAGE_DIMENSION
                        )
                        # Seek back to start for the next resize
                        try:
                            original.seek(0)
                        except (OSError, AttributeError):
                            pass  # File doesn't support seeking, proceed anyway
                    # Convert to browser-friendly format and size
                    self.file = resize_image_file(original)
                except Exception:  # pragma: no cover
                    logger.warning("Could not resize uploaded photo %s", self.file, exc_info=True)
        super().save(*args, **kwargs)

    def get_parent(self):
        """Return the parent object this media is attached to."""
        return getattr(self, self.parent_field_name)


# ---------------------------------------------------------------------------
# Media model registry
# ---------------------------------------------------------------------------

# Maps model names to import paths for lazy loading. Add new media models here.
_MEDIA_MODEL_REGISTRY: dict[str, str] = {
    "LogEntryMedia": "the_flip.apps.maintenance.models.LogEntryMedia",
    "ProblemReportMedia": "the_flip.apps.maintenance.models.ProblemReportMedia",
    "PartRequestMedia": "the_flip.apps.parts.models.PartRequestMedia",
    "PartRequestUpdateMedia": "the_flip.apps.parts.models.PartRequestUpdateMedia",
}


def get_media_model(model_name: str):
    """
    Get a media model class by name.

    Used by the transcode worker and upload receiver to handle multiple media types.
    """
    if model_name not in _MEDIA_MODEL_REGISTRY:
        raise ValueError(f"Unknown media model: {model_name}")

    import_path = _MEDIA_MODEL_REGISTRY[model_name]
    module_path, class_name = import_path.rsplit(".", 1)

    from importlib import import_module

    module = import_module(module_path)
    return getattr(module, class_name)
