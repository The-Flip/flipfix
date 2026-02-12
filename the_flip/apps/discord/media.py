"""Media download and upload for Discord bot.

Downloads Discord attachments and uploads them to the web service via HTTP API.
The Discord bot service on Railway cannot store media directly (no persistent storage).
Instead, it downloads from Discord CDN and uploads to the web service's media API endpoint.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from decouple import config
from django.db.models import Model

from the_flip.apps.core.media import ALLOWED_VIDEO_EXTENSIONS

if TYPE_CHECKING:
    import discord

logger = logging.getLogger(__name__)

# Configuration for web service communication
DJANGO_WEB_SERVICE_URL = config("DJANGO_WEB_SERVICE_URL", default="")
TRANSCODING_UPLOAD_TOKEN = config("TRANSCODING_UPLOAD_TOKEN", default="")

# HTTP timeout for uploads (60 seconds)
HTTP_UPLOAD_TIMEOUT = 60


def is_media_upload_configured() -> bool:
    """Check if media upload to web service is configured.

    Call this at bot startup to fail fast if configuration is missing.
    Returns True if both DJANGO_WEB_SERVICE_URL and TRANSCODING_UPLOAD_TOKEN are set.
    """
    return bool(DJANGO_WEB_SERVICE_URL and TRANSCODING_UPLOAD_TOKEN)


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


def _get_media_model_name(record: Model) -> str:
    """Get the media model name for the web service API.

    Looks up the bot handler for the record type to find the media model name.
    """
    from the_flip.apps.discord.bot_handlers import get_all_bot_handlers

    record_class_name = type(record).__name__
    for handler in get_all_bot_handlers():
        if not handler.media_model_name:
            continue
        # Media model names follow the pattern "XMedia" where X is the model class name
        # e.g., "LogEntryMedia" -> "LogEntry", "ProblemReportMedia" -> "ProblemReport"
        expected_class = handler.media_model_name.replace("Media", "")
        if record_class_name == expected_class:
            return handler.media_model_name

    raise ValueError(f"No media model name configured for: {record_class_name}")


async def download_and_create_media(
    record: Model,
    attachments: list[discord.Attachment],
) -> tuple[int, int]:
    """Download attachments from Discord and upload to web service.

    Downloads from Discord CDN using discord.py's attachment.read() for auth handling.
    Uploads to web service via HTTP API for persistent storage.

    Args:
        record: The Flipfix record to attach media to.
        attachments: List of Discord attachments to download.

    Returns:
        Tuple of (success_count, failure_count) for user feedback.
    """
    if not attachments:
        return 0, 0

    # Validate configuration (use is_media_upload_configured() at bot startup for fail-fast)
    if not is_media_upload_configured():
        logger.error(
            "discord_media_upload_not_configured",
            extra={
                "has_url": bool(DJANGO_WEB_SERVICE_URL),
                "has_token": bool(TRANSCODING_UPLOAD_TOKEN),
            },
        )
        return 0, len(attachments)

    unique_attachments = _dedupe_by_url(attachments)
    model_name = _get_media_model_name(record)
    parent_id = record.pk

    success = 0
    failed = 0

    async with httpx.AsyncClient(timeout=HTTP_UPLOAD_TIMEOUT) as client:
        for attachment in unique_attachments:
            try:
                # Download from Discord CDN
                file_bytes = await attachment.read()

                # Upload to web service
                await _upload_to_web_service(
                    client=client,
                    model_name=model_name,
                    parent_id=parent_id,
                    filename=attachment.filename,
                    file_bytes=file_bytes,
                    content_type=attachment.content_type or "",
                )
                success += 1

                logger.info(
                    "discord_attachment_downloaded",
                    extra={
                        "record_type": type(record).__name__,
                        "record_id": record.pk,
                        "attachment_filename": attachment.filename,
                        "size": len(file_bytes),
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


async def _upload_to_web_service(
    client: httpx.AsyncClient,
    model_name: str,
    parent_id: int,
    filename: str,
    file_bytes: bytes,
    content_type: str,
) -> None:
    """Upload media file to web service via HTTP API.

    Args:
        client: httpx async client for HTTP requests.
        model_name: Media model name (e.g., "LogEntryMedia").
        parent_id: ID of the parent record.
        filename: Original filename from Discord.
        file_bytes: File content as bytes.
        content_type: MIME type of the file.

    Raises:
        RuntimeError: If upload fails.
    """
    url = f"{DJANGO_WEB_SERVICE_URL.rstrip('/')}/api/media/{model_name}/{parent_id}/"
    headers = {"Authorization": f"Bearer {TRANSCODING_UPLOAD_TOKEN}"}

    # httpx file upload format: (filename, content, content_type)
    files = {"file": (filename, file_bytes, content_type or "application/octet-stream")}

    response = await client.post(url, files=files, headers=headers)

    if response.status_code != 200:
        raise RuntimeError(f"Upload failed: HTTP {response.status_code} - {response.text[:200]}")

    result = response.json()
    logger.info(
        "discord_media_upload_success",
        extra={
            "model_name": model_name,
            "parent_id": parent_id,
            "media_id": result.get("media_id"),
            "media_type": result.get("media_type"),
        },
    )
