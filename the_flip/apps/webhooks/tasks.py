"""Webhook delivery tasks using Django Q."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import requests
from django_q.tasks import async_task

if TYPE_CHECKING:
    from the_flip.apps.maintenance.models import LogEntry, ProblemReport
    from the_flip.apps.webhooks.models import WebhookEndpoint

logger = logging.getLogger(__name__)


def dispatch_webhook(event_type: str, object_id: int, model_name: str) -> None:
    """Queue a webhook delivery task for the given event.

    This function is called synchronously from signal handlers and
    enqueues the actual webhook delivery to run asynchronously.
    """
    async_task(
        "the_flip.apps.webhooks.tasks.deliver_webhooks",
        event_type,
        object_id,
        model_name,
        timeout=60,
    )


def deliver_webhooks(event_type: str, object_id: int, model_name: str) -> dict:
    """Deliver webhooks for a given event to all subscribed endpoints.

    This runs asynchronously via Django Q.
    """
    from the_flip.apps.webhooks.models import (
        WebhookEventSubscription,
        WebhookSettings,
    )

    # Check global settings
    webhook_settings = WebhookSettings.get_settings()
    if not webhook_settings.webhooks_enabled:
        return {"status": "skipped", "reason": "webhooks globally disabled"}

    # Check per-event-type settings
    if event_type.startswith("problem_report"):
        if not webhook_settings.problem_reports_enabled:
            return {"status": "skipped", "reason": "problem report webhooks disabled"}
    elif event_type == "log_entry_created":
        if not webhook_settings.log_entries_enabled:
            return {"status": "skipped", "reason": "log entry webhooks disabled"}
    elif event_type.startswith("part_request"):
        if not webhook_settings.parts_enabled:
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


def _get_object(model_name: str, object_id: int):
    """Fetch the object by model name and ID."""
    if model_name == "ProblemReport":
        from the_flip.apps.maintenance.models import ProblemReport

        return ProblemReport.objects.select_related("machine").filter(pk=object_id).first()
    elif model_name == "LogEntry":
        from the_flip.apps.maintenance.models import LogEntry

        return (
            LogEntry.objects.select_related("machine", "problem_report")
            .prefetch_related("maintainers")
            .filter(pk=object_id)
            .first()
        )
    elif model_name == "PartRequest":
        from the_flip.apps.parts.models import PartRequest

        return (
            PartRequest.objects.select_related("machine", "requested_by__user")
            .filter(pk=object_id)
            .first()
        )
    elif model_name == "PartRequestUpdate":
        from the_flip.apps.parts.models import PartRequestUpdate

        return (
            PartRequestUpdate.objects.select_related("part_request__machine", "posted_by__user")
            .filter(pk=object_id)
            .first()
        )
    return None


def _deliver_to_endpoint(
    endpoint: WebhookEndpoint,
    event_type: str,
    obj: ProblemReport | LogEntry,
) -> dict:
    """Deliver a webhook to a single endpoint."""
    from the_flip.apps.webhooks.formatters import format_discord_message

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
    from the_flip.apps.webhooks.formatters import format_test_message
    from the_flip.apps.webhooks.models import WebhookEndpoint

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
