"""Webhook delivery tasks using Django Q."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import requests
from django_q.tasks import async_task

from the_flip.apps.discord.models import DiscordMessageMapping
from the_flip.logging import bind_log_context, current_log_context, reset_log_context

if TYPE_CHECKING:
    from django.db.models import Model

    from the_flip.apps.discord.webhook_handlers import WebhookHandler

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WebhookDeliveryResult:
    """Result of a webhook delivery attempt."""

    status: str  # "success", "error", "skipped"
    reason: str | None = None  # Why skipped or errored
    status_code: int | None = None  # HTTP status code on success


def dispatch_webhook(handler_name: str, object_id: int) -> None:
    """Queue a webhook delivery task for the given event.

    This function is called synchronously from signal handlers and
    enqueues the actual webhook delivery to run asynchronously.

    Checks if webhooks are enabled before queueing to avoid filling
    the task queue when webhooks are disabled.
    """
    from constance import config

    if not config.DISCORD_WEBHOOKS_ENABLED or not config.DISCORD_WEBHOOK_URL:
        return

    from the_flip.apps.discord.webhook_handlers import get_webhook_handler

    handler = get_webhook_handler(handler_name)
    if not handler:
        logger.warning("discord_unknown_webhook_handler", extra={"handler_name": handler_name})
        return

    # Skip creation webhooks for Discord-originated records (avoids echo).
    # Only suppress *_created events - future update events should still post.
    if handler.event_type.endswith("_created"):
        model_class = handler.get_model_class()
        if DiscordMessageMapping.has_mapping_for(model_class, object_id):
            return

    async_task(
        "the_flip.apps.discord.tasks.deliver_webhook",
        handler_name,
        object_id,
        current_log_context(),
        timeout=60,
    )


def deliver_webhook(
    handler_name: str, object_id: int, log_context: dict | None = None
) -> WebhookDeliveryResult:
    """Deliver webhook for a given event to the configured Discord webhook URL.

    This runs asynchronously via Django Q.
    """
    from constance import config

    token = bind_log_context(**log_context) if log_context else None

    try:
        # Check if webhook URL is configured
        webhook_url = config.DISCORD_WEBHOOK_URL
        if not webhook_url:
            return WebhookDeliveryResult(status="skipped", reason="no webhook URL configured")

        # Check global settings
        if not config.DISCORD_WEBHOOKS_ENABLED:
            return WebhookDeliveryResult(status="skipped", reason="webhooks globally disabled")

        # Look up the handler
        from the_flip.apps.discord.webhook_handlers import get_webhook_handler

        handler = get_webhook_handler(handler_name)
        if not handler:
            return WebhookDeliveryResult(status="error", reason=f"Unknown handler: {handler_name}")

        # Fetch the object with optimized queries
        obj = handler.get_object(object_id)
        if obj is None:
            return WebhookDeliveryResult(
                status="error", reason=f"{handler_name} {object_id} not found"
            )

        # Format and deliver
        return _deliver_to_url(webhook_url, handler, obj)
    finally:
        if token:
            reset_log_context(token)


def _deliver_to_url(
    url: str,
    handler: WebhookHandler,
    obj: Model,
) -> WebhookDeliveryResult:
    """Deliver a webhook to a URL."""
    try:
        payload = handler.format_webhook_message(obj)
        response = requests.post(
            url,
            json=payload,
            timeout=10,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        return WebhookDeliveryResult(status="success", status_code=response.status_code)
    except requests.RequestException as e:
        logger.warning(
            "discord_webhook_delivery_failed",
            extra={"error": str(e)},
        )
        return WebhookDeliveryResult(status="error", reason=str(e))


def send_test_webhook(event_type: str) -> dict:
    """Send a test webhook to the configured URL.

    This is called directly (not via async_task) from the admin UI
    so the user gets immediate feedback.
    """
    from constance import config

    from the_flip.apps.discord.formatters import format_test_message

    webhook_url = config.DISCORD_WEBHOOK_URL
    if not webhook_url:
        return {"status": "error", "error": "No webhook URL configured"}

    try:
        payload = format_test_message(event_type)
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=10,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        return {
            "status": "success",
            "message": "Test message sent successfully",
        }
    except requests.RequestException as e:
        return {
            "status": "error",
            "error": str(e),
        }
