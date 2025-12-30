"""Media download and creation for Discord bot.

Downloads Discord attachments and creates media records for Flipfix records.
Uses discord.py's attachment.read() for auth-handled downloads from Discord CDN.
"""

from __future__ import annotations

import logging
from functools import partial
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db import transaction

from the_flip.apps.core.media import ALLOWED_VIDEO_EXTENSIONS
from the_flip.apps.core.models import AbstractMedia
from the_flip.apps.core.tasks import enqueue_transcode
from the_flip.apps.maintenance.models import (
    LogEntry,
    LogEntryMedia,
    ProblemReport,
    ProblemReportMedia,
)
from the_flip.apps.parts.models import (
    PartRequest,
    PartRequestMedia,
    PartRequestUpdate,
    PartRequestUpdateMedia,
)

if TYPE_CHECKING:
    import discord

logger = logging.getLogger(__name__)

# Type alias for media model classes that can be created from Discord attachments
MediaModelClass = type[
    LogEntryMedia | ProblemReportMedia | PartRequestMedia | PartRequestUpdateMedia
]


def _is_video(filename: str) -> bool:
    """Check if filename has a video extension."""
    return Path(filename).suffix.lower() in ALLOWED_VIDEO_EXTENSIONS


def _dedupe_by_url(attachments: list[discord.Attachment]) -> list[discord.Attachment]:
    """Deduplicate attachments by URL.

    If same attachment appears in multiple source messages, only download once.
    """
    seen_urls: set[str] = set()
    unique: list[discord.Attachment] = []
    for a in attachments:
        if a.url not in seen_urls:
            seen_urls.add(a.url)
            unique.append(a)
    return unique


def _get_media_class_and_parent_field(
    record: LogEntry | ProblemReport | PartRequest | PartRequestUpdate,
) -> tuple[type, str, str]:
    """Get the media model class, parent field name, and model name for a record.

    Returns:
        Tuple of (MediaClass, parent_field_name, model_name_for_transcode)
    """
    if isinstance(record, LogEntry):
        return LogEntryMedia, "log_entry", "LogEntryMedia"
    elif isinstance(record, ProblemReport):
        return ProblemReportMedia, "problem_report", "ProblemReportMedia"
    elif isinstance(record, PartRequest):
        return PartRequestMedia, "part_request", "PartRequestMedia"
    elif isinstance(record, PartRequestUpdate):
        return PartRequestUpdateMedia, "update", "PartRequestUpdateMedia"
    else:
        raise ValueError(f"Unknown record type: {type(record)}")


async def download_and_create_media(
    record: LogEntry | ProblemReport | PartRequest | PartRequestUpdate,
    attachments: list[discord.Attachment],
) -> tuple[int, int]:
    """Download attachments and create media records for a record.

    Uses discord.py's attachment.read() for auth-handled downloads.
    Downloads are processed serially; each attachment is read into memory
    then passed to the existing media pipeline. Discord's 25MB limit per
    attachment keeps memory usage reasonable.

    Args:
        record: The Flipfix record to attach media to.
        attachments: List of Discord attachments to download.

    Returns:
        Tuple of (success_count, failure_count) for user feedback.
    """
    if not attachments:
        return 0, 0

    unique_attachments = _dedupe_by_url(attachments)
    media_class, parent_field, model_name = _get_media_class_and_parent_field(record)

    success = 0
    failed = 0

    for attachment in unique_attachments:
        try:
            data = await attachment.read()

            # Create media record synchronously (uses Django's DB)
            await _create_media_record(
                media_class=media_class,
                parent_field=parent_field,
                record=record,
                model_name=model_name,
                attachment_filename=attachment.filename,
                data=data,
                content_type=attachment.content_type or "",
            )
            success += 1

            logger.info(
                "discord_attachment_downloaded",
                extra={
                    "record_type": type(record).__name__,
                    "record_id": record.pk,
                    "attachment_filename": attachment.filename,
                    "size": len(data),
                },
            )

        except Exception:
            logger.warning(
                "discord_attachment_download_failed",
                extra={
                    "record_type": type(record).__name__,
                    "record_id": record.pk,
                    "attachment_filename": attachment.filename,
                    "attachment_url": attachment.url,
                },
                exc_info=True,
            )
            failed += 1

    return success, failed


@sync_to_async
def _create_media_record(
    media_class: MediaModelClass,
    parent_field: str,
    record: LogEntry | ProblemReport | PartRequest | PartRequestUpdate,
    model_name: str,
    attachment_filename: str,
    data: bytes,
    content_type: str,
) -> None:
    """Create a media record from downloaded data.

    Wraps in transaction and enqueues video transcoding if needed.
    """
    is_video = _is_video(attachment_filename)

    # Create an InMemoryUploadedFile to feed to the media model
    # This allows the model's save() to process photos (resize, thumbnail)
    file_buffer = BytesIO(data)
    uploaded_file = InMemoryUploadedFile(
        file=file_buffer,
        field_name="file",
        name=attachment_filename,
        content_type=content_type,
        size=len(data),
        charset=None,
    )

    with transaction.atomic():
        media = media_class.objects.create(
            **{parent_field: record},
            media_type=AbstractMedia.MediaType.VIDEO if is_video else AbstractMedia.MediaType.PHOTO,
            file=uploaded_file,
            transcode_status=AbstractMedia.TranscodeStatus.PENDING if is_video else "",
        )

        if is_video:
            transaction.on_commit(
                partial(enqueue_transcode, media_id=media.id, model_name=model_name)
            )
