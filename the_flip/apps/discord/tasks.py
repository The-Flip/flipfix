"""Webhook delivery tasks using Django Q."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import requests
from django_q.tasks import async_task

from the_flip.logging import bind_log_context, current_log_context, reset_log_context

if TYPE_CHECKING:
    from the_flip.apps.discord.models import WebhookEndpoint
    from the_flip.apps.maintenance.models import LogEntry, ProblemReport

logger = logging.getLogger(__name__)


def dispatch_webhook(event_type: str, object_id: int, model_name: str) -> None:
    """Queue a webhook delivery task for the given event.

    This function is called synchronously from signal handlers and
    enqueues the actual webhook delivery to run asynchronously.
    """
    async_task(
        "the_flip.apps.discord.tasks.deliver_webhooks",
        event_type,
        object_id,
        model_name,
        current_log_context(),
        timeout=60,
    )


def deliver_webhooks(
    event_type: str, object_id: int, model_name: str, log_context: dict | None = None
) -> dict:
    """Deliver webhooks for a given event to all subscribed endpoints.

    This runs asynchronously via Django Q.
    """
    from constance import config

    from the_flip.apps.discord.models import WebhookEventSubscription

    token = bind_log_context(**log_context) if log_context else None

    try:
        # Check global settings
        if not config.DISCORD_WEBHOOKS_ENABLED:
            return {"status": "skipped", "reason": "webhooks globally disabled"}

        # Check per-event-type settings
        if event_type.startswith("problem_report"):
            if not config.DISCORD_WEBHOOKS_PROBLEM_REPORTS:
                return {"status": "skipped", "reason": "problem report webhooks disabled"}
        elif event_type == "log_entry_created":
            if not config.DISCORD_WEBHOOKS_LOG_ENTRIES:
                return {"status": "skipped", "reason": "log entry webhooks disabled"}
        elif event_type.startswith("part_request"):
            if not config.DISCORD_WEBHOOKS_PARTS:
                return {"status": "skipped", "reason": "parts webhooks disabled"}

        # Get all enabled subscriptions for this event type
        subscriptions = WebhookEventSubscription.objects.filter(
            event_type=event_type,
            is_enabled=True,
            endpoint__is_enabled=True,
        ).select_related("endpoint")

        if not subscriptions.exists():
            return {"status": "skipped", "reason": "no subscribed endpoints"}

        # Fetch the object
        obj = _get_object(model_name, object_id)
        if obj is None:
            return {"status": "error", "reason": f"{model_name} {object_id} not found"}

        # Deliver to each endpoint
        results = []
        for subscription in subscriptions:
            result = _deliver_to_endpoint(subscription.endpoint, event_type, obj)
            results.append(result)

        return {"status": "completed", "results": results}
    finally:
        if token:
            reset_log_context(token)


# Registry of webhook models with their optimized query configurations
# Maps model name -> (import_path, select_related, prefetch_related)
_WEBHOOK_MODEL_REGISTRY: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    "ProblemReport": (
        "the_flip.apps.maintenance.models.ProblemReport",
        ("machine",),
        (),
    ),
    "LogEntry": (
        "the_flip.apps.maintenance.models.LogEntry",
        ("machine", "problem_report"),
        ("maintainers", "maintainers__discord_link"),
    ),
    "PartRequest": (
        "the_flip.apps.parts.models.PartRequest",
        ("machine", "requested_by__user", "requested_by__discord_link"),
        (),
    ),
    "PartRequestUpdate": (
        "the_flip.apps.parts.models.PartRequestUpdate",
        ("part_request__machine", "posted_by__user", "posted_by__discord_link"),
        (),
    ),
}


def _get_object(model_name: str, object_id: int):
    """Fetch the object by model name and ID with optimized related queries."""
    if model_name not in _WEBHOOK_MODEL_REGISTRY:
        logger.warning("Unknown webhook model: %s", model_name)
        return None

    import_path, select_related, prefetch_related = _WEBHOOK_MODEL_REGISTRY[model_name]

    # Lazy import the model class
    from importlib import import_module

    module_path, class_name = import_path.rsplit(".", 1)
    module = import_module(module_path)
    model_class = getattr(module, class_name)

    # Build optimized query
    queryset = model_class.objects.all()
    if select_related:
        queryset = queryset.select_related(*select_related)
    if prefetch_related:
        queryset = queryset.prefetch_related(*prefetch_related)

    return queryset.filter(pk=object_id).first()


def _deliver_to_endpoint(
    endpoint: WebhookEndpoint,
    event_type: str,
    obj: ProblemReport | LogEntry,
) -> dict:
    """Deliver a webhook to a single endpoint."""
    from the_flip.apps.discord.formatters import format_discord_message

    try:
        payload = format_discord_message(event_type, obj)
        response = requests.post(
            endpoint.url,
            json=payload,
            timeout=10,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        return {
            "endpoint": endpoint.name,
            "status": "success",
            "status_code": response.status_code,
        }
    except requests.RequestException as e:
        logger.warning(
            "Webhook delivery failed for endpoint %s: %s",
            endpoint.name,
            str(e),
        )
        return {
            "endpoint": endpoint.name,
            "status": "error",
            "error": str(e),
        }


def send_test_webhook(endpoint_id: int, event_type: str) -> dict:
    """Send a test webhook to a specific endpoint.

    This is called directly (not via async_task) from the admin UI
    so the user gets immediate feedback.
    """
    from the_flip.apps.discord.formatters import format_test_message
    from the_flip.apps.discord.models import WebhookEndpoint

    try:
        endpoint = WebhookEndpoint.objects.get(pk=endpoint_id)
    except WebhookEndpoint.DoesNotExist:
        return {"status": "error", "error": "Endpoint not found"}

    try:
        payload = format_test_message(event_type)
        response = requests.post(
            endpoint.url,
            json=payload,
            timeout=10,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        return {
            "status": "success",
            "message": f"Test message sent to {endpoint.name}",
        }
    except requests.RequestException as e:
        return {
            "status": "error",
            "error": str(e),
        }
