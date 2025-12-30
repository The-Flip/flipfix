"""Record creation for Discord bot.

Creates LogEntry, ProblemReport, PartRequest, and PartRequestUpdate records
from Discord suggestions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import transaction
from django.urls import reverse

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.discord.llm import RecordSuggestion, RecordType
from the_flip.apps.discord.models import DiscordMessageMapping, DiscordUserLink
from the_flip.apps.discord.types import DiscordUserInfo
from the_flip.apps.maintenance.models import LogEntry, ProblemReport
from the_flip.apps.parts.models import PartRequest, PartRequestUpdate

if TYPE_CHECKING:
    import discord

logger = logging.getLogger(__name__)


@dataclass
class RecordCreationResult:
    """Result of creating a Flipfix record from a Discord suggestion."""

    record_type: str
    record_id: int
    url: str
    record_obj: LogEntry | ProblemReport | PartRequest | PartRequestUpdate | None = None


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


@sync_to_async
@transaction.atomic
def create_record(
    suggestion: RecordSuggestion,
    author_id: str,
    author_id_map: dict[str, DiscordUserInfo],
) -> RecordCreationResult:
    """Create a Flipfix record from a suggestion (atomic transaction).

    Args:
        suggestion: The record to create.
        author_id: Author identifier - either a Discord snowflake ID (17-19 digits)
            or a "flipfix/Name" prefixed string for webhook-sourced authors.
        author_id_map: Mapping of Discord user IDs to DiscordUserInfo.
    """
    # Get the machine (required for log_entry and problem_report, optional for parts)
    machine: MachineInstance | None = None
    if suggestion.slug:
        machine = MachineInstance.objects.filter(slug=suggestion.slug).first()
        if not machine:
            raise ValueError(f"Machine not found: {suggestion.slug}")

    # Resolve author_id to maintainer and fallback display name
    maintainer, display_name = _resolve_author(author_id, author_id_map)

    base_url = _get_base_url()
    record_obj: LogEntry | ProblemReport | PartRequest | PartRequestUpdate

    if suggestion.record_type == RecordType.LOG_ENTRY:
        # If no machine specified but has parent_record_id, inherit machine from parent
        if not machine and suggestion.parent_record_id:
            parent_report = ProblemReport.objects.filter(pk=suggestion.parent_record_id).first()
            if parent_report:
                machine = parent_report.machine
        if not machine:
            raise ValueError(
                f"Machine is required for log_entry (slug={suggestion.slug!r} not found)"
            )
        record_obj = _create_log_entry(
            machine,
            suggestion.description,
            maintainer,
            display_name,
            suggestion.parent_record_id,
        )
        url = base_url + reverse("log-detail", kwargs={"pk": record_obj.pk})

    elif suggestion.record_type == RecordType.PROBLEM_REPORT:
        if not machine:
            raise ValueError(
                f"Machine is required for problem_report (slug={suggestion.slug!r} not found)"
            )
        record_obj = _create_problem_report(
            machine, suggestion.description, maintainer, display_name
        )
        url = base_url + reverse("problem-report-detail", kwargs={"pk": record_obj.pk})

    elif suggestion.record_type == RecordType.PART_REQUEST:
        if not maintainer:
            raise ValueError(
                f"Cannot create part request without a linked maintainer (author_id={author_id!r})"
            )
        record_obj = _create_part_request(machine, suggestion.description, maintainer)
        url = base_url + reverse("part-request-detail", kwargs={"pk": record_obj.pk})

    elif suggestion.record_type == RecordType.PART_REQUEST_UPDATE:
        if not maintainer:
            raise ValueError(
                f"Cannot create part request update without a linked maintainer "
                f"(author_id={author_id!r})"
            )
        if not suggestion.parent_record_id:
            raise ValueError(
                "part_request_update requires parent_record_id (none provided in suggestion)"
            )
        record_obj = _create_part_request_update(
            suggestion.parent_record_id, suggestion.description, maintainer
        )
        # URL points to parent part request (update doesn't have its own page)
        url = base_url + reverse("part-request-detail", kwargs={"pk": suggestion.parent_record_id})

    else:
        raise ValueError(f"Unknown record type: {suggestion.record_type}")

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


def _create_log_entry(
    machine: MachineInstance,
    description: str,
    maintainer: Maintainer | None,
    discord_display_name: str | None = None,
    parent_record_id: int | None = None,
) -> LogEntry:
    """Create a LogEntry record, optionally linking to a parent problem report."""
    fallback_name = discord_display_name or "Discord"

    # Look up parent problem report if specified
    problem_report = None
    if parent_record_id:
        problem_report = ProblemReport.objects.filter(pk=parent_record_id).first()
        if not problem_report:
            logger.warning(
                "discord_parent_problem_report_not_found",
                extra={"parent_record_id": parent_record_id},
            )

    log_entry = LogEntry.objects.create(
        machine=machine,
        text=description,
        maintainer_names="" if maintainer else fallback_name,
        problem_report=problem_report,
    )

    if maintainer:
        log_entry.maintainers.add(maintainer)

    return log_entry


def _create_problem_report(
    machine: MachineInstance,
    description: str,
    maintainer: Maintainer | None,
    discord_display_name: str | None = None,
) -> ProblemReport:
    """Create a ProblemReport record for a machine."""
    fallback_name = discord_display_name or "Discord"
    return ProblemReport.objects.create(
        machine=machine,
        description=description,
        problem_type=ProblemReport.ProblemType.OTHER,
        reported_by_user=maintainer.user if maintainer else None,
        reported_by_name="" if maintainer else fallback_name,
    )


def _create_part_request(
    machine: MachineInstance | None,
    description: str,
    maintainer: Maintainer,
) -> PartRequest:
    """Create a PartRequest record (machine is optional)."""
    return PartRequest.objects.create(
        machine=machine,
        text=description,
        requested_by=maintainer,
    )


def _create_part_request_update(
    parent_record_id: int,
    description: str,
    maintainer: Maintainer,
) -> PartRequestUpdate:
    """Create a PartRequestUpdate record. Raises ValueError if parent not found."""
    part_request = PartRequest.objects.filter(pk=parent_record_id).first()
    if not part_request:
        raise ValueError(f"Part request not found: {parent_record_id}")

    return PartRequestUpdate.objects.create(
        part_request=part_request,
        text=description,
        posted_by=maintainer,
    )


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
    message_attachments: dict[str, list[discord.Attachment]],
) -> RecordWithMediaResult:
    """Create record, then download and attach media.

    This separates DB work (atomic transaction) from media downloads (network I/O).
    Media is downloaded after the DB transaction commits.

    Args:
        suggestion: The record to create.
        author_id: Author identifier for attribution.
        author_id_map: Mapping of Discord user IDs to DiscordUserInfo.
        message_attachments: Mapping of message IDs to their attachments.

    Returns:
        RecordWithMediaResult with creation result and media counts.
    """
    # First, create the record (DB transaction)
    result = await create_record(suggestion, author_id, author_id_map)

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
