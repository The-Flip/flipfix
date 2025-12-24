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
    create_shared_terminal,
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
            era=MachineModel.Era.SS,
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
        self.assertEqual(new_instance.operational_status, MachineInstance.OperationalStatus.UNKNOWN)
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
        self.assertEqual(new_instance.operational_status, MachineInstance.OperationalStatus.UNKNOWN)
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


@tag("views", "public")
class PublicViewTests(TestCase):
    """Tests for public-facing catalog views."""

    def setUp(self):
        """Set up test data for public views."""
        self.machine = create_machine(slug="public-machine")
        self.list_url = reverse("public-machine-list")
        self.detail_url = reverse("public-machine-detail", kwargs={"slug": self.machine.slug})

    def test_public_list_view_accessible(self):
        """Public list view should be accessible to anonymous users."""
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "catalog/machine_list_public.html")

    def test_public_list_view_displays_machine(self):
        """Public list view should display visible machines."""
        response = self.client.get(self.list_url)
        self.assertContains(response, self.machine.display_name)

    def test_public_detail_view_accessible(self):
        """Public detail view should be accessible to anonymous users."""
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "catalog/machine_detail_public.html")

    def test_public_detail_view_displays_machine_details(self):
        """Public detail view should display machine-specific details."""
        response = self.client.get(self.detail_url)
        self.assertContains(response, self.machine.display_name)
        self.assertContains(response, self.machine.model.manufacturer)


@tag("models")
class MachineModelTests(TestCase):
    """Tests for the MachineModel model."""

    def test_slug_generation_on_create(self):
        """Should generate a slug from the name when a new model is created."""
        model = MachineModel.objects.create(name="Test Machine")
        self.assertEqual(model.slug, "test-machine")

    def test_slug_uniqueness(self):
        """Should ensure that generated slugs are unique."""
        # Create two models with names that slugify to the same value
        model1 = MachineModel.objects.create(name="My Machine")
        model2 = MachineModel.objects.create(name="My Machine--")
        self.assertEqual(model1.slug, "my-machine")
        self.assertNotEqual(model1.slug, model2.slug)
        self.assertEqual(model2.slug, "my-machine-2")


@tag("models")
class MachineInstanceModelTests(TestCase):
    """Tests for the MachineInstance model."""

    def setUp(self):
        """Set up a model for instance tests."""
        self.model = create_machine_model(name="Test Model")

    def test_display_name_property(self):
        """display_name property should return name_override if set, otherwise model name."""
        instance_with_override = MachineInstance.objects.create(
            model=self.model, name_override="Custom Name"
        )
        instance_without_override = MachineInstance.objects.create(model=self.model)

        self.assertEqual(instance_with_override.display_name, "Custom Name")
        self.assertEqual(instance_without_override.display_name, "Test Model")

    # name_override uniqueness tests

    def test_name_override_duplicate_raises_validation_error(self):
        """Duplicate name_override should raise ValidationError from clean()."""
        from django.core.exceptions import ValidationError

        MachineInstance.objects.create(model=self.model, name_override="Duplicate Name")
        duplicate = MachineInstance(model=self.model, name_override="Duplicate Name")

        with self.assertRaises(ValidationError) as context:
            duplicate.full_clean()

        self.assertIn("name_override", context.exception.message_dict)
        self.assertEqual(
            context.exception.message_dict["name_override"],
            ["A machine with this name already exists."],
        )

    def test_name_override_empty_string_converted_to_null(self):
        """Empty string name_override should be converted to NULL on save."""
        instance = MachineInstance.objects.create(model=self.model, name_override="")

        # Refresh from database to verify
        instance.refresh_from_db()
        self.assertIsNone(instance.name_override)

    def test_name_override_whitespace_only_converted_to_null_via_clean(self):
        """Whitespace-only name_override should be converted to NULL via clean()."""
        instance = MachineInstance(model=self.model, name_override="   ")
        instance.full_clean()

        self.assertIsNone(instance.name_override)

    def test_name_override_whitespace_only_converted_to_null_via_save(self):
        """Whitespace-only name_override should be converted to NULL on save (without clean)."""
        # This tests programmatic saves that bypass full_clean()
        instance = MachineInstance.objects.create(model=self.model, name_override="   ")

        instance.refresh_from_db()
        self.assertIsNone(instance.name_override)

    def test_name_override_null_allows_multiple_machines(self):
        """Multiple machines with NULL name_override should be allowed."""
        # This tests that the unique constraint doesn't conflict on NULLs
        instance1 = MachineInstance.objects.create(model=self.model, name_override=None)
        instance2 = MachineInstance.objects.create(model=self.model, name_override=None)
        instance3 = MachineInstance.objects.create(model=self.model, name_override="")

        # All should exist without error
        self.assertEqual(MachineInstance.objects.count(), 3)
        self.assertIsNone(instance1.name_override)
        self.assertIsNone(instance2.name_override)
        instance3.refresh_from_db()
        self.assertIsNone(instance3.name_override)

    def test_name_override_stripped_on_clean(self):
        """name_override should be stripped of leading/trailing whitespace."""
        instance = MachineInstance(model=self.model, name_override="  Padded Name  ")
        instance.full_clean()

        self.assertEqual(instance.name_override, "Padded Name")

    def test_slug_generation_on_create(self):
        """Should generate a slug from the display_name."""
        instance = MachineInstance.objects.create(model=self.model)
        self.assertEqual(instance.slug, "test-model")

    def test_slug_generation_with_name_override(self):
        """Should use the name_override for the slug if it exists."""
        instance = MachineInstance.objects.create(model=self.model, name_override="My Custom Game")
        self.assertEqual(instance.slug, "my-custom-game")

    def test_slug_uniqueness(self):
        """Should ensure slugs are unique for machine instances."""
        instance1 = MachineInstance.objects.create(model=self.model)
        instance2 = MachineInstance.objects.create(model=self.model)
        self.assertNotEqual(instance1.slug, instance2.slug)
        self.assertEqual(instance2.slug, "test-model-2")


@tag("models", "signals")
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
            created_by=self.maintainer_user,
        )

        log = LogEntry.objects.filter(machine=instance).first()
        self.assertIsNotNone(log)
        self.assertIn("New machine added", log.text)
        self.assertIn(instance.display_name, log.text)

    def test_new_machine_log_entry_has_created_by(self):
        """The auto log entry should have created_by set to the machine creator."""
        instance = MachineInstance.objects.create(
            model=self.model,
            created_by=self.maintainer_user,
        )

        log = LogEntry.objects.filter(machine=instance).first()
        self.assertEqual(log.created_by, self.maintainer_user)

    def test_new_machine_log_entry_adds_maintainer_if_exists(self):
        """The auto log entry should add the creator as a maintainer if they have a profile."""
        maintainer = Maintainer.objects.get(user=self.maintainer_user)

        instance = MachineInstance.objects.create(
            model=self.model,
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
            created_by=self.maintainer_user,
        )

        log = LogEntry.objects.filter(machine=instance).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.maintainers.count(), 0)

    def test_new_machine_log_entry_no_created_by(self):
        """Creating a machine without created_by should still create log entry."""
        instance = MachineInstance.objects.create(
            model=self.model,
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
            created_by=shared_terminal.user,
        )

        log = LogEntry.objects.filter(machine=instance).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.created_by, shared_terminal.user)
        # Shared terminal should NOT be added as maintainer
        self.assertEqual(log.maintainers.count(), 0)
