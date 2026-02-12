"""Record creation for Discord bot.

Creates Flipfix records from Discord suggestions by delegating to
registered bot handlers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import transaction
from django.db.models import Model
from django.utils import timezone

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.discord.llm import RecordSuggestion
from the_flip.apps.discord.models import DiscordMessageMapping, DiscordUserLink
from the_flip.apps.discord.types import DiscordUserInfo

if TYPE_CHECKING:
    import discord

logger = logging.getLogger(__name__)


@dataclass
class RecordCreationResult:
    """Result of creating a Flipfix record from a Discord suggestion."""

    record_type: str
    record_id: int
    url: str
    record_obj: Model | None = None


def _get_base_url() -> str:
    """Get the base URL for building record links."""
    if not hasattr(settings, "SITE_URL") or not settings.SITE_URL:
        raise ValueError("SITE_URL must be configured in settings")
    return settings.SITE_URL.rstrip("/")


# Prefix used to identify Flipfix user names (vs Discord snowflake IDs)
FLIPFIX_AUTHOR_PREFIX = "flipfix/"


def _resolve_author(
    author_id: str,
    author_id_map: dict[str, DiscordUserInfo],
) -> tuple[Maintainer | None, str]:
    """Resolve author_id to a Maintainer and fallback display name.

    Args:
        author_id: Either a Discord snowflake ID (17-19 digits) or a
            "flipfix/Name" prefixed string for webhook-sourced authors.
        author_id_map: Mapping of Discord user IDs to DiscordUserInfo.

    Returns:
        Tuple of (maintainer, display_name). Maintainer may be None if
        the author can't be linked to a Flipfix user.
    """
    if author_id.startswith(FLIPFIX_AUTHOR_PREFIX):
        # Webhook-sourced author: lookup by name
        name = author_id[len(FLIPFIX_AUTHOR_PREFIX) :]
        maintainer = Maintainer.match_by_name(name)
        return maintainer, name
    else:
        # Discord user ID: lookup in map, then resolve to maintainer
        discord_user = author_id_map.get(author_id)
        if discord_user:
            maintainer = _get_or_link_maintainer(discord_user)
            fallback: str = discord_user.display_name or discord_user.username or "Discord"
            return maintainer, fallback
        # Unknown author_id - can't resolve
        return None, "Discord"


def _resolve_occurred_at(
    source_message_ids: list[str],
    message_timestamp_map: dict[str, datetime],
) -> datetime:
    """Get the latest timestamp from source messages (when content was finalized).

    We use the latest timestamp because records typically represent the final state
    of a conversation - e.g., a log entry "fixed the flipper" should be timestamped
    when the fix was done, not when the problem was first reported.

    Falls back to current time if no matching timestamps found.
    """
    timestamps = [
        message_timestamp_map[msg_id]
        for msg_id in source_message_ids
        if msg_id in message_timestamp_map
    ]
    return max(timestamps) if timestamps else timezone.now()


@sync_to_async
@transaction.atomic
def create_record(
    suggestion: RecordSuggestion,
    author_id: str,
    author_id_map: dict[str, DiscordUserInfo],
    message_timestamp_map: dict[str, datetime],
) -> RecordCreationResult:
    """Create a Flipfix record from a suggestion (atomic transaction).

    Delegates type-specific creation to the registered bot handler.

    Args:
        suggestion: The record to create.
        author_id: Author identifier - either a Discord snowflake ID (17-19 digits)
            or a "flipfix/Name" prefixed string for webhook-sourced authors.
        author_id_map: Mapping of Discord user IDs to DiscordUserInfo.
        message_timestamp_map: Mapping of message IDs to their timestamps.
    """
    from the_flip.apps.discord.bot_handlers import get_bot_handler

    # Get the machine (required for log_entry and problem_report, optional for parts)
    machine: MachineInstance | None = None
    if suggestion.slug:
        machine = MachineInstance.objects.filter(slug=suggestion.slug).first()
        if not machine:
            raise ValueError(f"Machine not found: {suggestion.slug}")

    # Resolve author_id to maintainer and fallback display name
    maintainer, display_name = _resolve_author(author_id, author_id_map)

    # Resolve occurred_at from source message timestamps
    occurred_at = _resolve_occurred_at(suggestion.source_message_ids, message_timestamp_map)

    # Look up the handler for this record type
    handler = get_bot_handler(suggestion.record_type)
    if not handler:
        raise ValueError(f"Unknown record type: {suggestion.record_type}")

    base_url = _get_base_url()

    # Delegate creation to the handler
    record_obj = handler.create_from_suggestion(
        description=suggestion.description,
        machine=machine,
        maintainer=maintainer,
        display_name=display_name,
        parent_record_id=suggestion.parent_record_id,
        occurred_at=occurred_at,
    )

    url = base_url + handler.get_detail_url(record_obj)

    # Mark all source messages as processed
    for message_id in suggestion.source_message_ids:
        DiscordMessageMapping.mark_processed(str(message_id), record_obj)

    logger.info(
        "discord_record_created",
        extra={
            "record_type": suggestion.record_type,
            "record_id": record_obj.pk,
            "slug": suggestion.slug,
            "author_id": author_id,
            "source_message_count": len(suggestion.source_message_ids),
        },
    )

    return RecordCreationResult(
        record_type=suggestion.record_type,
        record_id=record_obj.pk,
        url=url,
        record_obj=record_obj,
    )


def _get_or_link_maintainer(discord_user: DiscordUserInfo) -> Maintainer | None:
    """Resolve a Discord user to a Flipfix Maintainer, auto-linking if possible.

    May create a DiscordUserLink record if no link exists but a Maintainer
    is found with a matching username.
    """
    # First, check for existing link
    link = (
        DiscordUserLink.objects.select_related("maintainer")
        .filter(discord_user_id=discord_user.user_id)
        .first()
    )
    if link:
        return link.maintainer

    # No existing link - try to auto-link by username or display name match
    maintainer = None

    # First try matching Discord username to Flipfix username
    if discord_user.username:
        maintainer = Maintainer.objects.filter(user__username__iexact=discord_user.username).first()

    # If no match, try matching Discord display name to Flipfix username
    if not maintainer and discord_user.display_name:
        maintainer = Maintainer.objects.filter(
            user__username__iexact=discord_user.display_name
        ).first()

    if maintainer:
        # Auto-create the link using get_or_create for idempotency
        # (handles race conditions where another request creates the link first)
        link, created = DiscordUserLink.objects.get_or_create(
            discord_user_id=discord_user.user_id,
            defaults={
                "discord_username": discord_user.username or "",
                "discord_display_name": discord_user.display_name or "",
                "maintainer": maintainer,
            },
        )
        if created:
            logger.info(
                "discord_user_auto_linked",
                extra={
                    "discord_user_id": discord_user.user_id,
                    "discord_username": discord_user.username,
                    "discord_display_name": discord_user.display_name,
                    "maintainer_id": maintainer.id,
                },
            )
        return link.maintainer

    return None


@dataclass
class RecordWithMediaResult:
    """Result of creating a record with media attachments."""

    result: RecordCreationResult
    media_success: int
    media_failed: int


async def create_record_with_media(
    suggestion: RecordSuggestion,
    author_id: str,
    author_id_map: dict[str, DiscordUserInfo],
    message_timestamp_map: dict[str, datetime],
    message_attachments: dict[str, list[discord.Attachment]],
) -> RecordWithMediaResult:
    """Create record, then download and attach media.

    This separates DB work (atomic transaction) from media downloads (network I/O).
    Media is downloaded after the DB transaction commits.

    Args:
        suggestion: The record to create.
        author_id: Author identifier for attribution.
        author_id_map: Mapping of Discord user IDs to DiscordUserInfo.
        message_timestamp_map: Mapping of message IDs to their timestamps.
        message_attachments: Mapping of message IDs to their attachments.

    Returns:
        RecordWithMediaResult with creation result and media counts.
    """
    # First, create the record (DB transaction)
    result = await create_record(suggestion, author_id, author_id_map, message_timestamp_map)

    # Gather attachments from source messages
    all_attachments: list[discord.Attachment] = []
    for msg_id in suggestion.source_message_ids:
        all_attachments.extend(message_attachments.get(msg_id, []))

    # Download media after DB transaction committed
    media_success = 0
    media_failed = 0
    if all_attachments and result.record_obj:
        from the_flip.apps.discord.media import download_and_create_media

        media_success, media_failed = await download_and_create_media(
            result.record_obj, all_attachments
        )

    return RecordWithMediaResult(
        result=result,
        media_success=media_success,
        media_failed=media_failed,
    )
