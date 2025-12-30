"""Media type configuration and utilities.

Single source of truth for supported media extensions used by:
- Web form validation (uploads)
- Discord bot media filtering
- Video detection for transcoding
"""

from pathlib import Path

from django.core.files.uploadedfile import UploadedFile

# Supported media extensions
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".hevc"}
ALLOWED_HEIC_EXTENSIONS = {".heic", ".heif"}
ALLOWED_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"} | ALLOWED_HEIC_EXTENSIONS
ALLOWED_MEDIA_EXTENSIONS = ALLOWED_PHOTO_EXTENSIONS | ALLOWED_VIDEO_EXTENSIONS

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
