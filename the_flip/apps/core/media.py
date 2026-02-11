"""Media type configuration and utilities.

Single source of truth for supported media extensions used by:
- Web form validation (uploads)
- Discord bot media filtering
- Video detection for transcoding
- Media attachment on form create views and AJAX uploads
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import partial
from pathlib import Path
from typing import Any

from django.core.files.uploadedfile import UploadedFile
from django.db import transaction

from the_flip.apps.core.tasks import enqueue_transcode

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


def attach_media_files(
    *,
    media_files: Sequence[UploadedFile],
    parent: object,
    media_model: type[Any],
) -> list[Any]:
    """Create media records for uploaded files and enqueue video transcoding.

    ``media_model`` must be a concrete ``AbstractMedia`` subclass
    (e.g. ``LogEntryMedia``).  The type is ``Any`` because django-stubs
    does not expose ``.objects`` on abstract model types.

    Must be called inside a transaction (e.g. a view decorated with
    ``@transaction.atomic``) so that ``on_commit`` callbacks fire correctly.
    """
    created: list[Any] = []
    for media_file in media_files:
        is_video = is_video_file(media_file)

        media = media_model.objects.create(
            **{media_model.parent_field_name: parent},
            media_type=media_model.MediaType.VIDEO if is_video else media_model.MediaType.PHOTO,
            file=media_file,
            transcode_status=media_model.TranscodeStatus.PENDING if is_video else "",
        )

        if is_video:
            transaction.on_commit(
                partial(enqueue_transcode, media_id=media.id, model_name=media_model.__name__)
            )

        created.append(media)
    return created
