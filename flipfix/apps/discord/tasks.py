"""Webhook delivery tasks using Django Q."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

import requests
from django.db import transaction
from django.utils import timezone
from django_q.tasks import async_task

from flipfix.apps.discord.models import DiscordMessageMapping, PendingNotification
from flipfix.logging import bind_log_context, current_log_context, reset_log_context

if TYPE_CHECKING:
    from django.db.models import Model

    from flipfix.apps.discord.webhook_handlers import WebhookHandler

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WebhookDeliveryResult:
    """Result of a webhook delivery attempt."""

    status: str  # "success", "error", "skipped"
    reason: str | None = None  # Why skipped or errored
    status_code: int | None = None  # HTTP status code on success


def dispatch_webhook(handler_name: str, object_id: int) -> None:
    """Route a would-fire webhook event: buffer it for coalescing, or deliver now.

    Called synchronously from signal handlers (via ``transaction.on_commit``).

    When ``DISCORD_NOTIFICATION_COALESCING_ENABLED`` is off, behaves as before:
    enqueue an immediate async delivery. When on, the event is appended to the
    :class:`PendingNotification` buffer keyed by the acting user, and the periodic
    ``flush_pending_notifications`` task later posts one combined message per
    actor. Anonymous events (no actor — e.g. visitor problem reports) always post
    immediately rather than debounce.

    Checks webhooks are enabled first to avoid buffering/queueing needlessly.
    """
    from constance import config

    if not config.DISCORD_WEBHOOKS_ENABLED or not config.DISCORD_WEBHOOK_URL:
        return

    from flipfix.apps.discord.webhook_handlers import get_webhook_handler

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

    if not config.DISCORD_NOTIFICATION_COALESCING_ENABLED:
        _enqueue_delivery(handler_name, object_id)
        return

    # Coalescing on: buffer by actor, unless the event is anonymous.
    obj = handler.get_object(object_id)
    if obj is None:
        return
    actor = handler.get_actor_user(obj)
    if actor is None:
        _enqueue_delivery(handler_name, object_id)
        return

    PendingNotification.objects.create(
        handler_name=handler_name,
        object_id=object_id,
        actor=actor,
    )


def _enqueue_delivery(handler_name: str, object_id: int) -> None:
    """Enqueue an immediate single-record webhook delivery on the worker."""
    async_task(
        "flipfix.apps.discord.tasks.deliver_webhook",
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
        from flipfix.apps.discord.webhook_handlers import get_webhook_handler

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


def _post_json(url: str, payload: dict) -> WebhookDeliveryResult:
    """POST a prepared payload to a Discord webhook URL."""
    try:
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


def _deliver_to_url(
    url: str,
    handler: WebhookHandler,
    obj: Model,
) -> WebhookDeliveryResult:
    """Deliver a single record's webhook to a URL."""
    return _post_json(url, handler.format_webhook_message(obj))


# ---------------------------------------------------------------------------
# Coalescing — debounced flush of the PendingNotification buffer
# ---------------------------------------------------------------------------

# Flush an actor's buffered events once they have been quiet this long...
COALESCE_QUIET_PERIOD = timedelta(minutes=5)
# ...but never hold a still-active actor's events longer than this cap.
COALESCE_MAX_WAIT = timedelta(minutes=15)


def flush_pending_notifications() -> WebhookDeliveryResult:
    """Post one combined Discord message per actor whose buffered events are due.

    Runs on the qcluster worker every minute (see ``ensure_scheduled_tasks``). An
    actor's un-sent events are "due" once the actor has been quiet for
    ``COALESCE_QUIET_PERIOD`` (a true debounce) or the oldest event has waited
    ``COALESCE_MAX_WAIT`` (a latency cap for continuously-active actors).

    Delivery is **at-least-once**. Each actor's due rows are selected under a
    short row lock (``select_for_update(skip_locked=True)``) that is released
    before the network call, so the Discord POST never runs inside a database
    transaction; rows are marked ``sent_at`` only after a successful post, so a
    failed delivery (or a crash mid-flight) simply retries next run. A crash
    between a successful POST and the ``sent_at`` write can repost a digest —
    preferred here to dropping a maintainer's activity summary.
    """
    from constance import config

    if not config.DISCORD_WEBHOOK_URL:
        return WebhookDeliveryResult(status="skipped", reason="no webhook URL configured")
    if not config.DISCORD_WEBHOOKS_ENABLED:
        return WebhookDeliveryResult(status="skipped", reason="webhooks globally disabled")

    now = timezone.now()
    actor_ids = list(
        PendingNotification.objects.filter(sent_at__isnull=True)
        .values_list("actor_id", flat=True)
        .distinct()
    )

    flushed = 0
    for actor_id in actor_ids:
        # Select the actor's due rows under a brief lock, then release it — the
        # HTTP POST below must not hold a transaction/connection open.
        with transaction.atomic():
            rows = list(
                PendingNotification.objects.select_for_update(skip_locked=True)
                .filter(sent_at__isnull=True, actor_id=actor_id)
                .order_by("buffered_at")
            )
            if not rows:
                continue
            quiet = now - rows[-1].buffered_at >= COALESCE_QUIET_PERIOD
            capped = now - rows[0].buffered_at >= COALESCE_MAX_WAIT
            if not (quiet or capped):
                rows = []
        if not rows:
            continue

        result = _deliver_pending(config.DISCORD_WEBHOOK_URL, rows)
        # "empty" means every referenced record has since vanished; consume the
        # rows anyway so they don't linger. On a delivery error, leave them
        # un-sent to retry next run.
        if result.status in ("success", "empty"):
            PendingNotification.objects.filter(
                pk__in=[r.pk for r in rows], sent_at__isnull=True
            ).update(sent_at=now)
            flushed += 1

    return WebhookDeliveryResult(status="success", reason=f"flushed {flushed} actor(s)")


