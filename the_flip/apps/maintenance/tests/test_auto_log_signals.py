"""Tests for automatic log entry creation signals.

These signals live in maintenance/signals.py and create LogEntry records
when machines are created or their status/location changes.
"""

from django.test import TestCase, tag

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import Location, MachineInstance
from the_flip.apps.core.test_utils import (
    create_machine,
    create_machine_model,
    create_maintainer_user,
    create_shared_terminal,
)
from the_flip.apps.maintenance.models import LogEntry


@tag("models")
class MachineCreationSignalTests(TestCase):
    """Tests for automatic log entry creation when machines are created."""

    def setUp(self):
        """Set up test data."""
        self.maintainer_user = create_maintainer_user()
        self.model = create_machine_model(name="Signal Test Model")

    def test_new_machine_creates_log_entry(self):
        """Creating a new machine should create an automatic log entry."""
        instance = MachineInstance.objects.create(
            model=self.model,
            name="New Signal Machine",
            created_by=self.maintainer_user,
        )

        log = LogEntry.objects.filter(machine=instance).first()
        self.assertIsNotNone(log)
        self.assertIn("New machine added", log.text)
        self.assertIn(instance.name, log.text)

    def test_new_machine_log_entry_has_created_by(self):
        """The auto log entry should have created_by set to the machine creator."""
        instance = MachineInstance.objects.create(
            model=self.model,
            name="Created By Machine",
            created_by=self.maintainer_user,
        )

        log = LogEntry.objects.filter(machine=instance).first()
        self.assertEqual(log.created_by, self.maintainer_user)

    def test_new_machine_log_entry_adds_maintainer_if_exists(self):
        """The auto log entry should add the creator as a maintainer if they have a profile."""
        maintainer = Maintainer.objects.get(user=self.maintainer_user)

        instance = MachineInstance.objects.create(
            model=self.model,
            name="Maintainer Profile Machine",
            created_by=self.maintainer_user,
        )

        log = LogEntry.objects.filter(machine=instance).first()
        self.assertIn(maintainer, log.maintainers.all())

    def test_new_machine_log_entry_no_maintainer_if_not_exists(self):
        """The auto log entry should not fail if the creator has no Maintainer profile."""
        # Remove the maintainer profile
        Maintainer.objects.filter(user=self.maintainer_user).delete()

        instance = MachineInstance.objects.create(
            model=self.model,
            name="No Profile Machine",
            created_by=self.maintainer_user,
        )

        log = LogEntry.objects.filter(machine=instance).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.maintainers.count(), 0)

    def test_new_machine_log_entry_no_created_by(self):
        """Creating a machine without created_by should still create log entry."""
        instance = MachineInstance.objects.create(
            model=self.model,
            name="No Creator Machine",
            created_by=None,
        )

        log = LogEntry.objects.filter(machine=instance).first()
        self.assertIsNotNone(log)
        self.assertIsNone(log.created_by)
        self.assertEqual(log.maintainers.count(), 0)

    def test_new_machine_log_entry_skips_shared_terminal(self):
        """The auto log entry should NOT add shared terminal as maintainer."""
        shared_terminal = create_shared_terminal()

        instance = MachineInstance.objects.create(
            model=self.model,
            name="Shared Terminal Machine",
            created_by=shared_terminal.user,
        )

        log = LogEntry.objects.filter(machine=instance).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.created_by, shared_terminal.user)
        # Shared terminal should NOT be added as maintainer
        self.assertEqual(log.maintainers.count(), 0)


