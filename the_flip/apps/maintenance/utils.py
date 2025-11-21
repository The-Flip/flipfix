"""Utilities for handling maintenance media uploads."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Optional

import logging
from django.core.files.uploadedfile import InMemoryUploadedFile, UploadedFile
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_IMAGE_DIMENSION = 2400
logger = logging.getLogger(__name__)


def _with_extension(name: str, ext: str) -> str:
    """Return filename with a new extension."""
    return str(Path(name).with_suffix(f".{ext}"))


def resize_image_file(
    uploaded_file: UploadedFile,
    max_dimension: int = MAX_IMAGE_DIMENSION,
) -> UploadedFile:
    """
    Resize the image so its longest side is max_dimension.

    Converts HEIC/HEIF to JPEG for browser compatibility. Returns the original
    file if it is not an image or cannot be identified.
    """
    content_type = (getattr(uploaded_file, "content_type", "") or "").lower()
    ext = Path(getattr(uploaded_file, "name", "")).suffix.lower()
    if content_type and not content_type.startswith("image/") and ext not in {".heic", ".heif"}:
        logger.warning("resize_image_file: skipping non-image content_type=%s name=%s", content_type, uploaded_file)
        return uploaded_file

    # Always seek to start in case the file has been read already.
    try:
        uploaded_file.seek(0)
    except Exception:
        pass

    try:
        image = Image.open(uploaded_file)
    except UnidentifiedImageError:
        try:
            uploaded_file.seek(0)
        except Exception:
            pass
        logger.warning("resize_image_file: not an image or unreadable (%s)", getattr(uploaded_file, "name", ""))
        return uploaded_file

    image = ImageOps.exif_transpose(image)
    original_format = (image.format or "").upper()
    is_heif = original_format in {"HEIC", "HEIF"}
    needs_resize = max(image.size) > max_dimension

    if not needs_resize and not is_heif:
        try:
            uploaded_file.seek(0)
        except Exception:
            pass
        return uploaded_file

    target_format = "PNG" if original_format == "PNG" and image.mode in {"RGBA", "LA"} else "JPEG"
    content_type_out = "image/png" if target_format == "PNG" else "image/jpeg"
    filename = _with_extension(uploaded_file.name or "upload", "png" if target_format == "PNG" else "jpg")

    if target_format == "JPEG" and image.mode not in {"RGB", "L"}:
        image = image.convert("RGB")

    if needs_resize:
        image = ImageOps.contain(image, (max_dimension, max_dimension), Image.LANCZOS)

    logger.warning(
        "resize_image_file: name=%s format=%s heif=%s resized=%s size=%s target_format=%s",
        getattr(uploaded_file, "name", ""),
        original_format,
        is_heif,
        needs_resize,
        image.size,
        target_format,
    )

    buffer = BytesIO()
    save_kwargs = {"format": target_format}
    if target_format == "JPEG":
        save_kwargs.update({"quality": 85, "optimize": True})
    else:
        save_kwargs.update({"optimize": True})

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
