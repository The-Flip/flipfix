"""Django signals for webhook triggers."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from the_flip.apps.maintenance.models import LogEntry, ProblemReport
from the_flip.apps.webhooks.tasks import dispatch_webhook


@receiver(post_save, sender=ProblemReport)
def problem_report_saved(sender, instance, created, **kwargs):
    """Trigger webhook when a problem report is created or status changes."""
    if created:
        dispatch_webhook(
            event_type="problem_report_created",
            object_id=instance.pk,
            model_name="ProblemReport",
        )
    else:
        # Check if status was updated by looking at update_fields
        update_fields = kwargs.get("update_fields")
        if update_fields and "status" in update_fields:
            if instance.status == ProblemReport.STATUS_CLOSED:
                dispatch_webhook(
                    event_type="problem_report_closed",
                    object_id=instance.pk,
                    model_name="ProblemReport",
                )
            elif instance.status == ProblemReport.STATUS_OPEN:
                dispatch_webhook(
                    event_type="problem_report_reopened",
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
