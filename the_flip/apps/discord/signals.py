"""Django signals for Discord webhook triggers."""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from the_flip.apps.discord.tasks import dispatch_webhook
from the_flip.apps.maintenance.models import LogEntry, ProblemReport
from the_flip.apps.parts.models import PartRequest, PartRequestUpdate


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


@receiver(post_save, sender=PartRequest)
def part_request_saved(sender, instance, created, **kwargs):
    """Trigger webhook when a part request is created."""
    if created:
        dispatch_webhook(
            event_type="part_request_created",
            object_id=instance.pk,
            model_name="PartRequest",
        )


@receiver(pre_save, sender=PartRequest)
def part_request_status_changing(sender, instance, **kwargs):
    """Track status changes for webhook dispatch."""
    if instance.pk:
        try:
            old_instance = PartRequest.objects.get(pk=instance.pk)
            instance._old_status = old_instance.status
        except PartRequest.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=PartRequest)
def part_request_status_changed(sender, instance, created, **kwargs):
    """Trigger webhook when part request status changes (not on creation)."""
    if not created:
        old_status = getattr(instance, "_old_status", None)
        if old_status and old_status != instance.status:
            dispatch_webhook(
                event_type="part_request_status_changed",
                object_id=instance.pk,
                model_name="PartRequest",
            )


@receiver(post_save, sender=PartRequestUpdate)
def part_request_update_created(sender, instance, created, **kwargs):
    """Trigger webhook when a part request update is created."""
    if created:
        dispatch_webhook(
            event_type="part_request_update_created",
            object_id=instance.pk,
            model_name="PartRequestUpdate",
        )
