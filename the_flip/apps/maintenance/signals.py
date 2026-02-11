"""Signals for the maintenance app.

Handles automatic log entry creation when machine status/location changes.
RecordReference cleanup is handled by register_reference_cleanup() in apps.py.
"""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import Location, MachineInstance

from .models import LogEntry

# =============================================================================
# Auto log entry signals — create LogEntry records for machine changes
# =============================================================================


@receiver(pre_save, sender=MachineInstance)
def capture_original_values(sender, instance, **kwargs):
    """Capture original field values before save for change detection."""
    if instance.pk:
        try:
            original = MachineInstance.objects.get(pk=instance.pk)
            instance._original_operational_status = original.operational_status
            instance._original_location_id = original.location_id
        except MachineInstance.DoesNotExist:
            instance._original_operational_status = None
            instance._original_location_id = None
    else:
        instance._original_operational_status = None
        instance._original_location_id = None


@receiver(post_save, sender=MachineInstance)
def create_auto_log_entries(sender, instance, created, **kwargs):
    """Create automatic log entries for machine creation and field changes.

    Set instance._skip_auto_log = True to prevent auto log entry creation.
    """
    # Allow skipping auto-log creation (useful for tests and bulk imports)
    if getattr(instance, "_skip_auto_log", False):
        return

    # New machine created
    if created:
        log_entry = LogEntry.objects.create(
            machine=instance,
            text=f"New machine added: {instance.name}",
            created_by=instance.created_by,
        )
        _add_maintainer_if_exists(log_entry, instance.created_by)
        return

    # Check for status change
    original_status = getattr(instance, "_original_operational_status", None)
    if original_status and original_status != instance.operational_status:
        try:
            old_display = MachineInstance.OperationalStatus(original_status).label
        except ValueError:
            old_display = original_status
        new_display = instance.get_operational_status_display()
        log_entry = LogEntry.objects.create(
            machine=instance,
            text=f"Status changed: {old_display} \u2192 {new_display}",
            created_by=instance.updated_by,
        )
        _add_maintainer_if_exists(log_entry, instance.updated_by)

    # Check for location change
    original_location_id = getattr(instance, "_original_location_id", None)
    if original_location_id != instance.location_id:
        old_location = None
        if original_location_id:
            try:
                old_location = Location.objects.get(pk=original_location_id)
            except Location.DoesNotExist:
                pass

        old_name = old_location.name if old_location else "No Location"
        new_name = instance.location.name if instance.location else "No Location"

        if old_name != new_name:
            # Celebrate moving to the floor!
            if instance.location and instance.location.slug == "floor":
                text = f"\U0001f389\U0001f38a {instance.name} has moved to the floor!"
            else:
                text = f"Location changed: {old_name} \u2192 {new_name}"

            log_entry = LogEntry.objects.create(
                machine=instance,
                text=text,
                created_by=instance.updated_by,
            )
            _add_maintainer_if_exists(log_entry, instance.updated_by)


def _add_maintainer_if_exists(log_entry, user):
    """Add the user as a maintainer on the log entry if they have a Maintainer profile.

    Skips shared terminal accounts since they don't represent a specific person.
    """
    if user is None:
        return

    try:
        maintainer = Maintainer.objects.get(user=user)
        if not maintainer.is_shared_account:
            log_entry.maintainers.add(maintainer)
    except Maintainer.DoesNotExist:
        pass
