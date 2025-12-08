"""Discord integration models for webhooks and bot."""

from django.db import models

from the_flip.apps.core.models import TimeStampedModel

# =============================================================================
# Discord Bot Models (inbound message processing)
# =============================================================================


class DiscordChannel(TimeStampedModel):
    """A Discord channel the bot listens to for messages."""

    channel_id = models.CharField(
        max_length=50,
        unique=True,
        help_text="Discord channel snowflake ID.",
    )
    name = models.CharField(
        max_length=100,
        help_text="Display name for this channel (for admin reference).",
    )
    is_enabled = models.BooleanField(
        default=True,
        help_text="Whether to listen to this channel.",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Discord channel"
        verbose_name_plural = "Discord channels"

    def __str__(self) -> str:
        status = "enabled" if self.is_enabled else "disabled"
        return f"{self.name} ({status})"


class DiscordUserLink(TimeStampedModel):
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
    """

    discord_message_id = models.CharField(
        max_length=50,
        unique=True,
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
        ]

    def __str__(self) -> str:
        return f"Discord {self.discord_message_id} → {self.content_type.model} #{self.object_id}"

    @classmethod
    def is_processed(cls, message_id: str) -> bool:
        """Check if a Discord message has already been processed."""
        return cls.objects.filter(discord_message_id=str(message_id)).exists()

    @classmethod
    def mark_processed(cls, message_id: str, obj) -> "DiscordMessageMapping":
        """Mark a Discord message as processed, linking to the created object."""
        from django.contrib.contenttypes.models import ContentType

        content_type = ContentType.objects.get_for_model(obj)
        return cls.objects.create(
            discord_message_id=str(message_id),
            content_type=content_type,
            object_id=obj.pk,
        )
