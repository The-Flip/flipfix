"""Tests for catalog app views and functionality."""

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import Location, MachineInstance, MachineModel
from the_flip.apps.core.test_utils import (
    AccessControlTestCase,
    create_machine,
    create_machine_model,
    create_maintainer_user,
    create_user,
)
from the_flip.apps.maintenance.models import LogEntry


@tag("views", "access-control")
class MaintainerMachineViewsAccessTests(AccessControlTestCase):
    """Tests for maintainer machine views access control."""

    def setUp(self):
        """Set up test data."""
        self.maintainer_user = create_maintainer_user()
        self.regular_user = create_user()
        self.machine = create_machine(slug="test-machine")

        self.list_url = reverse("maintainer-machine-list")
        self.detail_url = reverse("maintainer-machine-detail", kwargs={"slug": self.machine.slug})

    # MachineListView tests

    def test_list_view_requires_authentication(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_list_view_requires_maintainer_access(self):
        """Non-maintainer users should be denied access (403)."""
        self.client.force_login(self.regular_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    def test_list_view_accessible_to_maintainer(self):
        """Maintainer users should be able to access the list page."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)

    # MachineDetailViewForMaintainers tests

    def test_detail_view_requires_authentication(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_detail_view_requires_maintainer_access(self):
        """Non-maintainer users should be denied access (403)."""
        self.client.force_login(self.regular_user)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 403)

    def test_detail_view_accessible_to_maintainer(self):
        """Maintainer users should be able to access the detail page."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)


@tag("views")
class MachineQuickCreateViewTests(AccessControlTestCase):
    """Tests for the machine quick create view."""

    def setUp(self):
        """Set up test data for quick create view tests."""
        # Create an existing machine model for testing instance creation
        self.existing_model = create_machine_model(
            name="Existing Machine",
            manufacturer="Williams",
            year=1995,
            era=MachineModel.ERA_SS,
        )

        # Create maintainer user
        self.maintainer_user = create_maintainer_user()

        # Create regular user (non-staff)
        self.regular_user = create_user()

        self.create_url = reverse("machine-quick-create")

    def test_create_view_requires_authentication(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get(self.create_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_create_view_requires_staff_permission(self):
        """Non-staff users should be denied access (403)."""
        self.client.force_login(self.regular_user)
        response = self.client.get(self.create_url)
        self.assertEqual(response.status_code, 403)

    def test_create_view_accessible_to_staff(self):
        """Staff users should be able to access the create page."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.create_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "catalog/machine_quick_create.html")

    def test_create_view_shows_existing_models_in_dropdown(self):
        """Create page should show existing models in dropdown."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.create_url)

        # Should contain the existing model in the dropdown
        self.assertContains(response, "Existing Machine")
        self.assertContains(response, "Williams")

    def test_create_new_model_and_instance(self):
        """Should create both a new model and instance when model_name is provided."""
        self.client.force_login(self.maintainer_user)

        initial_model_count = MachineModel.objects.count()
        initial_instance_count = MachineInstance.objects.count()

        response = self.client.post(
            self.create_url,
            {
                "model": "",  # Empty = create new model
                "model_name": "New Test Machine",
                "manufacturer": "Stern",
                "year": 2023,
                "name_override": "",
            },
        )

        # Should redirect to machine detail page
        self.assertEqual(response.status_code, 302)

        # Should create new model and instance
        self.assertEqual(MachineModel.objects.count(), initial_model_count + 1)
        self.assertEqual(MachineInstance.objects.count(), initial_instance_count + 1)

        # Verify the new model was created correctly
        new_model = MachineModel.objects.get(name="New Test Machine")
        self.assertEqual(new_model.manufacturer, "Stern")
        self.assertEqual(new_model.year, 2023)
        self.assertEqual(new_model.created_by, self.maintainer_user)
        self.assertEqual(new_model.updated_by, self.maintainer_user)

        # Verify the new instance was created correctly
        new_instance = MachineInstance.objects.get(model=new_model)
        self.assertEqual(new_instance.operational_status, MachineInstance.STATUS_UNKNOWN)
        self.assertIsNone(new_instance.location)
        self.assertEqual(new_instance.created_by, self.maintainer_user)
        self.assertEqual(new_instance.updated_by, self.maintainer_user)

    def test_create_new_model_without_manufacturer_and_year(self):
        """Should allow creating a model with only name (manufacturer and year optional)."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.create_url,
            {
                "model": "",
                "model_name": "Minimal Machine",
                "manufacturer": "",
                "year": "",
                "name_override": "",
            },
        )

        self.assertEqual(response.status_code, 302)

        # Should create the model even without manufacturer and year
        new_model = MachineModel.objects.get(name="Minimal Machine")
        self.assertEqual(new_model.manufacturer, "")
        self.assertIsNone(new_model.year)

    def test_create_instance_of_existing_model(self):
        """Should create an instance of an existing model with name_override."""
        self.client.force_login(self.maintainer_user)

        initial_model_count = MachineModel.objects.count()
        initial_instance_count = MachineInstance.objects.count()

        response = self.client.post(
            self.create_url,
            {
                "model": self.existing_model.pk,
                "model_name": "",
                "manufacturer": "",
                "year": "",
                "name_override": "Machine #2",
            },
        )

        # Should redirect to machine detail page
        self.assertEqual(response.status_code, 302)

        # Should NOT create new model, only instance
        self.assertEqual(MachineModel.objects.count(), initial_model_count)
        self.assertEqual(MachineInstance.objects.count(), initial_instance_count + 1)

        # Verify the instance was created with the existing model
        new_instance = MachineInstance.objects.get(name_override="Machine #2")
        self.assertEqual(new_instance.model, self.existing_model)
        self.assertEqual(new_instance.operational_status, MachineInstance.STATUS_UNKNOWN)
        self.assertIsNone(new_instance.location)

    def test_validation_error_no_model_or_model_name(self):
        """Should show validation error if neither model nor model_name provided."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.create_url,
            {
                "model": "",
                "model_name": "",
                "manufacturer": "",
                "year": "",
                "name_override": "",
            },
        )

        # Should stay on form page
        self.assertEqual(response.status_code, 200)

        # Should show validation error
        self.assertFormError(
            response.context["form"],
            None,
            "Please either select an existing model or provide a name for a new model.",
        )

    def test_validation_error_existing_model_without_name_override(self):
        """Should require name_override when selecting an existing model."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.create_url,
            {
                "model": self.existing_model.pk,
                "model_name": "",
                "manufacturer": "",
                "year": "",
                "name_override": "",  # Missing required name_override
            },
        )

        # Should stay on form page
        self.assertEqual(response.status_code, 200)

        # Should show validation error
        self.assertFormError(
            response.context["form"],
            None,
            "When selecting an existing model, you must provide a unique name for this specific machine.",
        )

    def test_success_message_displayed(self):
        """Should show success message after creating a machine."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.create_url,
            {
                "model": "",
                "model_name": "Success Test Machine",
                "manufacturer": "Test Mfg",
                "year": 2024,
                "name_override": "",
            },
            follow=True,
        )

        # Should show success message
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("Machine created!", str(messages[0]))
        self.assertIn("edit the machine", str(messages[0]))
        self.assertIn("edit the model", str(messages[0]))

    def test_redirect_to_machine_detail(self):
        """Should redirect to the new machine's detail page after creation."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.create_url,
            {
                "model": "",
                "model_name": "Redirect Test",
                "manufacturer": "Test",
                "year": 2024,
                "name_override": "",
            },
        )

        # Get the created instance
        new_instance = MachineInstance.objects.get(model__name="Redirect Test")
        expected_url = reverse("maintainer-machine-detail", kwargs={"slug": new_instance.slug})

        # Should redirect to the instance detail page
        self.assertRedirects(response, expected_url)


@tag("views")
class MachineInlineUpdateViewTests(TestCase):
    """Tests for inline machine field updates (status/location)."""

    def setUp(self):
        """Set up test data."""
        self.maintainer_user = create_maintainer_user()
        self.regular_user = create_user()
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

        self.machine.operational_status = MachineInstance.STATUS_GOOD
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

        self.machine.operational_status = MachineInstance.STATUS_GOOD
        self.machine._skip_auto_log = True
        self.machine.save()

        self.client.post(
            self.update_url, {"action": "update_status", "operational_status": "broken"}
        )

        log = LogEntry.objects.filter(machine=self.machine).latest("created_at")
        self.assertEqual(log.created_by, self.maintainer_user)
        self.assertEqual(log.maintainers.count(), 0)


@tag("views")
class MachineActivitySearchTests(TestCase):
    """Tests for machine activity feed search including free-text name fields."""

    def setUp(self):
        self.maintainer_user = create_maintainer_user()
        self.machine = create_machine(slug="test-machine")
        self.detail_url = reverse("maintainer-machine-detail", kwargs={"slug": self.machine.slug})

    def test_search_finds_log_entry_by_maintainer_names(self):
        """Activity search should find log entries by free-text maintainer names."""
        from the_flip.apps.core.test_utils import create_log_entry

        create_log_entry(
            machine=self.machine,
            text="Replaced flipper",
            maintainer_names="Wandering Willie",
        )

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.detail_url, {"q": "Wandering"})

        self.assertContains(response, "Replaced flipper")

    def test_search_finds_problem_report_by_reporter_name(self):
        """Activity search should find problem reports by free-text reporter name."""
        from the_flip.apps.core.test_utils import create_problem_report

        create_problem_report(
            machine=self.machine,
            description="Lights flickering",
            reported_by_name="Visiting Vera",
        )

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.detail_url, {"q": "Visiting"})

        self.assertContains(response, "Lights flickering")

    def test_search_finds_part_request_by_requester_name(self):
        """Activity search should find part requests by free-text requester name."""
        from constance.test import override_config

        from the_flip.apps.parts.models import PartRequest

        PartRequest.objects.create(
            machine=self.machine,
            text="Need new rubber rings",
            requested_by_name="Requisitioning Ralph",
        )

        self.client.force_login(self.maintainer_user)
        with override_config(PARTS_ENABLED=True):
            response = self.client.get(self.detail_url, {"q": "Requisitioning"})

        self.assertContains(response, "Need new rubber rings")

    def test_search_finds_part_update_by_poster_name(self):
        """Activity search should find part request updates by free-text poster name."""
        from constance.test import override_config

        from the_flip.apps.parts.models import PartRequest, PartRequestUpdate

        part_request = PartRequest.objects.create(
            machine=self.machine,
            text="Flipper coil",
        )
        PartRequestUpdate.objects.create(
            part_request=part_request,
            text="Ordered from Marco",
            posted_by_name="Updating Ursula",
        )

        self.client.force_login(self.maintainer_user)
        with override_config(PARTS_ENABLED=True):
            response = self.client.get(self.detail_url, {"q": "Updating"})

        self.assertContains(response, "Ordered from Marco")

    def test_search_finds_problem_report_by_log_entry_maintainer_names(self):
        """Activity search should find problem reports by their log entry's free-text maintainer names."""
        from the_flip.apps.core.test_utils import create_log_entry, create_problem_report

        report = create_problem_report(
            machine=self.machine,
            description="Ball stuck in gutter",
        )
        create_log_entry(
            machine=self.machine,
            problem_report=report,
            text="Cleared the ball",
            maintainer_names="Wandering Willie",
        )

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.detail_url, {"q": "Wandering"})

        self.assertContains(response, "Ball stuck in gutter")

    def test_search_finds_log_entry_by_maintainer_fk(self):
        """Activity search should find log entries by FK maintainer name."""
        from the_flip.apps.accounts.models import Maintainer
        from the_flip.apps.core.test_utils import create_log_entry

        maintainer = Maintainer.objects.get(user=self.maintainer_user)
        log = create_log_entry(
            machine=self.machine,
            text="Fixed the flipper",
        )
        log.maintainers.add(maintainer)

        self.client.force_login(self.maintainer_user)
        # Search by maintainer's first name
        response = self.client.get(self.detail_url, {"q": self.maintainer_user.first_name})

        self.assertContains(response, "Fixed the flipper")
