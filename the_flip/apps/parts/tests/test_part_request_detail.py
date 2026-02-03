"""Tests for part request detail view and AJAX endpoints."""

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TestDataMixin,
    create_part_request,
    create_part_request_update,
)


@tag("views")
class PartRequestDetailViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for part request detail view."""

    def test_detail_view_requires_staff(self):
        """Detail view requires staff permission."""
        part_request = create_part_request(requested_by=self.maintainer)
        self.client.force_login(self.regular_user)
        response = self.client.get(reverse("part-request-detail", kwargs={"pk": part_request.pk}))
        self.assertEqual(response.status_code, 403)

    def test_detail_view_accessible_to_staff(self):
        """Staff can access detail view."""
        part_request = create_part_request(
            text="Test part request",
            requested_by=self.maintainer,
        )
        self.client.force_login(self.maintainer_user)
        response = self.client.get(reverse("part-request-detail", kwargs={"pk": part_request.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test part request")

    def test_detail_view_renders_status_dropdown_in_mobile_actions(self):
        """Mobile and sidebar both contain interactive status dropdowns."""
        part_request = create_part_request(
            text="Test request",
            requested_by=self.maintainer,
        )
        self.client.force_login(self.maintainer_user)
        response = self.client.get(reverse("part-request-detail", kwargs={"pk": part_request.pk}))

        # Both mobile and sidebar should have a status dropdown with data-update-url
        status_url = reverse("part-request-status-update", kwargs={"pk": part_request.pk})
        content = response.content.decode()
        self.assertEqual(
            content.count(f'data-update-url="{status_url}"'),
            2,
            "Expected two status dropdowns (mobile + sidebar)",
        )


@tag("views")
class PartRequestDetailViewTextUpdateTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for PartRequestDetailView AJAX text updates."""

    def setUp(self):
        super().setUp()
        self.part_request = create_part_request(
            text="Original text",
            requested_by=self.maintainer,
        )
        self.detail_url = reverse("part-request-detail", kwargs={"pk": self.part_request.pk})

    def test_update_text_success(self):
        """AJAX endpoint updates text successfully."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.detail_url,
            {"action": "update_text", "text": "Updated description"},
        )

        self.assertEqual(response.status_code, 200)
        self.part_request.refresh_from_db()
        self.assertEqual(self.part_request.text, "Updated description")

    def test_update_text_empty(self):
        """AJAX endpoint allows empty text."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.detail_url,
            {"action": "update_text", "text": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.part_request.refresh_from_db()
        self.assertEqual(self.part_request.text, "")

    def test_update_text_requires_auth(self):
        """AJAX endpoint requires authentication."""
        response = self.client.post(
            self.detail_url,
            {"action": "update_text", "text": "Should fail"},
        )

        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_update_text_requires_maintainer(self):
        """AJAX endpoint requires maintainer access."""
        self.client.force_login(self.regular_user)

        response = self.client.post(
            self.detail_url,
            {"action": "update_text", "text": "Should fail"},
        )

        self.assertEqual(response.status_code, 403)


@tag("views")
class PartRequestUpdateDetailViewTextUpdateTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for PartRequestUpdateDetailView AJAX text updates."""

    def setUp(self):
        super().setUp()
        self.part_request = create_part_request(requested_by=self.maintainer)
        self.update = create_part_request_update(
            part_request=self.part_request,
            text="Original update text",
            posted_by=self.maintainer,
        )
        self.detail_url = reverse(
            "part-request-update-detail",
            kwargs={"pk": self.update.pk},
        )

    def test_update_text_success(self):
        """AJAX endpoint updates text successfully."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.detail_url,
            {"action": "update_text", "text": "Updated text"},
        )

        self.assertEqual(response.status_code, 200)
        self.update.refresh_from_db()
        self.assertEqual(self.update.text, "Updated text")

    def test_update_text_empty(self):
        """AJAX endpoint allows empty text."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.detail_url,
            {"action": "update_text", "text": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.update.refresh_from_db()
        self.assertEqual(self.update.text, "")

    def test_update_text_requires_auth(self):
        """AJAX endpoint requires authentication."""
        response = self.client.post(
            self.detail_url,
            {"action": "update_text", "text": "Should fail"},
        )

        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_update_text_requires_maintainer(self):
        """AJAX endpoint requires maintainer access."""
        self.client.force_login(self.regular_user)

        response = self.client.post(
            self.detail_url,
            {"action": "update_text", "text": "Should fail"},
        )

        self.assertEqual(response.status_code, 403)
