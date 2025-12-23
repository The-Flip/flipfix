"""Tests for part request creation views."""

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.core.test_utils import (
    SharedAccountTestMixin,
    SuppressRequestLogsMixin,
    TestDataMixin,
)
from the_flip.apps.parts.models import PartRequest


@tag("views")
class PartRequestCreateViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for part request create view."""

    def setUp(self):
        super().setUp()
        self.maintainer = Maintainer.objects.get(user=self.maintainer_user)

    def test_create_view_requires_staff(self):
        """Create view requires staff permission."""
        self.client.force_login(self.regular_user)
        response = self.client.get(reverse("part-request-create"))
        self.assertEqual(response.status_code, 403)

    def test_create_view_accessible_to_staff(self):
        """Staff can access create view."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(reverse("part-request-create"))
        self.assertEqual(response.status_code, 200)

    def test_create_part_request(self):
        """Staff can create a part request."""
        self.client.force_login(self.maintainer_user)
        response = self.client.post(
            reverse("part-request-create"),
            {
                "text": "New target rubbers needed",
                "machine_slug": self.machine.slug,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PartRequest.objects.count(), 1)
        part_request = PartRequest.objects.first()
        self.assertEqual(part_request.text, "New target rubbers needed")
        self.assertEqual(part_request.machine, self.machine)
        self.assertEqual(part_request.requested_by, self.maintainer)

    def test_create_part_request_without_machine(self):
        """Can create a part request without linking to a machine."""
        self.client.force_login(self.maintainer_user)
        response = self.client.post(
            reverse("part-request-create"),
            {
                "text": "General supplies",
                "machine_slug": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        part_request = PartRequest.objects.first()
        self.assertIsNone(part_request.machine)


@tag("views")
class PartRequestSharedAccountTests(
    SharedAccountTestMixin, SuppressRequestLogsMixin, TestDataMixin, TestCase
):
    """Tests for part request creation from shared/terminal accounts."""

    def test_shared_account_with_valid_username_uses_fk(self):
        """Shared account selecting from dropdown saves to FK."""
        self.client.force_login(self.shared_user)
        response = self.client.post(
            reverse("part-request-create"),
            {
                "text": "Need flipper rubbers",
                "requester_name": str(self.identifying_maintainer),
                "requester_name_username": self.identifying_user.username,
            },
        )
        self.assertEqual(response.status_code, 302)
        part_request = PartRequest.objects.first()
        self.assertEqual(part_request.requested_by, self.identifying_maintainer)
        self.assertEqual(part_request.requested_by_name, "")

    def test_shared_account_with_free_text_uses_text_field(self):
        """Shared account typing free text saves to text field."""
        self.client.force_login(self.shared_user)
        response = self.client.post(
            reverse("part-request-create"),
            {
                "text": "Need flipper rubbers",
                "requester_name": "Jane Visitor",
                "requester_name_username": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        part_request = PartRequest.objects.first()
        self.assertIsNone(part_request.requested_by)
        self.assertEqual(part_request.requested_by_name, "Jane Visitor")

    def test_shared_account_with_empty_name_shows_error(self):
        """Shared account with empty name shows form error."""
        self.client.force_login(self.shared_user)
        response = self.client.post(
            reverse("part-request-create"),
            {
                "text": "Need flipper rubbers",
                "requester_name": "",
                "requester_name_username": "",
            },
        )
        self.assertEqual(response.status_code, 200)  # Form re-rendered
        self.assertContains(response, "Please enter your name")
        self.assertEqual(PartRequest.objects.count(), 0)

    def test_regular_account_uses_current_user(self):
        """Regular account falls back to current user."""
        self.client.force_login(self.identifying_user)
        response = self.client.post(
            reverse("part-request-create"),
            {
                "text": "Need flipper rubbers",
            },
        )
        self.assertEqual(response.status_code, 302)
        part_request = PartRequest.objects.first()
        self.assertEqual(part_request.requested_by, self.identifying_maintainer)


@tag("views")
class PartRequestFormReRenderTests(
    SharedAccountTestMixin, SuppressRequestLogsMixin, TestDataMixin, TestCase
):
    """Tests for form re-rendering preserving hidden username field."""

    def test_hidden_username_preserved_on_form_error(self):
        """Hidden username field is preserved when form re-renders with errors."""
        self.client.force_login(self.shared_user)

        # Submit form with valid username but missing required field (text)
        response = self.client.post(
            reverse("part-request-create"),
            {
                "text": "",  # Empty text should trigger validation error
                "requester_name": str(self.identifying_maintainer),
                "requester_name_username": self.identifying_user.username,
            },
        )

        # Form should re-render with error
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required")

        # Hidden username should be preserved in re-rendered form
        self.assertContains(
            response,
            f'value="{self.identifying_user.username}"',
            msg_prefix="Hidden username field should be preserved on form re-render",
        )
