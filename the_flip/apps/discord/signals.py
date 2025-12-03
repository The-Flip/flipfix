"""Django signals for Discord webhook triggers."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from the_flip.apps.discord.tasks import dispatch_webhook
from the_flip.apps.maintenance.models import LogEntry, ProblemReport


@receiver(post_save, sender=ProblemReport)
def problem_report_saved(sender, instance, created, **kwargs):
    """Trigger webhook when a problem report is created."""
    # Note: Closing/reopening problem reports creates log entries,
    # which trigger log_entry_created webhooks. No separate events needed.
    if created:
        dispatch_webhook(
            event_type="problem_report_created",
            object_id=instance.pk,
            model_name="ProblemReport",
        )


@receiver(post_save, sender=LogEntry)
def log_entry_created(sender, instance, created, **kwargs):
    """Trigger webhook when a log entry is created."""
    if created:
        dispatch_webhook(
            event_type="log_entry_created",
            object_id=instance.pk,
            model_name="LogEntry",
        )
