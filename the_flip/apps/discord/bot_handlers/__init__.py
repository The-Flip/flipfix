"""Bot record handlers for creating Flipfix records from Discord.

Each handler class encapsulates everything needed to create one record type
from a Discord bot suggestion: validation, creation, media model mapping,
and URL parsing for webhook embed context.

This package is completely separate from webhook_handlers/. You never need
to touch these files when adding webhook-only record types (e.g., wiki pages).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from django.db.models import Model

from the_flip.apps.discord.llm import RecordType

logger = logging.getLogger(__name__)

# Registry of bot record handlers, keyed by handler name (e.g., "log_entry")
_registry: dict[str, BotRecordHandler] = {}


class BotRecordHandler:
    """Base class for bot record creation handlers.

    Subclass this and set the class attributes, then implement
    create_from_suggestion() and get_detail_url().
    """

    # --- Identity (must be set by subclass) ---
    name: str  # e.g., "log_entry" — matches webhook handler name
    display_name: str  # e.g., "Log Entry" — for wizard UI

    # --- LLM schema ---
    machine_required: bool = False
    parent_handler_name: str | None = None  # e.g., "problem_report" for log_entry
    child_type_name: str | None = None  # e.g., "log_entry" for problem_report

    # --- Media (None if type has no media attachments) ---
    media_model_name: str | None = None  # e.g., "LogEntryMedia"

    # --- Context parsing (for recognizing webhook embeds in Discord messages) ---
    url_pattern: re.Pattern[str] | None = None  # e.g., re.compile(r"/logs/(\d+)$")

    def create_from_suggestion(
        self,
        *,
        description: str,
        machine: Any | None,
        maintainer: Any | None,
        display_name: str,
        parent_record_id: int | None,
        occurred_at: datetime,
    ) -> Model:
        """Create a record from a Discord bot suggestion.

        Args:
            description: The record description text.
            machine: MachineInstance or None.
            maintainer: Maintainer or None.
            display_name: Fallback display name if no maintainer.
            parent_record_id: ID of parent record, if applicable.
            occurred_at: When the work/event occurred.

        Returns:
            The created Django model instance.

        Raises:
            ValueError: If required fields are missing.
        """
        raise NotImplementedError

    def get_detail_url(self, obj: Any) -> str:
        """Return the URL path for the created record's detail page."""
        raise NotImplementedError

    @property
    def record_type(self) -> RecordType:
        """Return the RecordType enum value for this handler."""
        return RecordType(self.name)


def register(handler: BotRecordHandler) -> None:
    """Register a bot record handler instance."""
    _registry[handler.name] = handler


def get_bot_handler(name: str) -> BotRecordHandler | None:
    """Look up a bot record handler by name."""
    return _registry.get(name)


def get_all_bot_handlers() -> list[BotRecordHandler]:
    """Return all registered bot record handlers."""
    return list(_registry.values())
