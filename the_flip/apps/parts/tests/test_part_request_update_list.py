"""Tests for part request updates partial view (infinite scroll)."""

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TestDataMixin,
    create_part_request,
    create_part_request_update,
)


@tag("views")
class PartRequestUpdatesPartialViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for PartRequestUpdatesPartialView AJAX infinite scroll endpoint."""

    def setUp(self):
        super().setUp()
        self.part_request = create_part_request(
            text="Test part request",
            requested_by=self.maintainer,
        )
        self.partial_url = reverse("part-request-updates", kwargs={"pk": self.part_request.pk})

    def test_partial_view_requires_auth(self):
        """Unauthenticated users are redirected to login."""
        response = self.client.get(self.partial_url)
        self.assertEqual(response.status_code, 302)

    def test_partial_view_requires_staff(self):
        """Non-staff users get 403."""
        self.client.force_login(self.regular_user)
        response = self.client.get(self.partial_url)
        self.assertEqual(response.status_code, 403)

    def test_partial_view_returns_json(self):
        """Partial view returns JSON with items, has_next, next_page."""
        self.client.force_login(self.maintainer_user)

        response = self.client.get(self.partial_url)

        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertIn("items", json_data)
        self.assertIn("has_next", json_data)
        self.assertIn("next_page", json_data)

    def test_partial_view_items_contain_update_content(self):
        """Items HTML includes update text and poster."""
        create_part_request_update(
            part_request=self.part_request,
            text="Unique update content here",
            posted_by=self.maintainer,
        )

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.partial_url)

        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertIn("Unique update content here", json_data["items"])
        self.assertIn(str(self.maintainer), json_data["items"])

    def test_partial_view_page_size(self):
        """Returns exactly 10 items per page."""
        # Create 15 updates
        for i in range(15):
            create_part_request_update(
                part_request=self.part_request,
                text=f"Update number {i}",
                posted_by=self.maintainer,
            )

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.partial_url)

        self.assertEqual(response.status_code, 200)
        json_data = response.json()

        # First page should have has_next=True with 15 total items and page size 10
        self.assertTrue(json_data["has_next"])
        self.assertEqual(json_data["next_page"], 2)

    def test_partial_view_paginates(self):
        """Respects page parameter, page 2 gets remaining items."""
        # Create 15 updates
        for i in range(15):
            create_part_request_update(
                part_request=self.part_request,
                text=f"Update number {i}",
                posted_by=self.maintainer,
            )

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.partial_url, {"page": 2})

        self.assertEqual(response.status_code, 200)
        json_data = response.json()

        # Second page should have has_next=False (5 remaining items)
        self.assertFalse(json_data["has_next"])
        self.assertIsNone(json_data["next_page"])

    def test_partial_view_search_filters(self):
        """Search query filters results."""
        create_part_request_update(
            part_request=self.part_request,
            text="Ordered from Marco",
            posted_by=self.maintainer,
        )
        create_part_request_update(
            part_request=self.part_request,
            text="Received shipment",
            posted_by=self.maintainer,
        )

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.partial_url, {"q": "Marco"})

        self.assertEqual(response.status_code, 200)
        json_data = response.json()

        # Should only find the Marco update
        self.assertIn("Marco", json_data["items"])
        self.assertNotIn("Received shipment", json_data["items"])
