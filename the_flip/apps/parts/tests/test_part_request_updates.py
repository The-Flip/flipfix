"""Tests for part request update views."""

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.core.test_utils import (
    SharedAccountTestMixin,
    SuppressRequestLogsMixin,
    TestDataMixin,
    create_part_request,
)
from the_flip.apps.parts.models import PartRequest, PartRequestUpdate


@tag("views")
class PartRequestUpdateViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for part request update views."""

    def setUp(self):
        super().setUp()
        self.part_request = create_part_request(requested_by=self.maintainer)

    def test_create_update(self):
        """Staff can create an update on a part request."""
        self.client.force_login(self.maintainer_user)
        response = self.client.post(
            reverse("part-request-update-create", kwargs={"pk": self.part_request.pk}),
            {
                "text": "Ordered from Marco",
                "new_status": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PartRequestUpdate.objects.count(), 1)
        update = PartRequestUpdate.objects.first()
        self.assertEqual(update.text, "Ordered from Marco")
        self.assertEqual(update.posted_by, self.maintainer)

    def test_create_update_with_status_change(self):
        """Can create an update that changes the status."""
        self.client.force_login(self.maintainer_user)
        response = self.client.post(
            reverse("part-request-update-create", kwargs={"pk": self.part_request.pk}),
            {
                "text": "Ordered from Marco",
                "new_status": PartRequest.Status.ORDERED,
            },
        )
        self.assertEqual(response.status_code, 302)
        update = PartRequestUpdate.objects.first()
        self.assertEqual(update.new_status, PartRequest.Status.ORDERED)

        # Check the part request status was updated
        self.part_request.refresh_from_db()
        self.assertEqual(self.part_request.status, PartRequest.Status.ORDERED)


@tag("views")
class PartRequestUpdateSharedAccountTests(
    SharedAccountTestMixin, SuppressRequestLogsMixin, TestDataMixin, TestCase
):
    """Tests for part request update creation from shared/terminal accounts."""

    def setUp(self):
        super().setUp()
        # Create a part request to update
        self.part_request = create_part_request(requested_by=self.identifying_maintainer)

    def test_shared_account_with_valid_username_uses_fk(self):
        """Shared account selecting from dropdown saves to FK."""
        self.client.force_login(self.shared_user)
        response = self.client.post(
            reverse("part-request-update-create", kwargs={"pk": self.part_request.pk}),
            {
                "text": "Ordered from Marco",
                "new_status": "",
                "requester_name": str(self.identifying_maintainer),
                "requester_name_username": self.identifying_user.username,
            },
        )
        self.assertEqual(response.status_code, 302)
        update = PartRequestUpdate.objects.first()
        self.assertEqual(update.posted_by, self.identifying_maintainer)
        self.assertEqual(update.posted_by_name, "")

    def test_shared_account_with_free_text_uses_text_field(self):
        """Shared account typing free text saves to text field."""
        self.client.force_login(self.shared_user)
        response = self.client.post(
            reverse("part-request-update-create", kwargs={"pk": self.part_request.pk}),
            {
                "text": "Ordered from Marco",
                "new_status": "",
                "requester_name": "Jane Visitor",
                "requester_name_username": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        update = PartRequestUpdate.objects.first()
        self.assertIsNone(update.posted_by)
        self.assertEqual(update.posted_by_name, "Jane Visitor")

    def test_shared_account_with_empty_name_shows_error(self):
        """Shared account with empty name shows form error."""
        self.client.force_login(self.shared_user)
        response = self.client.post(
            reverse("part-request-update-create", kwargs={"pk": self.part_request.pk}),
            {
                "text": "Ordered from Marco",
                "new_status": "",
                "requester_name": "",
                "requester_name_username": "",
            },
        )
        self.assertEqual(response.status_code, 200)  # Form re-rendered with errors
        self.assertContains(response, "Please enter your name")
        self.assertEqual(PartRequestUpdate.objects.count(), 0)

    def test_regular_account_uses_current_user(self):
        """Regular account falls back to current user."""
        self.client.force_login(self.identifying_user)
        response = self.client.post(
            reverse("part-request-update-create", kwargs={"pk": self.part_request.pk}),
            {
                "text": "Ordered from Marco",
                "new_status": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        update = PartRequestUpdate.objects.first()
        self.assertEqual(update.posted_by, self.identifying_maintainer)
