from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q

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


class SearchableQuerySetMixin:
    """Mixin that DRYs up the strip → empty-guard → filter → distinct pattern.

    Every search method in the project follows the same boilerplate::

        query = (query or "").strip()
        if not query:
            return self
        return self.filter(...).distinct()

    This mixin extracts that into two helpers so each search method
    only contains the domain-specific Q logic::

        def search(self, query: str = ""):
            query = self._clean_query(query)
            return self._apply_search(
                query,
                self._build_core_q(query) | Q(machine__name__icontains=query),
            )
    """

    @staticmethod
    def _clean_query(query: str) -> str:
        """Normalize a search query: coerce None and strip whitespace."""
        return (query or "").strip()

    def _apply_search(self, query: str, q: Q) -> models.QuerySet:
        """Apply standard search normalization and filtering.

        Returns self unchanged for empty/blank queries. Otherwise
        filters by *q* and returns distinct results.

        Callers must pass the already-cleaned query (via ``_clean_query``)
        so that the Q objects use the stripped value.
        """
        if not query:
            return self  # type: ignore[return-value]
        return self.filter(q).distinct()  # type: ignore[attr-defined]


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
#
# Apps register their AbstractMedia subclasses via AppConfig.ready(), keeping
# core free of hardcoded knowledge about other apps.  Compare the same pattern
# in core/markdown_links.py for link-type registration.
# ---------------------------------------------------------------------------

_MEDIA_MODEL_REGISTRY: dict[str, type[AbstractMedia]] = {}


def register_media_model(model_class: type[AbstractMedia]) -> None:
    """Register a media model. Called from each app's AppConfig.ready()."""
    name = model_class.__name__
    if name in _MEDIA_MODEL_REGISTRY:
        raise ValueError(f"Media model '{name}' is already registered")
    _MEDIA_MODEL_REGISTRY[name] = model_class


def clear_media_model_registry() -> None:
    """Reset registry state. For tests only."""
    _MEDIA_MODEL_REGISTRY.clear()


def get_media_model(model_name: str) -> Any:
    """Get a concrete media model class by name.

    Returns a concrete AbstractMedia subclass. Typed as ``Any`` because
    django-stubs removes the manager from abstract models, yet callers
    need ``.objects`` and ``.DoesNotExist`` on the returned class.
    """
    try:
        return _MEDIA_MODEL_REGISTRY[model_name]
    except KeyError:
        raise ValueError(f"Unknown media model: {model_name}") from None


# ---------------------------------------------------------------------------
# Generic link tracking
# ---------------------------------------------------------------------------


class RecordReference(models.Model):
    """Tracks links between records for 'what links here' queries.

    Uses Django's contenttypes framework for polymorphic source/target.
    GenericForeignKey doesn't support on_delete, so all target deletions
    are allowed. Broken links render as 'broken link' text. For wiki
    pages, the delete confirmation warns which pages will have broken links.
    """

    # Source (the record containing the link)
    source_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name="+")
    source_id = models.PositiveBigIntegerField()
    source = GenericForeignKey("source_type", "source_id")

    # Target (the record being linked to)
    target_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name="+")
    target_id = models.PositiveBigIntegerField()
    target = GenericForeignKey("target_type", "target_id")

    class Meta:
        unique_together = [["source_type", "source_id", "target_type", "target_id"]]
        indexes = [
            models.Index(fields=["target_type", "target_id"]),  # "What links here"
            models.Index(fields=["source_type", "source_id"]),  # Cleanup on delete
        ]

    def __str__(self):
        return (
            f"{self.source_type.model}:{self.source_id} → {self.target_type.model}:{self.target_id}"
        )


def register_reference_cleanup(*model_classes: type[models.Model]) -> None:
    """Connect post_delete signals to clean up RecordReference rows for the given models.

    Call from AppConfig.ready() for every model whose text fields can contain
    ``[[type:ref]]`` markdown links (i.e. any model passed to ``sync_references``).

    Example::

        from the_flip.apps.core.models import register_reference_cleanup
        from .models import ProblemReport, LogEntry

        class MaintenanceConfig(AppConfig):
            def ready(self):
                register_reference_cleanup(ProblemReport, LogEntry)
    """
    from django.db.models.signals import post_delete

    def _cleanup_references(sender, instance, **kwargs):
        ct = ContentType.objects.get_for_model(sender)
        RecordReference.objects.filter(source_type=ct, source_id=instance.pk).delete()

    for model_class in model_classes:
        post_delete.connect(_cleanup_references, sender=model_class)
