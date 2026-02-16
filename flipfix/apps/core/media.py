"""Media type configuration and utilities.

Single source of truth for supported media extensions used by:
- Web form validation (uploads)
- Discord bot media filtering
- Video detection for transcoding
- Image processing format decisions
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from django.core.files.uploadedfile import UploadedFile


@dataclass(frozen=True)
class ImageFormat:
    """Configuration for a web-native image format."""

    content_type: str
    extension: str
    quality: int | None = None  # Lossy formats only; None = lossless
    optimize: bool = False  # Pillow optimize flag (JPEG/PNG only)


# Image formats browsers can display natively.  These are preserved on resize, not converted to JPEG.
# Keyed by Pillow's image.format string (always uppercase).
WEB_NATIVE_FORMATS: dict[str, ImageFormat] = {
    "JPEG": ImageFormat(content_type="image/jpeg", extension="jpg", quality=85, optimize=True),
    "PNG": ImageFormat(content_type="image/png", extension="png", optimize=True),
    "WEBP": ImageFormat(content_type="image/webp", extension="webp", quality=80),
    "AVIF": ImageFormat(content_type="image/avif", extension="avif", quality=63),
}

# Supported media extensions
ALLOWED_HEIC_EXTENSIONS = {".heic", ".heif"}
ALLOWED_AVIF_EXTENSIONS = {".avif"}
ALLOWED_PHOTO_EXTENSIONS = (
    {".jpg", ".jpeg", ".png", ".gif", ".webp"} | ALLOWED_HEIC_EXTENSIONS | ALLOWED_AVIF_EXTENSIONS
)
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".hevc"}
ALLOWED_MEDIA_EXTENSIONS = ALLOWED_PHOTO_EXTENSIONS | ALLOWED_VIDEO_EXTENSIONS

# Extensions where browsers may not map to image/* in the file picker.
# These get explicit entries in the HTML accept attribute alongside image/*.
BROWSER_QUIRK_EXTENSIONS = ALLOWED_HEIC_EXTENSIONS | ALLOWED_AVIF_EXTENSIONS

# Generated accept string for file inputs — single source of truth.
MEDIA_ACCEPT_ATTR = ",".join(
    [
        "image/*",
        "video/*",
        *sorted(f".{ext.lstrip('.')}" for ext in BROWSER_QUIRK_EXTENSIONS),
        *sorted(f"image/{ext.lstrip('.')}" for ext in BROWSER_QUIRK_EXTENSIONS),
    ]
)

# File size limit
MAX_MEDIA_FILE_SIZE_BYTES = 200 * 1024 * 1024  # 200MB


def is_video_file(uploaded_file: UploadedFile) -> bool:
    """Check if an uploaded file is a video based on content type and extension.

    Args:
        uploaded_file: The uploaded file to check.

    Returns:
        True if the file is a video, False otherwise.
    """
    content_type = (getattr(uploaded_file, "content_type", "") or "").lower()
    ext = Path(getattr(uploaded_file, "name", "")).suffix.lower()
    return content_type.startswith("video/") or ext in ALLOWED_VIDEO_EXTENSIONS