def _deliver_pending(url: str, rows: list[PendingNotification]) -> WebhookDeliveryResult:
    """Deliver a single actor's buffered rows as one message.

    A single surviving event keeps its rich per-record embed (with photos); two
    or more collapse into a compact per-machine digest.
    """
    from flipfix.apps.discord.webhook_handlers import get_webhook_handler

    deliverables: list[tuple[WebhookHandler, Model]] = []
    for row in rows:
        handler = get_webhook_handler(row.handler_name)
        if handler is None:
            continue
        obj = handler.get_object(row.object_id)
        if obj is None:  # record deleted before flush
            continue
        deliverables.append((handler, obj))

    if not deliverables:
        return WebhookDeliveryResult(status="empty")
    if len(deliverables) == 1:
        handler, obj = deliverables[0]
        return _deliver_to_url(url, handler, obj)

    return _post_json(url, _build_combined_payload(deliverables))


def _build_combined_payload(deliverables: list[tuple[WebhookHandler, Model]]) -> dict:
    """Group an actor's events by machine and render one combined digest payload."""
    from flipfix.apps.discord.formatters import (
        build_actor_digest,
        get_actor_display_name,
        get_base_url,
    )

    base_url = get_base_url()
    sections: dict[str, list[tuple[str, str, str]]] = {}
    for handler, obj in deliverables:
        machine = handler.get_machine(obj)
        label = machine.short_display_name if machine is not None else "Parts (no machine)"
        url = base_url + handler.get_detail_url(obj)
        sections.setdefault(label, []).append((handler.emoji, handler.get_digest_text(obj), url))

    # All rows share one actor; derive the display name from the first record.
    first_handler, first_obj = deliverables[0]
    actor = first_handler.get_actor_user(first_obj)
    actor_name = get_actor_display_name(actor) if actor is not None else "Unknown"

    return build_actor_digest(
        actor_name=actor_name,
        sections=list(sections.items()),
        total=len(deliverables),
    )


DISCORD_CONTENT_LIMIT = 2000


def _fit_discord_content(body: str, link_line: str) -> str:
    """Join the digest body and its landing-page link within Discord's 2000-char
    ``content`` cap, truncating the body (but keeping the link) if it overflows."""
    footer = f"\n\n{link_line}"
    budget = DISCORD_CONTENT_LIMIT - len(footer)
    if len(body) > budget:
        body = body[: budget - 1].rstrip() + "…"
    return body + footer


def post_daily_maintenance_report() -> WebhookDeliveryResult:
    """Build the daily maintenance digest and post it to the Discord webhook.

    Runs on the qcluster worker via a daily Schedule (see the
    ``ensure_scheduled_tasks`` management command). The Discord bot is read-only,
    so posting goes through the webhook; the content is the compact emoji-digest
    markdown plus a link to the full landing page.
    """
    from constance import config
    from django.conf import settings
    from django.urls import reverse

    from flipfix.apps.maintenance.reports import build_report, render_markdown

    webhook_url = config.DISCORD_WEBHOOK_URL
    if not webhook_url:
        return WebhookDeliveryResult(status="skipped", reason="no webhook URL configured")
    if not config.DISCORD_WEBHOOKS_ENABLED:
        return WebhookDeliveryResult(status="skipped", reason="webhooks globally disabled")

    board_url = settings.SITE_URL.rstrip("/") + reverse("daily-maintenance-report")
    # Angle brackets suppress Discord's link-preview embed card.
    content = _fit_discord_content(render_markdown(build_report()), f"🔗 Full board: <{board_url}>")
    try:
        response = requests.post(
            webhook_url,
            json={"content": content},
            timeout=10,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        return WebhookDeliveryResult(status="success", status_code=response.status_code)
    except requests.RequestException as e:
        logger.warning("daily_report_webhook_failed", extra={"error": str(e)})
        return WebhookDeliveryResult(status="error", reason=str(e))


def send_test_webhook(event_type: str) -> dict:
    """Send a test webhook to the configured URL.

    This is called directly (not via async_task) from the admin UI
    so the user gets immediate feedback.
    """
    from constance import config

    from flipfix.apps.discord.formatters import format_test_message

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
