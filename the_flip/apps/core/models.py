from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

from django.core.files.uploadedfile import InMemoryUploadedFile, UploadedFile
from django.db import models
from PIL import Image, ImageOps, UnidentifiedImageError

if TYPE_CHECKING:
    from typing import ClassVar

logger = logging.getLogger(__name__)

# Image dimension constants
MAX_IMAGE_DIMENSION = 2400
THUMB_IMAGE_DIMENSION = 800


class TimeStampedMixin(models.Model):
    """Mixin providing created_at and updated_at timestamp fields."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# Image processing utilities
# ---------------------------------------------------------------------------


def _with_extension(name: str, ext: str) -> str:
    """Return filename with a new extension."""
    return str(Path(name).with_suffix(f".{ext}"))


def resize_image_file(
    uploaded_file: UploadedFile,
    max_dimension: int | None = MAX_IMAGE_DIMENSION,
) -> UploadedFile:
    """
    Resize the image so its longest side is max_dimension.

    Converts HEIC/HEIF to JPEG for browser compatibility. Returns the original
    file if it is not an image or cannot be identified.
    """
    content_type = (getattr(uploaded_file, "content_type", "") or "").lower()
    ext = Path(getattr(uploaded_file, "name", "")).suffix.lower()
    if content_type and not content_type.startswith("image/") and ext not in {".heic", ".heif"}:
        logger.debug(
            "resize_image_file: skipping non-image content_type=%s name=%s",
            content_type,
            uploaded_file,
        )
        return uploaded_file

    # Always seek to start in case the file has been read already.
    try:
        uploaded_file.seek(0)
    except Exception:  # noqa: S110 - seek failure is benign
        pass

    try:
        image: Image.Image = Image.open(uploaded_file)  # type: ignore[assignment]
    except UnidentifiedImageError:
        try:
            uploaded_file.seek(0)
        except Exception:  # noqa: S110 - seek failure is benign
            pass
        logger.debug(
            "resize_image_file: not an image or unreadable (%s)", getattr(uploaded_file, "name", "")
        )
        return uploaded_file

    transposed = ImageOps.exif_transpose(image)
    needs_transpose = transposed is not None and transposed is not image
    if transposed is None:
        transposed = image
    image = transposed
    original_format = (image.format or "").upper()
    is_heif = original_format in {"HEIC", "HEIF"}
    needs_resize = max_dimension is not None and max(image.size) > max_dimension
    needs_format_conversion = is_heif or original_format not in {"JPEG", "PNG"}

    # Skip re-encoding if no transformation needed
    if not needs_resize and not needs_format_conversion and not needs_transpose:
        try:
            uploaded_file.seek(0)
        except (OSError, AttributeError):
            pass
        return uploaded_file

    target_format = "PNG" if original_format == "PNG" and image.mode in {"RGBA", "LA"} else "JPEG"
    content_type_out = "image/png" if target_format == "PNG" else "image/jpeg"
    filename = _with_extension(
        uploaded_file.name or "upload", "png" if target_format == "PNG" else "jpg"
    )

    if target_format == "JPEG" and image.mode not in {"RGB", "L"}:
        image = image.convert("RGB")

    if needs_resize and max_dimension:
        image = ImageOps.contain(image, (max_dimension, max_dimension), Image.Resampling.LANCZOS)

    logger.debug(
        "resize_image_file: name=%s format=%s heif=%s resized=%s size=%s target_format=%s",
        getattr(uploaded_file, "name", ""),
        original_format,
        is_heif,
        needs_resize,
        image.size,
        target_format,
    )

    buffer = BytesIO()
    if target_format == "JPEG":
        image.save(buffer, format=target_format, quality=85, optimize=True)
    else:
        image.save(buffer, format=target_format, optimize=True)
    size = buffer.tell()
    buffer.seek(0)

    return InMemoryUploadedFile(
        buffer,
        getattr(uploaded_file, "field_name", None),
        filename,
        content_type_out,
        size,
        None,
    )


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

    # Media type constants
    TYPE_PHOTO = "photo"
    TYPE_VIDEO = "video"
    MEDIA_CHOICES = [
        (TYPE_PHOTO, "Photo"),
        (TYPE_VIDEO, "Video"),
    ]

    # Transcode status constants
    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_READY = "ready"
    STATUS_FAILED = "failed"
    TRANSCODE_STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_READY, "Ready"),
        (STATUS_FAILED, "Failed"),
    ]

    media_type = models.CharField(max_length=20, choices=MEDIA_CHOICES)
    file = models.FileField()  # upload_to set by subclass
    thumbnail_file = models.FileField(blank=True)
    transcoded_file = models.FileField(blank=True, null=True)
    poster_file = models.ImageField(blank=True, null=True)
    transcode_status = models.CharField(
        max_length=20,
        choices=TRANSCODE_STATUS_CHOICES,
        blank=True,
        default=STATUS_PENDING,
    )
    duration = models.IntegerField(null=True, blank=True, help_text="Duration in seconds")
    display_order = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        abstract = True
        ordering = ["display_order", "created_at"]

    def save(self, *args, **kwargs):
        """Process photo uploads: generate thumbnail and resize for web."""
        if self.media_type == self.TYPE_PHOTO and self.file:
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
