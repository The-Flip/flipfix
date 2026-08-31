"""Signals for the maintenance app.

Handles automatic log entry creation when machine status/location changes.
Uses FieldTracker on MachineInstance to detect changes without extra DB queries.
RecordReference cleanup is handled by register_reference_cleanup() in apps.py.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from flipfix.apps.accounts.models import Maintainer
from flipfix.apps.catalog.models import Location, MachineInstance

from . import auto_log
from .models import LogEntry

# =============================================================================
# Auto log entry signals — create LogEntry records for machine changes
# =============================================================================


@receiver(post_save, sender=MachineInstance)
def create_auto_log_entries(sender, instance, created, **kwargs):
    """Create automatic log entries for machine creation and field changes.

    Set instance._skip_auto_log = True to prevent auto log entry creation.
    Change detection uses MachineInstance.tracker (FieldTracker).
    """
    # Allow skipping auto-log creation (useful for tests and bulk imports)
    if getattr(instance, "_skip_auto_log", False):
        return

    # New machine created
    if created:
        log_entry = LogEntry.objects.create(
            machine=instance,
            text=auto_log.machine_added_text(instance.name),
            created_by=instance.created_by,
        )
        _add_maintainer_if_exists(log_entry, instance.created_by)
        return

    # Check for status change
    if instance.tracker.has_changed("operational_status"):
        previous_status = instance.tracker.previous("operational_status")
        if previous_status is not None:
            try:
                old_display = MachineInstance.OperationalStatus(previous_status).label
            except ValueError:
                old_display = previous_status
            new_display = instance.get_operational_status_display()
            log_entry = LogEntry.objects.create(
                machine=instance,
                text=auto_log.status_changed_text(old_display, new_display),
                created_by=instance.updated_by,
            )
            _add_maintainer_if_exists(log_entry, instance.updated_by)

    # Check for location change
    if instance.tracker.has_changed("location_id"):
        previous_location_id = instance.tracker.previous("location_id")
        old_location = None
        if previous_location_id:
            try:
                old_location = Location.objects.get(pk=previous_location_id)
            except Location.DoesNotExist:
                pass

        old_name = old_location.name if old_location else "No Location"
        new_name = instance.location.name if instance.location else "No Location"

        if old_name != new_name:
            # Celebrate moving to the floor!
            if instance.location and instance.location.slug == "floor":
                text = auto_log.moved_to_floor_text(instance.name)
            else:
                text = auto_log.location_changed_text(old_name, new_name)

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
