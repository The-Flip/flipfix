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
from flipfix.apps.discord.webhook_handlers import DISCORD_GALLERY_MAX_PHOTOS
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
    :class:`PendingNotification` buffer keyed by the user who saved the record,
    and the periodic ``flush_pending_notifications`` task later posts one message
    per machine that person touched. Events with no signed-in user — visitor
    problem reports from the public QR flow — always post immediately.

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

    # Records the author marked as routine paperwork (an intake checklist, say)
    # are never announced, coalescing on or off.
    if not handler.should_announce(object_id):
        return

    if not config.DISCORD_NOTIFICATION_COALESCING_ENABLED:
        _enqueue_delivery(handler_name, object_id)
        return

    # Coalescing on: buffer by whoever saved the record, unless nobody was signed in.
    obj = handler.get_object(object_id)
    if obj is None:
        return
    actor = handler.get_submitting_user(obj)
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

# Most full posts one flush may produce. Grouping per machine means a session
# touching twenty machines would otherwise post twenty times; past this many the
# rest degrade to lines in the summary message.
MAX_RICH_POSTS_PER_FLUSH = 4


def flush_pending_notifications() -> WebhookDeliveryResult:
    """Post the Discord messages for every actor whose buffered events are due.

    Runs on the qcluster worker every minute (see ``ensure_scheduled_tasks``). An
    actor's un-sent events are "due" once the actor has been quiet for
    ``COALESCE_QUIET_PERIOD`` (a true debounce) or the oldest event has waited
    ``COALESCE_MAX_WAIT`` (a latency cap for continuously-active actors).

    One flush can produce several messages — see :func:`build_pending_posts` —
    and each is delivered and marked independently, so a failure partway through
    doesn't repost what already landed.

    Delivery is **at-least-once**. Each actor's due rows are selected under a
    short row lock (``select_for_update(skip_locked=True)``) that is released
    before the network call, so the Discord POST never runs inside a database
    transaction; rows are marked ``sent_at`` only after a successful post, so a
    failed delivery (or a crash mid-flight) simply retries next run. A crash
    between a successful POST and the ``sent_at`` write can repost a message —
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
        # order_by() clears the model's default ordering: a DISTINCT that also
        # selects buffered_at yields one row per event, not one per actor, and
        # the loop below would then handle the same actor several times.
        .order_by()
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

        posts, orphan_pks = build_pending_posts(rows)
        # Rows whose record has since been deleted can never be delivered;
        # consume them so they don't linger in the buffer forever.
        sent_pks = list(orphan_pks)
        for post in posts:
            # On a delivery error, leave that post's rows un-sent to retry next run.
            if _post_json(config.DISCORD_WEBHOOK_URL, post.payload).status == "success":
                sent_pks.extend(post.row_pks)
        if sent_pks:
            PendingNotification.objects.filter(pk__in=sent_pks, sent_at__isnull=True).update(
                sent_at=now
            )
            flushed += 1

    return WebhookDeliveryResult(status="success", reason=f"flushed {flushed} actor(s)")


@dataclass(frozen=True)
class PendingPost:
    """One Discord message built from buffered rows, with the rows it covers."""

    payload: dict
    row_pks: list[int]


# A record and the buffered row that asked for it to be announced.
Buffered = tuple["WebhookHandler", "Model", PendingNotification]


def build_pending_posts(
    rows: list[PendingNotification],
) -> tuple[list[PendingPost], list[int]]:
    """Turn one actor's due rows into the messages to post.

    Records are grouped by the machine they concern, because that is what makes
    a set of records one piece of work: fixing a machine, closing its report,
    marking it Good and moving it to the floor all belong in a single message.

    Each machine's group then goes one of two ways:

    * **Somebody wrote something** — a repair note, a problem report, a parts
      request. That becomes a full post with its body text and photos, and the
      rest of the group's records are listed underneath it.
    * **Nothing but recorded actions** — status flips, location moves. Those hold
      no content worth a post each, so every such group for this actor merges
      into one summary message grouped by action ("Moved to the floor: Comet,
      Cyclone, Star Trek").

    At most ``MAX_RICH_POSTS_PER_FLUSH`` full posts come out of one flush; the
    machines that miss the cut join the summary message. See
    :func:`_rank_by_written_content` for which ones those are.

    Returns the posts plus the row pks whose record no longer exists.
    """
    from flipfix.apps.discord.webhook_handlers import get_webhook_handler

    groups: dict[object, list[Buffered]] = {}
    orphan_pks: list[int] = []
    resolved_count = 0
    for row in rows:
        handler = get_webhook_handler(row.handler_name)
        obj = handler.get_object(row.object_id) if handler else None
        if handler is None or obj is None:  # unknown handler, or record deleted
            orphan_pks.append(row.pk)
            continue
        resolved_count += 1
        machine = handler.get_machine(obj)
        # Machine-less parts records share one group; they are their own work.
        groups.setdefault(machine.pk if machine is not None else None, []).append(
            (handler, obj, row)
        )

    if resolved_count == 0:
        return [], orphan_pks

    # A lone record is just itself — no summarising to do, so keep the full post
    # even when it is a bare status change.
    if resolved_count == 1:
        group = next(iter(groups.values()))
        return [_build_rich_post(group)], orphan_pks

    written: list[list[Buffered]] = []
    routine: list[Buffered] = []
    for group in groups.values():
        if any(handler.is_substantive(obj) for handler, obj, _ in group):
            written.append(group)
        else:
            routine.extend(group)

    # Beyond the cap, the machines with the least written about them give up
    # their own post and join the summary instead. Selection is by content but
    # delivery stays in the order the work happened.
    promoted = set(_rank_by_written_content(written)[:MAX_RICH_POSTS_PER_FLUSH])
    posts: list[PendingPost] = []
    for index, group in enumerate(written):
        if index in promoted:
            posts.append(_build_rich_post(group))
        else:
            routine.extend(group)

    if routine:
        posts.append(_build_sweep_post(routine))
    return posts, orphan_pks


def _rank_by_written_content(groups: list[list[Buffered]]) -> list[int]:
    """Order group indexes by how much a person actually wrote, most first.

    The cap has to drop somebody's machine from a full post to a summary line,
    and a summary line carries no body text at all. Dropping the *newest* work
    would throw away a long repair write-up to make room for a one-word note, so
    rank by the amount of hand-written text instead and let the shortest go.
    """

    def written_words(group: list[Buffered]) -> int:
        return sum(
            len(handler.get_summary_line(obj).split())
            for handler, obj, _ in group
            if handler.is_substantive(obj)
        )

    # Score once rather than inside the sort key: get_summary_line renders
    # markdown links. Ties fall back to the index, so equally-wordy machines keep
    # the order the work happened in.
    scored = [(written_words(group), index) for index, group in enumerate(groups)]
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [index for _, index in scored]


def _build_rich_post(group: list[Buffered]) -> PendingPost:
    """Render one machine's work as a full post led by what somebody wrote."""
    from flipfix.apps.discord.formatters import build_followup_line, get_base_url

    lead_index = next(
        (i for i, (handler, obj, _) in enumerate(group) if handler.is_substantive(obj)),
        0,
    )
    lead_handler, lead_obj, _ = group[lead_index]

    # The gallery is the session's photos, not just the lead record's, so a photo
    # attached to a follow-up entry isn't lost. Discord shows at most four.
    photos = list(lead_handler.get_photos(lead_obj))
    for index, (handler, obj, _) in enumerate(group):
        if index != lead_index:
            photos.extend(handler.get_photos(obj))

    base_url = get_base_url()
    followups = [
        build_followup_line(
            handler.get_summary_line(obj),
            base_url + handler.get_detail_url(obj) if handler.is_substantive(obj) else None,
        )
        for index, (handler, obj, _) in enumerate(group)
        if index != lead_index
    ]

    payload = lead_handler.format_webhook_message(
        lead_obj,
        followups=followups or None,
        photos=photos[:DISCORD_GALLERY_MAX_PHOTOS],
    )
    return PendingPost(payload=payload, row_pks=[row.pk for _, _, row in group])


def _build_sweep_post(routine: list[Buffered]) -> PendingPost:
    """Render a stretch of pure record-keeping as one message grouped by action."""
    from flipfix.apps.discord.formatters import build_sweep_message, get_actor_display_name

    sections: dict[str, list[str]] = {}
    for handler, obj, _ in routine:
        entries = sections.setdefault(handler.get_sweep_label(obj), [])
        entry = handler.get_sweep_entry(obj)
        if entry not in entries:  # the same machine flipped twice reads as noise
            entries.append(entry)

    first_handler, first_obj, _ = routine[0]
    actor = first_handler.get_submitting_user(first_obj)
    payload = build_sweep_message(
        actor_name=get_actor_display_name(actor) if actor is not None else "Unknown",
        sections=list(sections.items()),
        total=len(routine),
    )
    return PendingPost(payload=payload, row_pks=[row.pk for _, _, row in routine])


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
