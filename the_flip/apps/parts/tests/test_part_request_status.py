"""Tests for part request status update AJAX endpoint."""

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TestDataMixin,
    create_part_request,
)
from the_flip.apps.parts.models import PartRequest, PartRequestUpdate


@tag("views")
class PartRequestStatusUpdateTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for PartRequestStatusUpdateView AJAX endpoint."""

    def setUp(self):
        super().setUp()
        self.part_request = create_part_request(
            text="Test part request",
            requested_by=self.maintainer,
        )
        self.status_url = reverse("part-request-status-update", kwargs={"pk": self.part_request.pk})

    def test_status_update_requires_auth(self):
        """Unauthenticated users are redirected to login."""
        response = self.client.post(
            self.status_url,
            {"action": "update_status", "status": PartRequest.Status.ORDERED},
        )
        self.assertEqual(response.status_code, 302)

    def test_status_update_requires_staff(self):
        """Non-staff users cannot update status."""
        self.client.force_login(self.regular_user)
        response = self.client.post(
            self.status_url,
            {"action": "update_status", "status": PartRequest.Status.ORDERED},
        )
        self.assertEqual(response.status_code, 403)

    def test_status_update_success(self):
        """Staff can update status via AJAX, creates update record, returns update_html."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.status_url,
            {"action": "update_status", "status": PartRequest.Status.ORDERED},
        )

        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertTrue(json_data["success"])
        self.assertEqual(json_data["status"], "success")
        self.assertEqual(json_data["new_status"], PartRequest.Status.ORDERED)
        self.assertEqual(json_data["new_status_display"], "Ordered")
        self.assertIn("update_html", json_data)
        self.assertTrue(len(json_data["update_html"]) > 0)

        # Verify update record was created
        self.assertEqual(PartRequestUpdate.objects.count(), 1)
        update = PartRequestUpdate.objects.first()
        self.assertEqual(update.new_status, PartRequest.Status.ORDERED)
        self.assertEqual(update.posted_by, self.maintainer)
        self.assertIn("Requested", update.text)
        self.assertIn("Ordered", update.text)

    def test_status_update_cascades_to_part_request(self):
        """Status update cascades to parent PartRequest."""
        self.client.force_login(self.maintainer_user)

        self.client.post(
            self.status_url,
            {"action": "update_status", "status": PartRequest.Status.RECEIVED},
        )

        self.part_request.refresh_from_db()
        self.assertEqual(self.part_request.status, PartRequest.Status.RECEIVED)

    def test_status_update_invalid_status(self):
        """Invalid status returns 400."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.status_url,
            {"action": "update_status", "status": "invalid_status"},
        )

        self.assertEqual(response.status_code, 400)
        json_data = response.json()
        self.assertFalse(json_data["success"])
        self.assertIn("error", json_data)

    def test_status_update_noop_same_status(self):
        """Same status returns noop, no update created, status unchanged."""
        self.client.force_login(self.maintainer_user)
        original_status = self.part_request.status

        response = self.client.post(
            self.status_url,
            {"action": "update_status", "status": original_status},
        )

        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertTrue(json_data["success"])
        self.assertEqual(json_data["status"], "noop")

        # Verify no update was created
        self.assertEqual(PartRequestUpdate.objects.count(), 0)

        # Verify status unchanged
        self.part_request.refresh_from_db()
        self.assertEqual(self.part_request.status, original_status)

    def test_status_update_unknown_action(self):
        """Unknown action returns 400."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.status_url,
            {"action": "unknown_action"},
        )

        self.assertEqual(response.status_code, 400)
        json_data = response.json()
        self.assertFalse(json_data["success"])
        self.assertIn("error", json_data)
