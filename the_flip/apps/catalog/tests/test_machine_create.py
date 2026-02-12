"""Tests for machine creation views."""

from django.test import tag
from django.urls import reverse

from the_flip.apps.catalog.models import MachineInstance, MachineModel
from the_flip.apps.core.test_utils import (
    AccessControlTestCase,
    create_machine_model,
    create_maintainer_user,
    create_user,
)


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
class MachineCreateTemplateEdgeCaseTests(AccessControlTestCase):
    """Edge case tests for machine creation templates."""

    def setUp(self):
        """Set up test data."""
        self.maintainer_user = create_maintainer_user()
        self.landing_url = reverse("machine-create-landing")

    def test_landing_page_with_many_models(self):
        """Landing page should handle a large number of existing models."""
        # Create multiple models
        for i in range(10):
            create_machine_model(
                name=f"Test Machine {i}",
                manufacturer="Test Mfg",
                year=1990 + i,
                era=MachineModel.Era.SS,
            )

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.landing_url)
        self.assertEqual(response.status_code, 200)
        # Should contain all models in dropdown
        for i in range(10):
            self.assertContains(response, f"Test Machine {i}")

    def test_landing_page_with_no_existing_models(self):
        """Landing page should work when no models exist yet."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.landing_url)
        self.assertEqual(response.status_code, 200)
        # Should still show "Create a new model" option
        self.assertContains(response, "Create a new model")

    def test_model_exists_view_shows_model_details(self):
        """Model exists view should display model manufacturer and year."""
        model = create_machine_model(
            name="Test Model",
            manufacturer="Williams",
            year=1995,
            era=MachineModel.Era.SS,
        )
        self.client.force_login(self.maintainer_user)
        url = reverse("machine-create-model-exists", kwargs={"model_slug": model.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Williams")
        self.assertContains(response, "Test Model")

    def test_model_exists_view_with_existing_instances(self):
        """Model exists view should show existing instances in sidebar."""
        model = create_machine_model(name="Popular Model", era=MachineModel.Era.SS)
        # Create multiple instances
        machine1 = create_machine(slug="instance-1", model=model)
        machine2 = create_machine(slug="instance-2", model=model)

        self.client.force_login(self.maintainer_user)
        url = reverse("machine-create-model-exists", kwargs={"model_slug": model.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, machine1.name)
        self.assertContains(response, machine2.name)

    def test_create_page_cancel_button_present(self):
        """Create pages should have cancel buttons."""
        self.client.force_login(self.maintainer_user)
        # Test landing page has navigation back
        response = self.client.get(self.landing_url)
        self.assertEqual(response.status_code, 200)

    def test_create_model_does_not_exist_breadcrumbs(self):
        """Create new model page should have proper breadcrumbs."""
        self.client.force_login(self.maintainer_user)
        url = reverse("machine-create-model-does-not-exist")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Should have breadcrumb navigation
        self.assertContains(response, "Machines")