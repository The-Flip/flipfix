"""Tests for automatic log entry creation signals.

These signals live in maintenance/signals.py and create LogEntry records
when machines are created or their status/location changes.
"""

from django.test import TestCase, tag

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.core.test_utils import (
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
