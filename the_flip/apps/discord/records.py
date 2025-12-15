"""Record creation for Discord bot.

Creates LogEntry, ProblemReport, and PartRequest records from Discord suggestions.
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
from the_flip.apps.discord.llm import RecordSuggestion
from the_flip.apps.discord.models import DiscordMessageMapping, DiscordUserLink
from the_flip.apps.maintenance.models import LogEntry, ProblemReport
from the_flip.apps.parts.models import PartRequest

logger = logging.getLogger(__name__)


@dataclass
class CreatedRecord:
    """Result of creating a record."""

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
    discord_user_id: str,
    discord_message_id: int,
    discord_username: str | None = None,
    discord_display_name: str | None = None,
) -> CreatedRecord:
    """Create a record from a suggestion.

    This function is atomic - all database operations (record creation,
    message mapping, user linking) either all succeed or all roll back.

    Args:
        suggestion: The LLM-generated suggestion
        discord_user_id: The Discord user ID who initiated the action
        discord_message_id: The target Discord message ID
        discord_username: The Discord username (for auto-linking)
        discord_display_name: The Discord display name (for auto-linking)

    Returns:
        CreatedRecord with the created record's type, ID, and URL
    """
    # Get the machine
    machine = MachineInstance.objects.filter(slug=suggestion.machine_slug).first()
    if not machine:
        raise ValueError(f"Machine not found: {suggestion.machine_slug}")

    # Try to get the maintainer linked to this Discord user (may auto-link)
    maintainer = _get_maintainer_for_discord_user(
        discord_user_id, discord_username, discord_display_name
    )

    base_url = _get_base_url()
    record_obj: LogEntry | ProblemReport | PartRequest

    if suggestion.record_type == "log_entry":
        record_obj = _create_log_entry(
            machine, suggestion.description, maintainer, discord_display_name
        )
        url = base_url + reverse("log-detail", kwargs={"pk": record_obj.pk})
        record_id = record_obj.pk

    elif suggestion.record_type == "problem_report":
        record_obj = _create_problem_report(
            machine, suggestion.description, maintainer, discord_display_name
        )
        url = base_url + reverse("problem-report-detail", kwargs={"pk": record_obj.pk})
        record_id = record_obj.pk

    elif suggestion.record_type == "part_request":
        if not maintainer:
            raise ValueError("Cannot create part request without a linked maintainer")
        record_obj = _create_part_request(machine, suggestion.description, maintainer)
        url = base_url + reverse("part-request-detail", kwargs={"pk": record_obj.pk})
        record_id = record_obj.pk

    else:
        raise ValueError(f"Unknown record type: {suggestion.record_type}")

    # Mark the Discord message as processed
    DiscordMessageMapping.mark_processed(str(discord_message_id), record_obj)

    logger.info(
        "discord_record_created",
        extra={
            "record_type": suggestion.record_type,
            "record_id": record_id,
            "machine_slug": suggestion.machine_slug,
            "discord_user_id": discord_user_id,
            "discord_message_id": discord_message_id,
        },
    )

    return CreatedRecord(
        record_type=suggestion.record_type,
        record_id=record_id,
        url=url,
    )


def _get_maintainer_for_discord_user(
    discord_user_id: str,
    discord_username: str | None = None,
    discord_display_name: str | None = None,
) -> Maintainer | None:
    """Get the Maintainer linked to a Discord user.

    If no link exists but we find a maintainer with a matching username,
    auto-create the link using get_or_create for idempotency.
    """
    # First, check for existing link
    link = (
        DiscordUserLink.objects.select_related("maintainer")
        .filter(discord_user_id=discord_user_id)
        .first()
    )
    if link:
        return link.maintainer

    # No existing link - try to auto-link by username or display name match
    maintainer = None

    # First try matching Discord username to Flipfix username
    if discord_username:
        maintainer = Maintainer.objects.filter(user__username__iexact=discord_username).first()

    # If no match, try matching Discord display name to Flipfix username
    if not maintainer and discord_display_name:
        maintainer = Maintainer.objects.filter(user__username__iexact=discord_display_name).first()

    if maintainer:
        # Auto-create the link using get_or_create for idempotency
        # (handles race conditions where another request creates the link first)
        link, created = DiscordUserLink.objects.get_or_create(
            discord_user_id=discord_user_id,
            defaults={
                "discord_username": discord_username or "",
                "discord_display_name": discord_display_name or "",
                "maintainer": maintainer,
            },
        )
        if created:
            logger.info(
                "discord_user_auto_linked",
                extra={
                    "discord_user_id": discord_user_id,
                    "discord_username": discord_username,
                    "discord_display_name": discord_display_name,
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
) -> LogEntry:
    """Create a LogEntry record."""
    fallback_name = discord_display_name or "Discord"
    log_entry = LogEntry.objects.create(
        machine=machine,
        text=description,
        maintainer_names="" if maintainer else fallback_name,
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
    """Create a ProblemReport record."""
    fallback_name = discord_display_name or "Discord"
    return ProblemReport.objects.create(
        machine=machine,
        description=description,
        problem_type=ProblemReport.PROBLEM_OTHER,
        reported_by_user=maintainer.user if maintainer else None,
        reported_by_name="" if maintainer else fallback_name,
    )


def _create_part_request(
    machine: MachineInstance,
    description: str,
    maintainer: Maintainer,
) -> PartRequest:
    """Create a PartRequest record."""
    return PartRequest.objects.create(
        machine=machine,
        text=description,
        requested_by=maintainer,
    )
