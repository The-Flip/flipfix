"""Record creation for Discord bot.

Creates LogEntry, ProblemReport, PartRequest, and PartRequestUpdate records
from Discord suggestions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

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

logger = logging.getLogger(__name__)


@dataclass
class RecordCreationResult:
    """Result of creating a Flipfix record from a Discord suggestion."""

    record_type: str
    record_id: int
    url: str


def _get_base_url() -> str:
    """Get the base URL for building record links."""
    if not hasattr(settings, "SITE_URL") or not settings.SITE_URL:
        raise ValueError("SITE_URL must be configured in settings")
    return settings.SITE_URL.rstrip("/")


@sync_to_async
@transaction.atomic
def create_record(
    suggestion: RecordSuggestion,
    discord_user: DiscordUserInfo,
) -> RecordCreationResult:
    """Create a Flipfix record from a suggestion (atomic transaction)."""
    # Get the machine (required for log_entry and problem_report, optional for parts)
    machine: MachineInstance | None = None
    if suggestion.slug:
        machine = MachineInstance.objects.filter(slug=suggestion.slug).first()
        if not machine:
            raise ValueError(f"Machine not found: {suggestion.slug}")

    # Resolve Discord user to Flipfix maintainer (auto-links if usernames match)
    maintainer = _get_or_link_maintainer(discord_user)

    base_url = _get_base_url()
    record_obj: LogEntry | ProblemReport | PartRequest | PartRequestUpdate

    if suggestion.record_type == RecordType.LOG_ENTRY:
        if not machine:
            raise ValueError(
                f"Machine is required for log_entry (slug={suggestion.slug!r} not found)"
            )
        record_obj = _create_log_entry(
            machine,
            suggestion.description,
            maintainer,
            discord_user.display_name,
            suggestion.parent_record_id,
        )
        url = base_url + reverse("log-detail", kwargs={"pk": record_obj.pk})

    elif suggestion.record_type == RecordType.PROBLEM_REPORT:
        if not machine:
            raise ValueError(
                f"Machine is required for problem_report (slug={suggestion.slug!r} not found)"
            )
        record_obj = _create_problem_report(
            machine, suggestion.description, maintainer, discord_user.display_name
        )
        url = base_url + reverse("problem-report-detail", kwargs={"pk": record_obj.pk})

    elif suggestion.record_type == RecordType.PART_REQUEST:
        if not maintainer:
            raise ValueError(
                f"Cannot create part request without a linked maintainer "
                f"(discord_user_id={discord_user.user_id!r})"
            )
        record_obj = _create_part_request(machine, suggestion.description, maintainer)
        url = base_url + reverse("part-request-detail", kwargs={"pk": record_obj.pk})

    elif suggestion.record_type == RecordType.PART_REQUEST_UPDATE:
        if not maintainer:
            raise ValueError(
                f"Cannot create part request update without a linked maintainer "
                f"(discord_user_id={discord_user.user_id!r})"
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
            "discord_user_id": discord_user.user_id,
            "source_message_count": len(suggestion.source_message_ids),
        },
    )

    return RecordCreationResult(
        record_type=suggestion.record_type,
        record_id=record_obj.pk,
        url=url,
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
