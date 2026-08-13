"""Webhook handlers for posting records to Discord.

Each handler class encapsulates everything needed to post one record type
to Discord: signal registration, query optimization, and message formatting.

To add a new record type (e.g., wiki pages):
1. Create a new handler file in this package
2. Done. Auto-discovery imports all modules at startup.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from functools import partial
from typing import Any

from django.db import transaction
from django.db.models.signals import post_save

logger = logging.getLogger(__name__)

# Registry of webhook handlers, keyed by handler name (e.g., "log_entry")
_registry: dict[str, WebhookHandler] = {}

# Discord shows at most four images in an embed gallery.
DISCORD_GALLERY_MAX_PHOTOS = 4


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

    def should_announce(self, object_id: int) -> bool:
        """Whether the record wants announcing at all.

        Record types with an ``announce`` field let the author mark routine
        paperwork — an intake checklist pasted in as a problem report — as
        something the channel does not need to hear about. Types without the
        field always announce.
        """
        from django.core.exceptions import FieldDoesNotExist

        model_class = self.get_model_class()
        try:
            model_class._meta.get_field("announce")
        except FieldDoesNotExist:
            return True
        return (
            model_class.objects.filter(pk=object_id).values_list("announce", flat=True).first()
            is not False
        )

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

    def format_webhook_message(
        self,
        obj: Any,
        *,
        followups: list[str] | None = None,
        photos: list | None = None,
    ) -> dict:
        """Build the Discord webhook payload for this record.

        Args:
            obj: The record to render.
            followups: Extra lines appended below the attribution, describing the
                rest of the same work session (see ``build_discord_embed``).
            photos: Override the gallery, e.g. with photos gathered from every
                record in the session. ``None`` means use this record's own.
        """
        raise NotImplementedError

    def get_photos(self, obj: Any) -> list:
        """Return this record's gallery photos, in display order.

        Every notifiable record has a ``media`` related manager of
        :class:`~flipfix.apps.core.models.AbstractMedia` rows. Videos and photos
        that never got a thumbnail are skipped — Discord webhooks can only show
        images, and an embed without a usable URL renders as a broken box.
        """
        from flipfix.apps.core.models import AbstractMedia

        return list(
            obj.media.filter(media_type=AbstractMedia.MediaType.PHOTO)
            .filter(thumbnail_file__gt="")
            .order_by("display_order", "created_at")[:DISCORD_GALLERY_MAX_PHOTOS]
        )

    # --- Coalescing support (used by the debounced notification buffer) ---

    def get_submitting_user(self, obj: Any):
        """Return the User whose activity this record belongs to — the grouping key.

        Prefers who *saved* the record, which ``django-simple-history`` captures
        on the creation row, over the record's attribution field
        (``reported_by_user``/``requested_by``/``posted_by``). Attribution says
        who the record is *about*, and `core.attribution` leaves it null whenever
        somebody files on another person's behalf — which is how the great
        majority of records ended up looking anonymous to the coalescer.

        Falls back to attribution for records created outside a request (the
        Discord bot, management commands, tests), where there is no history user.

        Returns ``None`` only when neither is known — the public QR problem
        report flow. Those post immediately rather than being debounced.
        """
        creation = obj.history.filter(history_type="+").order_by("history_date").first()
        if creation is not None and creation.history_user is not None:
            return creation.history_user
        return self.get_attributed_user(obj)

    def get_attributed_user(self, obj: Any):
        """Return the User the record credits, or ``None``. See get_submitting_user."""
        return None

    def get_machine(self, obj: Any):
        """Return the MachineInstance this event concerns, or ``None``.

        Records are grouped into one message per machine, so this is what decides
        which records belong to the same piece of work.
        """
        return None

    def is_substantive(self, obj: Any) -> bool:
        """Whether a person wrote this, as opposed to Flipfix recording an action.

        A session containing something substantive is worth a full post — body
        text and photos — and everything else about that machine is folded into
        it as a one-line follow-up. A session of nothing but recorded actions
        collapses into a single summary message.
        """
        return True

    def get_summary_line(self, obj: Any) -> str:
        """Return a one-line plain-text summary of this record."""
        return self.display_name

    def get_sweep_label(self, obj: Any) -> str:
        """Return the action this record represents, e.g. "Marked Good".

        Records sharing a label are listed together in the summary message.
        """
        return self.display_name

    def get_sweep_entry(self, obj: Any) -> str:
        """Return what the action was performed on, e.g. a machine name."""
        machine = self.get_machine(obj)
        return machine.short_display_name if machine is not None else self.display_name


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
            from flipfix.apps.discord.tasks import dispatch_webhook

            transaction.on_commit(
                partial(
                    dispatch_webhook,
                    handler_name=handler.name,
                    object_id=instance.pk,
                )
            )

    return signal_handler


def discover() -> None:
    """Auto-discover and import all handler modules in this package.

    Imports every module in webhook_handlers/ to trigger their module-level
    register() calls. Called from DiscordConfig.ready().
    """
    for module_info in pkgutil.iter_modules(__path__):
        importlib.import_module(f".{module_info.name}", __package__)
