"""Tests for catalog app views and functionality."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from the_flip.apps.catalog.models import MachineInstance, MachineModel

User = get_user_model()


class MachineQuickCreateViewTests(TestCase):
    """Tests for the machine quick create view."""

    def setUp(self):
        """Set up test data for quick create view tests."""
        # Create an existing machine model for testing instance creation
        self.existing_model = MachineModel.objects.create(
            name="Existing Machine",
            manufacturer="Williams",
            year=1995,
            era=MachineModel.ERA_SS,
        )

        # Create staff user (maintainer)
        self.staff_user = User.objects.create_user(
            username="staffuser",
            password="testpass123",
            is_staff=True,
        )

        # Create regular user (non-staff)
        self.regular_user = User.objects.create_user(
            username="regularuser",
            password="testpass123",
            is_staff=False,
        )

        self.create_url = reverse("machine-quick-create")

    def test_create_view_requires_authentication(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get(self.create_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_create_view_requires_staff_permission(self):
        """Non-staff users should be denied access (403)."""
        self.client.login(username="regularuser", password="testpass123")
        response = self.client.get(self.create_url)
        self.assertEqual(response.status_code, 403)

    def test_create_view_accessible_to_staff(self):
        """Staff users should be able to access the create page."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.create_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "catalog/machine_quick_create.html")

    def test_create_view_shows_existing_models_in_dropdown(self):
        """Create page should show existing models in dropdown."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.create_url)

        # Should contain the existing model in the dropdown
        self.assertContains(response, "Existing Machine")
        self.assertContains(response, "Williams")

    def test_create_new_model_and_instance(self):
        """Should create both a new model and instance when model_name is provided."""
        self.client.login(username="staffuser", password="testpass123")

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
        self.assertEqual(new_model.created_by, self.staff_user)
        self.assertEqual(new_model.updated_by, self.staff_user)

        # Verify the new instance was created correctly
        new_instance = MachineInstance.objects.get(model=new_model)
        self.assertEqual(new_instance.operational_status, MachineInstance.STATUS_UNKNOWN)
        self.assertEqual(new_instance.location, "")
        self.assertEqual(new_instance.created_by, self.staff_user)
        self.assertEqual(new_instance.updated_by, self.staff_user)

    def test_create_new_model_without_manufacturer_and_year(self):
        """Should allow creating a model with only name (manufacturer and year optional)."""
        self.client.login(username="staffuser", password="testpass123")

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
        self.client.login(username="staffuser", password="testpass123")

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
        self.assertEqual(new_instance.location, "")

    def test_validation_error_no_model_or_model_name(self):
        """Should show validation error if neither model nor model_name provided."""
        self.client.login(username="staffuser", password="testpass123")

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
        self.client.login(username="staffuser", password="testpass123")

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
        self.client.login(username="staffuser", password="testpass123")

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
        self.client.login(username="staffuser", password="testpass123")

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
