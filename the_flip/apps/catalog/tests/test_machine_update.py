"""Tests for machine inline update views."""

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import Location, MachineInstance
from the_flip.apps.core.test_utils import (
    create_machine,
    create_maintainer_user,
    create_shared_terminal,
)
from the_flip.apps.maintenance.models import LogEntry


@tag("views")
class MachineInlineUpdateViewTests(TestCase):
    """Tests for inline machine field updates (status/location)."""

    def setUp(self):
        """Set up test data."""
        self.maintainer_user = create_maintainer_user()
        self.machine = create_machine(slug="test-machine")

        # Get or create locations
        self.floor, _ = Location.objects.get_or_create(
            slug="floor", defaults={"name": "Floor", "sort_order": 1}
        )
        self.workshop, _ = Location.objects.get_or_create(
            slug="workshop", defaults={"name": "Workshop", "sort_order": 2}
        )
        self.storage, _ = Location.objects.get_or_create(
            slug="storage", defaults={"name": "Storage", "sort_order": 3}
        )

        self.update_url = reverse("machine-inline-update", kwargs={"slug": self.machine.slug})

    def test_location_change_to_floor_creates_celebratory_log(self):
        """Moving to floor should create log entry with celebration emoji."""
        self.client.force_login(self.maintainer_user)
        self.machine.location = self.workshop
        self.machine.save()

        response = self.client.post(
            self.update_url, {"action": "update_location", "location": "floor"}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check celebration flag in response
        self.assertTrue(data.get("celebration"))

        # Check log entry exists with celebration emoji
        log = LogEntry.objects.filter(machine=self.machine).latest("created_at")
        self.assertIn("🎉", log.text)

    def test_location_change_to_workshop_creates_standard_log(self):
        """Moving to non-floor location should create standard log entry."""
        self.client.force_login(self.maintainer_user)
        self.machine.location = self.floor
        self.machine.save()

        response = self.client.post(
            self.update_url, {"action": "update_location", "location": "workshop"}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # No celebration flag
        self.assertFalse(data.get("celebration", False))

        # Log exists with location name, no celebration emoji
        log = LogEntry.objects.filter(machine=self.machine).latest("created_at")
        self.assertIn("Workshop", log.text)
        self.assertNotIn("🎉", log.text)

    def test_clearing_location_creates_log(self):
        """Clearing location should create a log entry."""
        self.client.force_login(self.maintainer_user)
        self.machine.location = self.floor
        self.machine.save()
        initial_log_count = LogEntry.objects.filter(machine=self.machine).count()

        response = self.client.post(self.update_url, {"action": "update_location", "location": ""})

        self.assertEqual(response.status_code, 200)

        # A new log entry should be created (not celebratory)
        self.assertEqual(
            LogEntry.objects.filter(machine=self.machine).count(), initial_log_count + 1
        )
        log = LogEntry.objects.filter(machine=self.machine).latest("created_at")
        self.assertNotIn("🎉", log.text)

    def test_location_noop_does_not_create_log(self):
        """Setting same location should not create a log entry."""
        self.client.force_login(self.maintainer_user)
        self.machine.location = self.floor
        self.machine.save()
        initial_log_count = LogEntry.objects.filter(machine=self.machine).count()

        response = self.client.post(
            self.update_url, {"action": "update_location", "location": "floor"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "noop")

        # No new log entry
        self.assertEqual(LogEntry.objects.filter(machine=self.machine).count(), initial_log_count)

    def test_location_change_log_linked_to_user(self):
        """Log entry should be created by the current user."""
        self.client.force_login(self.maintainer_user)

        self.client.post(self.update_url, {"action": "update_location", "location": "floor"})

        log = LogEntry.objects.filter(machine=self.machine).latest("created_at")
        self.assertEqual(log.created_by, self.maintainer_user)

    def test_status_change_adds_maintainer_if_exists(self):
        """Auto log entry should add user as maintainer if they have a Maintainer profile."""
        self.client.force_login(self.maintainer_user)
        # Get the Maintainer profile (created automatically for staff users)
        maintainer = Maintainer.objects.get(user=self.maintainer_user)

        self.machine.operational_status = MachineInstance.OperationalStatus.GOOD
        self.machine._skip_auto_log = True
        self.machine.save()

        self.client.post(
            self.update_url, {"action": "update_status", "operational_status": "broken"}
        )

        log = LogEntry.objects.filter(machine=self.machine).latest("created_at")
        self.assertEqual(log.created_by, self.maintainer_user)
        self.assertIn(maintainer, log.maintainers.all())

    def test_status_change_no_maintainer_if_not_exists(self):
        """Auto log entry should not fail if user has no Maintainer profile."""
        self.client.force_login(self.maintainer_user)
        # Ensure no Maintainer profile exists
        Maintainer.objects.filter(user=self.maintainer_user).delete()

        self.machine.operational_status = MachineInstance.OperationalStatus.GOOD
        self.machine._skip_auto_log = True
        self.machine.save()

        self.client.post(
            self.update_url, {"action": "update_status", "operational_status": "broken"}
        )

        log = LogEntry.objects.filter(machine=self.machine).latest("created_at")
        self.assertEqual(log.created_by, self.maintainer_user)
        self.assertEqual(log.maintainers.count(), 0)

    def test_status_change_skips_shared_terminal(self):
        """Auto log entry should NOT add shared terminal as maintainer."""
        shared_terminal = create_shared_terminal()
        self.client.force_login(shared_terminal.user)

        self.machine.operational_status = MachineInstance.OperationalStatus.GOOD
        self.machine._skip_auto_log = True
        self.machine.save()

        self.client.post(
            self.update_url, {"action": "update_status", "operational_status": "broken"}
        )

        log = LogEntry.objects.filter(machine=self.machine).latest("created_at")
        self.assertEqual(log.created_by, shared_terminal.user)
        # Shared terminal should NOT be added as maintainer
        self.assertEqual(log.maintainers.count(), 0)

    def test_location_change_skips_shared_terminal(self):
        """Auto log entry should NOT add shared terminal as maintainer for location changes."""
        shared_terminal = create_shared_terminal()
        self.client.force_login(shared_terminal.user)

        self.machine.location = self.workshop
        self.machine._skip_auto_log = True
        self.machine.save()

        self.client.post(self.update_url, {"action": "update_location", "location": "floor"})

        log = LogEntry.objects.filter(machine=self.machine).latest("created_at")
        self.assertEqual(log.created_by, shared_terminal.user)
        # Shared terminal should NOT be added as maintainer
        self.assertEqual(log.maintainers.count(), 0)
