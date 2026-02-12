"""Webhook handlers for posting records to Discord.

Each handler class encapsulates everything needed to post one record type
to Discord: signal registration, query optimization, and message formatting.

To add a new record type (e.g., wiki pages):
1. Create a new handler file in this package
2. Import it in discord/apps.py
3. Done. No other files need changing.
"""

from __future__ import annotations

import logging
from functools import partial
from typing import Any

from django.db import transaction
from django.db.models.signals import post_save

logger = logging.getLogger(__name__)

# Registry of webhook handlers, keyed by handler name (e.g., "log_entry")
_registry: dict[str, WebhookHandler] = {}


class WebhookHandler:
    """Base class for Discord webhook handlers.

    Subclass this and set the class attributes, then implement
    format_webhook_message() and get_detail_url().
    """

    # --- Identity (must be set by subclass) ---
    name: str  # e.g., "log_entry"
    event_type: str  # e.g., "log_entry_created"
    model_path: str  # e.g., "maintenance.LogEntry"

    # --- Display (must be set by subclass) ---
    display_name: str  # e.g., "Log Entry"
    emoji: str  # e.g., "🗒️"
    color: int  # Discord embed color

    # --- Query optimization (override in subclass as needed) ---
    select_related: tuple[str, ...] = ()
    prefetch_related: tuple[str, ...] = ()

    def should_notify(self, instance: Any, created: bool) -> bool:
        """Whether this save should post to Discord. Default: creation only."""
        return created

    def get_model_class(self):
        """Get the Django model class for this handler."""
        from django.apps import apps

        return apps.get_model(self.model_path)

    def get_object(self, object_id: int):
        """Fetch the object by ID with optimized related queries."""
        model_class = self.get_model_class()
        queryset = model_class.objects.all()
        if self.select_related:
            queryset = queryset.select_related(*self.select_related)
        if self.prefetch_related:
            queryset = queryset.prefetch_related(*self.prefetch_related)
        return queryset.filter(pk=object_id).first()

    def get_detail_url(self, obj: Any) -> str:
        """Return the URL path for the record's detail page."""
        raise NotImplementedError

    def format_webhook_message(self, obj: Any) -> dict:
        """Build the Discord webhook payload for this record."""
        raise NotImplementedError


def register(handler: WebhookHandler) -> None:
    """Register a webhook handler instance."""
    if handler.name in _registry:
        raise ValueError(f"Duplicate webhook handler name: {handler.name!r}")
    _registry[handler.name] = handler


def get_webhook_handler(name: str) -> WebhookHandler | None:
    """Look up a webhook handler by name."""
    return _registry.get(name)


def get_webhook_handler_by_event(event_type: str) -> WebhookHandler | None:
    """Look up a webhook handler by event type (e.g., 'log_entry_created')."""
    for handler in _registry.values():
        if handler.event_type == event_type:
            return handler
    return None


def get_all_webhook_handlers() -> list[WebhookHandler]:
    """Return all registered webhook handlers."""
    return list(_registry.values())


def connect_signals() -> None:
    """Connect Django post_save signals for all registered webhook handlers.

    Called from DiscordConfig.ready(). Uses dispatch_uid to prevent
    double registration.
    """
    for handler in _registry.values():
        model_class = handler.get_model_class()
        post_save.connect(
            _make_signal_handler(handler),
            sender=model_class,
            dispatch_uid=f"discord_webhook_{handler.name}",
            weak=False,
        )


def _make_signal_handler(handler: WebhookHandler):
    """Create a Django signal handler that dispatches webhooks for a handler."""

    def signal_handler(sender, instance, created, **kwargs):
        if handler.should_notify(instance, created):
            from the_flip.apps.discord.tasks import dispatch_webhook

            transaction.on_commit(
                partial(
                    dispatch_webhook,
                    handler_name=handler.name,
                    object_id=instance.pk,
                )
            )

    return signal_handler
