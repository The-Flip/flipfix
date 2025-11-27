"""Utilities for handling maintenance media uploads."""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

from django.core.files.uploadedfile import InMemoryUploadedFile, UploadedFile
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_IMAGE_DIMENSION = 2400
THUMB_IMAGE_DIMENSION = 800
logger = logging.getLogger(__name__)


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
    except Exception:
        pass

    try:
        image: Image.Image = Image.open(uploaded_file)  # type: ignore[assignment]
    except UnidentifiedImageError:
        try:
            uploaded_file.seek(0)
        except Exception:
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
