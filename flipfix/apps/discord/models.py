"""Discord integration models."""

from django.conf import settings
from django.db import models
from django.db.models import Model

from flipfix.apps.core.models import TimeStampedMixin


class DiscordUserLink(TimeStampedMixin):
    """Links a Discord user to a Maintainer account."""

    discord_user_id = models.CharField(
        max_length=50,
        unique=True,
        help_text="Discord user snowflake ID.",
    )
    discord_username = models.CharField(
        max_length=100,
        help_text="Discord username (e.g., 'deanmoses').",
    )
    discord_display_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Discord display name (e.g., 'Dean Moses').",
    )
    discord_avatar_url = models.URLField(
        max_length=500,
        blank=True,
        help_text="URL to the user's Discord avatar.",
    )
    maintainer = models.OneToOneField(
        "accounts.Maintainer",
        on_delete=models.CASCADE,
        related_name="discord_link",
        help_text="The maintainer this Discord user is linked to.",
    )

    class Meta:
        ordering = ["discord_username"]
        verbose_name = "Discord user link"
        verbose_name_plural = "Discord user links"

    def __str__(self) -> str:
        return f"{self.discord_display_name or self.discord_username} → {self.maintainer}"


class DiscordMessageMapping(models.Model):
    """Tracks which Discord messages have been processed to prevent duplicates.

    Uses Django's ContentType framework to link to any model type.
    One Discord message can create multiple records (e.g., Claude suggests
    problems on different machines), so discord_message_id is not unique.
    """

    discord_message_id = models.CharField(
        max_length=50,
        help_text="Discord message snowflake ID.",
    )
    content_type = models.ForeignKey(
        "contenttypes.ContentType",
        on_delete=models.CASCADE,
    )
    object_id = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Discord message mapping"
        verbose_name_plural = "Discord message mappings"
        indexes = [
            models.Index(fields=["discord_message_id"]),
            # For was_created_from_discord() lookups
            models.Index(fields=["content_type", "object_id"]),
        ]
        constraints = [
            # Prevent duplicate mappings for the same record
            models.UniqueConstraint(
                fields=["discord_message_id", "content_type", "object_id"],
                name="unique_discord_message_record",
            ),
        ]

    def __str__(self) -> str:
        return f"Discord {self.discord_message_id} → {self.content_type.model} #{self.object_id}"

    @classmethod
    def is_processed(cls, message_id: str) -> bool:
        """Check if a Discord message has already been processed."""
        return cls.objects.filter(discord_message_id=str(message_id)).exists()

    @classmethod
    def mark_processed(cls, message_id: str, obj: Model) -> "DiscordMessageMapping":
        """Mark a Discord message as processed, linking to the created object."""
        from django.contrib.contenttypes.models import ContentType

        content_type = ContentType.objects.get_for_model(obj)
        return cls.objects.create(
            discord_message_id=str(message_id),
            content_type=content_type,
            object_id=obj.pk,
        )

    @classmethod
    def was_created_from_discord(cls, obj: Model) -> bool:
        """Check if a record was created via the Discord bot.

        Used by webhook signals to skip notifying Discord about records
        that originated from Discord (avoiding redundant notifications).
        """
        from django.contrib.contenttypes.models import ContentType

        content_type = ContentType.objects.get_for_model(obj)
        return cls.objects.filter(content_type=content_type, object_id=obj.pk).exists()

    @classmethod
    def has_mapping_for(cls, model_class: type, object_id: int) -> bool:
        """Check if a mapping exists without fetching the full object.

        More efficient than was_created_from_discord() when you only have
        the model class and ID (e.g., in dispatch_webhook before queueing).
        """
        from django.contrib.contenttypes.models import ContentType

        content_type = ContentType.objects.get_for_model(model_class)
        return cls.objects.filter(content_type=content_type, object_id=object_id).exists()


class PendingNotification(models.Model):
    """A buffered outbound notification awaiting a debounced flush.

    When ``DISCORD_NOTIFICATION_COALESCING_ENABLED`` is on, each record creation
    that would fire a real-time webhook is appended here instead of being
    delivered immediately. The periodic ``flush_pending_notifications`` task
    groups an actor's un-sent rows into a single Discord message once the actor
    has gone quiet (or a max-wait cap is reached). See ``discord/tasks.py``.

    Anonymous events (e.g. visitor problem reports, which have no actor) are
    never buffered — they post immediately — so ``actor`` is always set here.
    """

    handler_name = models.CharField(
        max_length=50,
        help_text="Webhook handler name, e.g. 'log_entry' (see webhook_handlers/).",
    )
    object_id = models.PositiveIntegerField(
        help_text="Primary key of the record to notify about.",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="+",
        help_text="The user whose activity this event belongs to; the grouping key.",
    )
    buffered_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the event was buffered (≈ when the record was created).",
    )
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this event was flushed to Discord; null while pending.",
    )

    class Meta:
        ordering = ["buffered_at"]
        verbose_name = "Pending notification"
        verbose_name_plural = "Pending notifications"
        indexes = [
            # Drives the flush scan: unsent rows, grouped by actor, oldest first.
            models.Index(fields=["sent_at", "actor", "buffered_at"]),
        ]

    def __str__(self) -> str:
        state = "sent" if self.sent_at else "pending"
        return f"{self.handler_name} #{self.object_id} for user {self.actor_id} ({state})"
