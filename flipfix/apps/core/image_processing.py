"""Image processing utilities for uploaded files.

Provides resizing and format conversion for uploaded images, including:
- HEIC/HEIF to JPEG conversion for browser compatibility
- Preservation of web-native formats (JPEG, PNG, WebP, AVIF)
- Downscaling large images to reasonable web dimensions
- EXIF orientation correction
- Thumbnail generation

This module intentionally avoids importing Django models to keep it
focused purely on image transformation logic.
"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.core.files.uploadedfile import InMemoryUploadedFile
from PIL import Image, ImageOps, UnidentifiedImageError

from flipfix.apps.core.media import BROWSER_QUIRK_EXTENSIONS, WEB_NATIVE_FORMATS

if TYPE_CHECKING:
    from django.core.files.uploadedfile import UploadedFile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Image dimension constants
# ---------------------------------------------------------------------------
MAX_IMAGE_DIMENSION = 2400
"""Maximum dimension (width or height) for full-size images."""

THUMB_IMAGE_DIMENSION = 800
"""Maximum dimension (width or height) for thumbnail images."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _with_extension(name: str, ext: str) -> str:
    """Return filename with a new extension."""
    return str(Path(name).with_suffix(f".{ext}"))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resize_image_file(
    uploaded_file: UploadedFile,
    max_dimension: int | None = MAX_IMAGE_DIMENSION,
) -> UploadedFile:
    """
    Resize the image so its longest side is max_dimension.

    Web-native formats (see ``WEB_NATIVE_FORMATS`` in ``media.py``) are
    preserved.  Non-native formats (e.g. HEIC/HEIF, BMP) are converted to
    JPEG.  Returns the original file if it is not an image or cannot be
    identified.

    Args:
        uploaded_file: The uploaded file to process.
        max_dimension: Maximum width/height. Pass None to skip resizing
            but still perform format conversion if needed.

    Returns:
        The processed file (may be the original if no processing needed).
    """
    content_type = (getattr(uploaded_file, "content_type", "") or "").lower()
    ext = Path(getattr(uploaded_file, "name", "")).suffix.lower()
    if (
        content_type
        and not content_type.startswith("image/")
        and ext not in BROWSER_QUIRK_EXTENSIONS
    ):
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

    # Capture format before transpose (exif_transpose returns a copy that loses format attr)
    original_format = (image.format or "").upper()

    transposed = ImageOps.exif_transpose(image)
    needs_transpose = transposed is not None and transposed is not image
    if transposed is None:
        transposed = image
    image = transposed
    is_heif = original_format in {"HEIC", "HEIF"}
    needs_resize = max_dimension is not None and max(image.size) > max_dimension
    needs_format_conversion = is_heif or original_format not in WEB_NATIVE_FORMATS

    # Skip re-encoding if no transformation needed
    if not needs_resize and not needs_format_conversion and not needs_transpose:
        try:
            uploaded_file.seek(0)
        except (OSError, AttributeError):
            pass
        return uploaded_file

    # Determine output format: preserve web-native formats, convert others to JPEG.
    # Special case: PNG with transparency stays PNG regardless.
    if original_format == "PNG" and image.mode in {"RGBA", "LA"}:
        target_format = "PNG"
    elif original_format in WEB_NATIVE_FORMATS:
        target_format = original_format
    else:
        target_format = "JPEG"

    fmt_info = WEB_NATIVE_FORMATS[target_format]
    content_type_out = fmt_info.content_type
    filename = _with_extension(uploaded_file.name or "upload", fmt_info.extension)

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
    save_kwargs: dict[str, Any] = {"format": target_format}
    if fmt_info.quality is not None:
        save_kwargs["quality"] = fmt_info.quality
    if fmt_info.optimize:
        save_kwargs["optimize"] = True
    image.save(buffer, **save_kwargs)
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
