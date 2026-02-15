"""Tests for machine model update view."""

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    create_machine,
    create_maintainer_user,
    create_user,
)


@tag("views")
class MachineModelUpdateViewTests(SuppressRequestLogsMixin, TestCase):
    """Tests for MachineModelUpdateView (edit model details)."""

    def setUp(self):
        self.maintainer_user = create_maintainer_user()
        self.machine = create_machine()
        self.model = self.machine.model
        self.url = reverse("machine-model-edit", kwargs={"slug": self.model.slug})

    def test_requires_maintainer_access(self):
        """Non-maintainer users should not access the model edit page."""
        regular_user = create_user()
        self.client.force_login(regular_user)
        response = self.client.get(self.url)
        self.assertNotEqual(response.status_code, 200)

    def test_loads_for_maintainer(self):
        """Maintainer should see the model edit form."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "catalog/machine_model_edit.html")

    def test_update_saves_changes(self):
        """Submitting the form should save model changes."""
        self.client.force_login(self.maintainer_user)
        response = self.client.post(
            self.url,
            {"name": "Updated Model Name", "manufacturer": "Bally"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.model.refresh_from_db()
        self.assertEqual(self.model.name, "Updated Model Name")
        self.assertEqual(self.model.manufacturer, "Bally")

    def test_update_sets_updated_by(self):
        """Saving should set updated_by to the current user."""
        self.client.force_login(self.maintainer_user)
        self.client.post(self.url, {"name": "New Name"}, follow=True)
        self.model.refresh_from_db()
        self.assertEqual(self.model.updated_by, self.maintainer_user)

    def test_update_shows_success_message(self):
        """Saving should show a success message with the model name."""
        self.client.force_login(self.maintainer_user)
        response = self.client.post(self.url, {"name": "Star Trek"}, follow=True)
        msgs = list(response.context["messages"])
        self.assertEqual(len(msgs), 1)
        self.assertIn("Star Trek", str(msgs[0]))
        self.assertIn("saved", str(msgs[0]))

    def test_context_includes_instances(self):
        """Context should include instances of this model."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.url)
        self.assertIn("instances", response.context)
        self.assertIn(self.machine, response.context["instances"])

    def test_context_includes_machine_instance_for_breadcrumb(self):
        """Context should include first instance for breadcrumb navigation."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.url)
        self.assertEqual(response.context["machine_instance"], self.machine)