@tag("models")
class StatusChangeSignalTests(TestCase):
    """Tests for automatic log entry creation when operational_status changes."""

    def setUp(self):
        self.maintainer_user = create_maintainer_user()
        self.machine = create_machine(operational_status=MachineInstance.OperationalStatus.GOOD)
        # create_machine sets _skip_auto_log; clear it so signals fire
        del self.machine._skip_auto_log  # type: ignore[attr-defined]
        # Clear any log entries from machine creation
        LogEntry.objects.filter(machine=self.machine).delete()

    def _log_count(self):
        return LogEntry.objects.filter(machine=self.machine).count()

    def test_status_change_creates_log_entry(self):
        """Changing operational_status should create a log entry."""
        self.machine.operational_status = MachineInstance.OperationalStatus.BROKEN
        self.machine.updated_by = self.maintainer_user
        self.machine.save()

        self.assertEqual(self._log_count(), 1)
        log = LogEntry.objects.filter(machine=self.machine).latest("occurred_at")
        self.assertIn("Status changed", log.text)
        self.assertIn("Good", log.text)
        self.assertIn("Broken", log.text)

    def test_status_change_log_has_arrow(self):
        """Status change log should show old → new."""
        self.machine.operational_status = MachineInstance.OperationalStatus.BROKEN
        self.machine.updated_by = self.maintainer_user
        self.machine.save()

        log = LogEntry.objects.filter(machine=self.machine).latest("occurred_at")
        self.assertIn("\u2192", log.text)

    def test_status_change_log_has_updated_by(self):
        """Status change log should record who made the change."""
        self.machine.operational_status = MachineInstance.OperationalStatus.BROKEN
        self.machine.updated_by = self.maintainer_user
        self.machine.save()

        log = LogEntry.objects.filter(machine=self.machine).latest("occurred_at")
        self.assertEqual(log.created_by, self.maintainer_user)

    def test_status_change_log_adds_maintainer(self):
        """Status change log should link maintainer profile."""
        maintainer = Maintainer.objects.get(user=self.maintainer_user)
        self.machine.operational_status = MachineInstance.OperationalStatus.BROKEN
        self.machine.updated_by = self.maintainer_user
        self.machine.save()

        log = LogEntry.objects.filter(machine=self.machine).latest("occurred_at")
        self.assertIn(maintainer, log.maintainers.all())

    def test_same_status_does_not_create_log(self):
        """Saving with the same status should not create a log entry."""
        self.machine.updated_by = self.maintainer_user
        self.machine.save()

        self.assertEqual(self._log_count(), 0)

    def test_skip_auto_log_suppresses_status_change(self):
        """_skip_auto_log should prevent log creation on status change."""
        self.machine.operational_status = MachineInstance.OperationalStatus.BROKEN
        self.machine._skip_auto_log = True  # type: ignore[attr-defined]
        self.machine.save()

        self.assertEqual(self._log_count(), 0)


@tag("models")
class LocationChangeSignalTests(TestCase):
    """Tests for automatic log entry creation when location changes."""

    def setUp(self):
        self.maintainer_user = create_maintainer_user()
        self.floor, _ = Location.objects.get_or_create(
            slug="floor", defaults={"name": "Floor", "sort_order": 1}
        )
        self.workshop, _ = Location.objects.get_or_create(
            slug="workshop", defaults={"name": "Workshop", "sort_order": 2}
        )
        self.machine = create_machine(location=self.workshop)
        # create_machine sets _skip_auto_log; clear it so signals fire
        del self.machine._skip_auto_log  # type: ignore[attr-defined]
        # Clear any log entries from machine creation
        LogEntry.objects.filter(machine=self.machine).delete()

    def _log_count(self):
        return LogEntry.objects.filter(machine=self.machine).count()

    def test_location_change_creates_log_entry(self):
        """Changing location should create a log entry."""
        self.machine.location = self.floor
        self.machine.updated_by = self.maintainer_user
        self.machine.save()

        self.assertEqual(self._log_count(), 1)
        log = LogEntry.objects.filter(machine=self.machine).latest("occurred_at")
        self.assertIn("moved to the floor", log.text)

    def test_location_change_to_non_floor(self):
        """Moving to non-floor location should show standard message."""
        # Move to floor first (suppressed)
        self.machine.location = self.floor
        self.machine._skip_auto_log = True  # type: ignore[attr-defined]
        self.machine.save()
        del self.machine._skip_auto_log  # type: ignore[attr-defined]

        self.machine.location = self.workshop
        self.machine.updated_by = self.maintainer_user
        self.machine.save()

        log = LogEntry.objects.filter(machine=self.machine).latest("occurred_at")
        self.assertIn("Location changed", log.text)
        self.assertIn("Floor", log.text)
        self.assertIn("Workshop", log.text)

    def test_location_change_to_floor_has_celebration(self):
        """Moving to floor should include celebration emoji."""
        self.machine.location = self.floor
        self.machine.updated_by = self.maintainer_user
        self.machine.save()

        log = LogEntry.objects.filter(machine=self.machine).latest("occurred_at")
        self.assertIn("\U0001f389", log.text)

    def test_location_change_log_has_updated_by(self):
        """Location change log should record who made the change."""
        self.machine.location = self.floor
        self.machine.updated_by = self.maintainer_user
        self.machine.save()

        log = LogEntry.objects.filter(machine=self.machine).latest("occurred_at")
        self.assertEqual(log.created_by, self.maintainer_user)

    def test_clearing_location_creates_log(self):
        """Setting location to None should create a log entry."""
        self.machine.location = None
        self.machine.updated_by = self.maintainer_user
        self.machine.save()

        self.assertEqual(self._log_count(), 1)
        log = LogEntry.objects.filter(machine=self.machine).latest("occurred_at")
        self.assertIn("No Location", log.text)

    def test_same_location_does_not_create_log(self):
        """Saving with the same location should not create a log entry."""
        self.machine.updated_by = self.maintainer_user
        self.machine.save()

        self.assertEqual(self._log_count(), 0)

    def test_skip_auto_log_suppresses_location_change(self):
        """_skip_auto_log should prevent log creation on location change."""
        self.machine.location = self.floor
        self.machine._skip_auto_log = True  # type: ignore[attr-defined]
        self.machine.save()

        self.assertEqual(self._log_count(), 0)
