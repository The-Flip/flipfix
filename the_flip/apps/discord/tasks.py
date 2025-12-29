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
    from the_flip.apps.maintenance.models import LogEntry, ProblemReport
    from the_flip.apps.parts.models import PartRequest, PartRequestUpdate

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WebhookModelConfig:
    """Configuration for webhook model queries."""

    import_path: str
    select_related: tuple[str, ...]
    prefetch_related: tuple[str, ...]


@dataclass(frozen=True)
class WebhookDeliveryResult:
    """Result of a webhook delivery attempt."""

    status: str  # "success", "error", "skipped"
    reason: str | None = None  # Why skipped or errored
    status_code: int | None = None  # HTTP status code on success


def dispatch_webhook(event_type: str, object_id: int, model_name: str) -> None:
    """Queue a webhook delivery task for the given event.

    This function is called synchronously from signal handlers and
    enqueues the actual webhook delivery to run asynchronously.

    Checks if webhooks are enabled before queueing to avoid filling
    the task queue when webhooks are disabled.
    """
    from constance import config

    if not config.DISCORD_WEBHOOKS_ENABLED or not config.DISCORD_WEBHOOK_URL:
        return

    # Skip creation webhooks for Discord-originated records (avoids echo).
    # Only suppress *_created events - future update events should still post.
    if event_type.endswith("_created"):
        model_class = _get_model_class(model_name)
        if model_class and DiscordMessageMapping.has_mapping_for(model_class, object_id):
            return

    async_task(
        "the_flip.apps.discord.tasks.deliver_webhook",
        event_type,
        object_id,
        model_name,
        current_log_context(),
        timeout=60,
    )


def deliver_webhook(
    event_type: str, object_id: int, model_name: str, log_context: dict | None = None
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

        # Check per-event-type settings
        if event_type.startswith("problem_report"):
            if not config.DISCORD_WEBHOOKS_PROBLEM_REPORTS:
                return WebhookDeliveryResult(
                    status="skipped", reason="problem report webhooks disabled"
                )
        elif event_type == "log_entry_created":
            if not config.DISCORD_WEBHOOKS_LOG_ENTRIES:
                return WebhookDeliveryResult(status="skipped", reason="log entry webhooks disabled")
        elif event_type.startswith("part_request"):
            if not config.DISCORD_WEBHOOKS_PARTS:
                return WebhookDeliveryResult(status="skipped", reason="parts webhooks disabled")

        # Fetch the object
        obj = _get_object(model_name, object_id)
        if obj is None:
            return WebhookDeliveryResult(
                status="error", reason=f"{model_name} {object_id} not found"
            )

        # Deliver webhook
        return _deliver_to_url(webhook_url, event_type, obj)
    finally:
        if token:
            reset_log_context(token)


# Registry of webhook models with their optimized query configurations
_WEBHOOK_MODEL_REGISTRY: dict[str, WebhookModelConfig] = {
    "ProblemReport": WebhookModelConfig(
        import_path="the_flip.apps.maintenance.models.ProblemReport",
        select_related=("machine",),
        prefetch_related=(),
    ),
    "LogEntry": WebhookModelConfig(
        import_path="the_flip.apps.maintenance.models.LogEntry",
        select_related=("machine", "problem_report"),
        prefetch_related=("maintainers", "maintainers__discord_link"),
    ),
    "PartRequest": WebhookModelConfig(
        import_path="the_flip.apps.parts.models.PartRequest",
        select_related=("machine", "requested_by__user", "requested_by__discord_link"),
        prefetch_related=(),
    ),
    "PartRequestUpdate": WebhookModelConfig(
        import_path="the_flip.apps.parts.models.PartRequestUpdate",
        select_related=("part_request__machine", "posted_by__user", "posted_by__discord_link"),
        prefetch_related=(),
    ),
}


def _get_model_class(model_name: str):
    """Get the model class for a model name, or None if unknown."""
    config = _WEBHOOK_MODEL_REGISTRY.get(model_name)
    if not config:
        logger.warning("discord_unknown_webhook_model", extra={"model_name": model_name})
        return None

    from importlib import import_module

    module_path, class_name = config.import_path.rsplit(".", 1)
    module = import_module(module_path)
    return getattr(module, class_name)


def _get_object(model_name: str, object_id: int):
    """Fetch the object by model name and ID with optimized related queries."""
    model_class = _get_model_class(model_name)
    if model_class is None:
        return None

    config = _WEBHOOK_MODEL_REGISTRY[model_name]

    # Build optimized query
    queryset = model_class.objects.all()
    if config.select_related:
        queryset = queryset.select_related(*config.select_related)
    if config.prefetch_related:
        queryset = queryset.prefetch_related(*config.prefetch_related)

    return queryset.filter(pk=object_id).first()


def _deliver_to_url(
    url: str,
    event_type: str,
    obj: ProblemReport | LogEntry | PartRequest | PartRequestUpdate,
) -> WebhookDeliveryResult:
    """Deliver a webhook to a URL."""
    from the_flip.apps.discord.formatters import format_discord_message

    try:
        payload = format_discord_message(event_type, obj)
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
