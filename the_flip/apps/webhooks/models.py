"""Webhook configuration models."""

from django.db import models

from the_flip.apps.core.models import TimeStampedModel


class WebhookEndpoint(TimeStampedModel):
    """A webhook endpoint that receives notifications."""

    # Event types that can trigger webhooks
    EVENT_PROBLEM_REPORT_CREATED = "problem_report_created"
    EVENT_LOG_ENTRY_CREATED = "log_entry_created"

    EVENT_CHOICES = [
        (EVENT_PROBLEM_REPORT_CREATED, "Problem Report Created"),
        (EVENT_LOG_ENTRY_CREATED, "Log Entry Created"),
    ]

    name = models.CharField(
        max_length=100,
        help_text="Display name for this webhook endpoint.",
    )
    url = models.URLField(
        max_length=500,
        help_text="The webhook URL to send notifications to.",
    )
    is_enabled = models.BooleanField(
        default=True,
        help_text="Whether this endpoint is active.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        status = "enabled" if self.is_enabled else "disabled"
        return f"{self.name} ({status})"


class WebhookEventSubscription(TimeStampedModel):
    """Links a webhook endpoint to the event types it should receive."""

    endpoint = models.ForeignKey(
        WebhookEndpoint,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    event_type = models.CharField(
        max_length=50,
        choices=WebhookEndpoint.EVENT_CHOICES,
    )
    is_enabled = models.BooleanField(
        default=True,
        help_text="Whether this event subscription is active.",
    )

    class Meta:
        unique_together = ["endpoint", "event_type"]
        ordering = ["event_type"]

    def __str__(self) -> str:
        return f"{self.endpoint.name} → {self.get_event_type_display()}"


class WebhookSettings(models.Model):
    """Singleton model for global webhook settings."""

    # Global master switch
    webhooks_enabled = models.BooleanField(
        default=True,
        help_text="Master switch to enable/disable all webhook notifications.",
    )

    # Per-event-type switches
    problem_reports_enabled = models.BooleanField(
        default=True,
        help_text="Enable webhooks for problem report events.",
    )
    log_entries_enabled = models.BooleanField(
        default=True,
        help_text="Enable webhooks for log entry events.",
    )

    class Meta:
        verbose_name = "Webhook Settings"
        verbose_name_plural = "Webhook Settings"

    def __str__(self) -> str:
        status = "enabled" if self.webhooks_enabled else "disabled"
        return f"Webhook Settings ({status})"

    def save(self, *args, **kwargs):
        # Ensure only one instance exists (singleton pattern)
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Prevent deletion of the singleton
        pass

    @classmethod
    def get_settings(cls) -> "WebhookSettings":
        """Get or create the singleton settings instance."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
