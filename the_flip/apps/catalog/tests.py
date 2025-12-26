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


@tag("views")
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
class MachineCreateLandingViewTests(AccessControlTestCase):
    """Tests for the machine create landing page (model selection)."""

    def setUp(self):
        """Set up test data for landing view tests."""
        self.existing_model = create_machine_model(
            name="Existing Machine",
            manufacturer="Williams",
            year=1995,
            era=MachineModel.Era.SS,
        )
        self.maintainer_user = create_maintainer_user()
        self.regular_user = create_user()
        self.landing_url = reverse("machine-create-landing")

    def test_landing_view_requires_authentication(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get(self.landing_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_landing_view_requires_maintainer_access(self):
        """Non-maintainer users should be denied access (403)."""
        self.client.force_login(self.regular_user)
        response = self.client.get(self.landing_url)
        self.assertEqual(response.status_code, 403)

    def test_landing_view_accessible_to_maintainer(self):
        """Maintainer users should be able to access the landing page."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.landing_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "catalog/machine_create_landing.html")

    def test_landing_view_shows_existing_models_in_dropdown(self):
        """Landing page should show existing models in dropdown."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.landing_url)

        self.assertContains(response, "Existing Machine")
        self.assertContains(response, "Williams")

    def test_landing_view_has_create_new_model_as_default(self):
        """Landing page should have 'Create a new model' as the default option."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.landing_url)

        self.assertContains(response, "Create a new model")
        self.assertContains(response, 'value="new"')

    def test_landing_form_redirects_to_new_model(self):
        """Selecting 'new' should redirect to create new model page."""
        self.client.force_login(self.maintainer_user)
        response = self.client.post(self.landing_url, {"model_slug": "new"})

        self.assertRedirects(response, reverse("machine-create-model-does-not-exist"))

    def test_landing_form_redirects_to_existing_model(self):
        """Selecting an existing model should redirect to that model's page."""
        self.client.force_login(self.maintainer_user)
        response = self.client.post(self.landing_url, {"model_slug": self.existing_model.slug})

        expected_url = reverse(
            "machine-create-model-exists", kwargs={"model_slug": self.existing_model.slug}
        )
        self.assertRedirects(response, expected_url)

    def test_landing_form_404_for_invalid_slug(self):
        """Submitting an invalid slug should return 404."""
        self.client.force_login(self.maintainer_user)
        response = self.client.post(self.landing_url, {"model_slug": "nonexistent"})

        self.assertEqual(response.status_code, 404)


@tag("views")
class MachineCreateModelExistsViewTests(AccessControlTestCase):
    """Tests for creating an instance of an existing model."""

    def setUp(self):
        """Set up test data."""
        self.existing_model = create_machine_model(
            name="Existing Machine",
            manufacturer="Williams",
            year=1995,
            era=MachineModel.Era.SS,
        )
        self.maintainer_user = create_maintainer_user()
        self.regular_user = create_user()
        self.create_url = reverse(
            "machine-create-model-exists", kwargs={"model_slug": self.existing_model.slug}
        )

    def test_view_requires_authentication(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get(self.create_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_view_requires_maintainer_access(self):
        """Non-maintainer users should be denied access (403)."""
        self.client.force_login(self.regular_user)
        response = self.client.get(self.create_url)
        self.assertEqual(response.status_code, 403)

    def test_view_accessible_to_maintainer(self):
        """Maintainer users should be able to access the page."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.create_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "catalog/machine_create_model_exists.html")

    def test_view_shows_selected_model(self):
        """Page should show the selected model name."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.create_url)

        self.assertContains(response, "Existing Machine")
        self.assertContains(response, "Williams")

    def test_view_404_for_invalid_model_slug(self):
        """Should return 404 for non-existent model slug."""
        self.client.force_login(self.maintainer_user)
        url = reverse("machine-create-model-exists", kwargs={"model_slug": "nonexistent"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_create_instance_of_existing_model(self):
        """Should create an instance of the selected model."""
        self.client.force_login(self.maintainer_user)

        initial_model_count = MachineModel.objects.count()
        initial_instance_count = MachineInstance.objects.count()

        response = self.client.post(
            self.create_url,
            {"instance_name": "Machine #2"},
        )

        # Should redirect to machine detail page
        self.assertEqual(response.status_code, 302)

        # Should NOT create new model, only instance
        self.assertEqual(MachineModel.objects.count(), initial_model_count)
        self.assertEqual(MachineInstance.objects.count(), initial_instance_count + 1)

        # Verify the instance was created correctly
        new_instance = MachineInstance.objects.get(name="Machine #2")
        self.assertEqual(new_instance.model, self.existing_model)
        self.assertEqual(new_instance.operational_status, MachineInstance.OperationalStatus.UNKNOWN)
        self.assertIsNone(new_instance.location)
        self.assertEqual(new_instance.created_by, self.maintainer_user)
        self.assertEqual(new_instance.updated_by, self.maintainer_user)

    def test_validation_error_empty_instance_name(self):
        """Should require instance_name."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.create_url,
            {"instance_name": ""},
        )

        # Should stay on form page
        self.assertEqual(response.status_code, 200)
        # Check that form has errors
        self.assertTrue(response.context["form"].errors)

    def test_redirect_to_machine_detail(self):
        """Should redirect to the new machine's detail page."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.create_url,
            {"instance_name": "Redirect Test Instance"},
        )

        new_instance = MachineInstance.objects.get(name="Redirect Test Instance")
        expected_url = reverse("maintainer-machine-detail", kwargs={"slug": new_instance.slug})
        self.assertRedirects(response, expected_url)

    def test_shows_existing_instances_in_sidebar(self):
        """Should show existing instances of the model in the sidebar."""
        # Create an existing instance
        MachineInstance.objects.create(
            model=self.existing_model,
            name="First Instance",
            created_by=self.maintainer_user,
        )

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.create_url)

        self.assertContains(response, "First Instance")

    def test_validation_error_duplicate_name(self):
        """Should reject instance name that matches an existing machine's name."""
        # Create an existing instance with a specific name
        MachineInstance.objects.create(
            model=self.existing_model,
            name="Already Taken",
            created_by=self.maintainer_user,
        )

        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.create_url,
            {"instance_name": "Already Taken"},
        )

        # Should stay on form page with error
        self.assertEqual(response.status_code, 200)
        self.assertIn("instance_name", response.context["form"].errors)
        self.assertContains(response, "already exists")


@tag("views")
class MachineCreateModelDoesNotExistViewTests(AccessControlTestCase):
    """Tests for creating a new model and instance."""

    def setUp(self):
        """Set up test data."""
        self.maintainer_user = create_maintainer_user()
        self.regular_user = create_user()
        self.create_url = reverse("machine-create-model-does-not-exist")

    def test_view_requires_authentication(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get(self.create_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_view_requires_maintainer_access(self):
        """Non-maintainer users should be denied access (403)."""
        self.client.force_login(self.regular_user)
        response = self.client.get(self.create_url)
        self.assertEqual(response.status_code, 403)

    def test_view_accessible_to_maintainer(self):
        """Maintainer users should be able to access the page."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.create_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "catalog/machine_create_model_does_not_exist.html")

    def test_create_new_model_and_instance(self):
        """Should create both a new model and instance."""
        self.client.force_login(self.maintainer_user)

        initial_model_count = MachineModel.objects.count()
        initial_instance_count = MachineInstance.objects.count()

        response = self.client.post(
            self.create_url,
            {
                "name": "New Test Machine",
                "manufacturer": "Stern",
                "year": 2023,
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
        self.assertEqual(new_model.era, "")  # Era is optional, defaults to empty
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
                "name": "Minimal Machine",
                "manufacturer": "",
                "year": "",
            },
        )

        self.assertEqual(response.status_code, 302)

        # Should create the model even without manufacturer and year
        new_model = MachineModel.objects.get(name="Minimal Machine")
        self.assertEqual(new_model.manufacturer, "")
        self.assertIsNone(new_model.year)

    def test_validation_error_empty_name(self):
        """Should require model name."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.create_url,
            {
                "name": "",
                "manufacturer": "Stern",
                "year": 2023,
            },
        )

        # Should stay on form page
        self.assertEqual(response.status_code, 200)
        # Check that form has errors
        self.assertTrue(response.context["form"].errors)

    def test_redirect_to_machine_detail(self):
        """Should redirect to the new machine's detail page."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.create_url,
            {
                "name": "Redirect Test Model",
                "manufacturer": "Test",
                "year": 2024,
            },
        )

        new_instance = MachineInstance.objects.get(model__name="Redirect Test Model")
        expected_url = reverse("maintainer-machine-detail", kwargs={"slug": new_instance.slug})
        self.assertRedirects(response, expected_url)

    def test_success_message_displayed(self):
        """Should show success message after creating a machine."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.create_url,
            {
                "name": "Success Test Machine",
                "manufacturer": "Test Mfg",
                "year": 2024,
            },
            follow=True,
        )

        # Should show success message
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("Machine created!", str(messages[0]))

    def test_validation_error_duplicate_model_name(self):
        """Should reject model name that already exists."""
        # Create an existing model
        create_machine_model(
            name="Already Exists",
            manufacturer="Williams",
            year=1990,
            era=MachineModel.Era.SS,
        )

        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.create_url,
            {
                "name": "Already Exists",
                "manufacturer": "Stern",
                "year": 2024,
            },
        )

        # Should stay on form page with error
        self.assertEqual(response.status_code, 200)
        self.assertIn("name", response.context["form"].errors)
        self.assertContains(response, "already exists")


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


@tag("views")
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
        self.assertContains(response, self.machine.name)

    def test_public_detail_view_accessible(self):
        """Public detail view should be accessible to anonymous users."""
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "catalog/machine_detail_public.html")

    def test_public_detail_view_displays_machine_details(self):
        """Public detail view should display machine-specific details."""
        response = self.client.get(self.detail_url)
        self.assertContains(response, self.machine.name)
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

    # name field tests

    def test_name_required(self):
        """name field should be required."""
        from django.core.exceptions import ValidationError

        instance = MachineInstance(model=self.model, name="")

        with self.assertRaises(ValidationError) as context:
            instance.full_clean()

        self.assertIn("name", context.exception.message_dict)

    def test_name_whitespace_only_raises_validation_error(self):
        """Whitespace-only name should raise ValidationError.

        Bug: clean() strips name but doesn't check if result is empty.
        Submitting "   " becomes "" after stripping but passes validation.
        """
        from django.core.exceptions import ValidationError

        instance = MachineInstance(model=self.model, name="   ")

        with self.assertRaises(ValidationError) as context:
            instance.full_clean()

        self.assertIn("name", context.exception.message_dict)

    def test_name_collision_with_different_model_raises_validation_error(self):
        """Name collision across different models should raise ValidationError.

        Instance names must be unique globally, not just per-model.
        """
        from django.core.exceptions import ValidationError

        # Create existing machine with name "Godzilla"
        existing_model = MachineModel.objects.create(name="Existing Model")
        MachineInstance.objects.create(model=existing_model, name="Godzilla")

        # Try to create new instance with same name (but different model)
        new_model = MachineModel.objects.create(name="Godzilla")
        instance = MachineInstance(model=new_model, name="Godzilla")

        with self.assertRaises(ValidationError) as context:
            instance.full_clean()

        self.assertIn("name", context.exception.message_dict)

    def test_name_duplicate_raises_validation_error(self):
        """Duplicate name should raise ValidationError from clean()."""
        from django.core.exceptions import ValidationError

        MachineInstance.objects.create(model=self.model, name="Duplicate Name")
        duplicate = MachineInstance(model=self.model, name="Duplicate Name")

        with self.assertRaises(ValidationError) as context:
            duplicate.full_clean()

        self.assertIn("name", context.exception.message_dict)
        self.assertEqual(
            context.exception.message_dict["name"],
            ["A machine with this name already exists."],
        )

    def test_name_duplicate_case_insensitive(self):
        """Name uniqueness should be case-insensitive.

        "Godzilla" and "godzilla" should be treated as the same name.
        """
        from django.core.exceptions import ValidationError

        MachineInstance.objects.create(model=self.model, name="Godzilla")
        duplicate = MachineInstance(model=self.model, name="godzilla")

        with self.assertRaises(ValidationError) as context:
            duplicate.full_clean()

        self.assertIn("name", context.exception.message_dict)

    def test_name_stripped_on_clean(self):
        """name should be stripped of leading/trailing whitespace."""
        instance = MachineInstance(model=self.model, name="  Padded Name  ")
        instance.full_clean()

        self.assertEqual(instance.name, "Padded Name")

    # short_name tests

    def test_short_display_name_returns_short_name_if_set(self):
        """short_display_name should return short_name if set."""
        instance = MachineInstance.objects.create(
            model=self.model, name="Test Machine", short_name="Short"
        )
        self.assertEqual(instance.short_display_name, "Short")

    def test_short_display_name_returns_name_if_no_short_name(self):
        """short_display_name should return name if short_name is not set."""
        instance = MachineInstance.objects.create(model=self.model, name="Test Machine")
        self.assertEqual(instance.short_display_name, instance.name)

    def test_short_name_duplicate_raises_validation_error(self):
        """Duplicate short_name should raise ValidationError from clean()."""
        from django.core.exceptions import ValidationError

        create_machine(model=self.model, name="Machine 1", short_name="Duplicate")
        duplicate = MachineInstance(model=self.model, name="Machine 2", short_name="Duplicate")

        with self.assertRaises(ValidationError) as context:
            duplicate.full_clean()

        self.assertIn("short_name", context.exception.message_dict)
        self.assertEqual(
            context.exception.message_dict["short_name"],
            ["A machine with this short name already exists."],
        )

    def test_short_name_empty_string_converted_to_null(self):
        """Empty string short_name should be converted to NULL on save."""
        instance = create_machine(model=self.model, short_name="")

        instance.refresh_from_db()
        self.assertIsNone(instance.short_name)

    def test_short_name_whitespace_only_converted_to_null_via_clean(self):
        """Whitespace-only short_name should be converted to NULL via clean()."""
        instance = MachineInstance(model=self.model, name="Test Machine", short_name="   ")
        instance.full_clean()

        self.assertIsNone(instance.short_name)

    def test_short_name_whitespace_only_converted_to_null_via_save(self):
        """Whitespace-only short_name should be converted to NULL on save (without clean)."""
        instance = create_machine(model=self.model, short_name="   ")

        instance.refresh_from_db()
        self.assertIsNone(instance.short_name)

    def test_short_name_null_allows_multiple_machines(self):
        """Multiple machines with NULL short_name should be allowed."""
        instance1 = create_machine(model=self.model, name="Machine 1", short_name=None)
        instance2 = create_machine(model=self.model, name="Machine 2", short_name=None)
        instance3 = create_machine(model=self.model, name="Machine 3", short_name="")

        self.assertEqual(MachineInstance.objects.count(), 3)
        self.assertIsNone(instance1.short_name)
        self.assertIsNone(instance2.short_name)
        instance3.refresh_from_db()
        self.assertIsNone(instance3.short_name)

    def test_short_name_stripped_on_clean(self):
        """short_name should be stripped of leading/trailing whitespace."""
        instance = MachineInstance(model=self.model, name="Test Machine", short_name="  Padded  ")
        instance.full_clean()

        self.assertEqual(instance.short_name, "Padded")

    def test_slug_generation_on_create(self):
        """Should generate a slug from the name."""
        # Use model directly to test auto-generation (create_machine passes explicit slug)
        instance = MachineInstance.objects.create(model=self.model, name="Slug Test Machine")
        self.assertEqual(instance.slug, "slug-test-machine")

    def test_slug_generation_with_custom_name(self):
        """Should use the name for the slug."""
        # Use model directly to test auto-generation (create_machine passes explicit slug)
        instance = MachineInstance.objects.create(model=self.model, name="My Custom Game")
        self.assertEqual(instance.slug, "my-custom-game")

    def test_slug_uniqueness(self):
        """Should ensure slugs are unique for machine instances."""
        # Use model directly to test auto-generation (create_machine passes explicit slug)
        instance1 = MachineInstance.objects.create(model=self.model, name="Same Name")
        instance2 = MachineInstance.objects.create(model=self.model, name="Same Name #2")
        self.assertNotEqual(instance1.slug, instance2.slug)
        self.assertEqual(instance1.slug, "same-name")
        self.assertEqual(instance2.slug, "same-name-2")


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
