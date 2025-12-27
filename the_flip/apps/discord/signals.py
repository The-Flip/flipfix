"""Django signals for Discord webhook triggers."""

from functools import partial

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from the_flip.apps.discord.tasks import dispatch_webhook
from the_flip.apps.maintenance.models import LogEntry, ProblemReport
from the_flip.apps.parts.models import PartRequest, PartRequestUpdate


@receiver(post_save, sender=ProblemReport)
def problem_report_saved(sender, instance, created, **kwargs):
    """Trigger webhook when a problem report is created.

    Uses transaction.on_commit to ensure webhook fires after the transaction
    commits, so the record exists when the worker processes it.
    """
    # Note: Closing/reopening problem reports creates log entries,
    # which trigger log_entry_created webhooks. No separate events needed.
    if created:
        transaction.on_commit(
            partial(
                dispatch_webhook,
                event_type="problem_report_created",
                object_id=instance.pk,
                model_name="ProblemReport",
            )
        )


@receiver(post_save, sender=LogEntry)
def log_entry_created(sender, instance, created, **kwargs):
    """Trigger webhook when a log entry is created.

    Uses transaction.on_commit to ensure webhook fires after the entire
    request transaction commits, including any media attachments saved
    after the log entry itself.
    """
    if created:
        transaction.on_commit(
            partial(
                dispatch_webhook,
                event_type="log_entry_created",
                object_id=instance.pk,
                model_name="LogEntry",
            )
        )


@receiver(post_save, sender=PartRequest)
def part_request_saved(sender, instance, created, **kwargs):
    """Trigger webhook when a part request is created.

    Uses transaction.on_commit to ensure webhook fires after the transaction
    commits, including any media attachments saved after the part request.
    """
    if created:
        transaction.on_commit(
            partial(
                dispatch_webhook,
                event_type="part_request_created",
                object_id=instance.pk,
                model_name="PartRequest",
            )
        )


@receiver(post_save, sender=PartRequestUpdate)
def part_request_update_created(sender, instance, created, **kwargs):
    """Trigger webhook when a part request update is created.

    Uses transaction.on_commit to ensure webhook fires after the transaction
    commits, including any media attachments saved after the update.
    """
    if created:
        transaction.on_commit(
            partial(
                dispatch_webhook,
                event_type="part_request_update_created",
                object_id=instance.pk,
                model_name="PartRequestUpdate",
            )
        )
