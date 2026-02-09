"""Tests for part request detail view and AJAX endpoints."""

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.core.models import RecordReference
from the_flip.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TestDataMixin,
    create_part_request,
    create_part_request_update,
)
from the_flip.apps.parts.models import PartRequest, PartRequestUpdate


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
class PartRequestDetailSearchBarVisibilityTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for conditional search bar visibility on part request detail."""

    def setUp(self):
        super().setUp()
        self.part_request = create_part_request(
            text="Test part request",
            requested_by=self.maintainer,
        )
        self.detail_url = reverse("part-request-detail", kwargs={"pk": self.part_request.pk})

    def test_search_bar_hidden_when_few_updates(self):
        """Search bar should not appear when there are 5 or fewer updates."""
        for i in range(5):
            create_part_request_update(
                part_request=self.part_request, text=f"Update {i}", posted_by=self.maintainer
            )

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.detail_url)

        self.assertNotContains(response, 'type="search"')

    def test_search_bar_shown_when_many_updates(self):
        """Search bar should appear when there are more than 5 updates."""
        for i in range(6):
            create_part_request_update(
                part_request=self.part_request, text=f"Update {i}", posted_by=self.maintainer
            )

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.detail_url)

        self.assertContains(response, 'type="search"')

    def test_search_bar_shown_when_query_active_with_few_updates(self):
        """Search bar should appear when a search query is active, even with few updates."""
        create_part_request_update(
            part_request=self.part_request, text="Only update", posted_by=self.maintainer
        )

        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.detail_url, {"q": "test"})

        self.assertContains(response, 'type="search"')


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

    def test_update_text_converts_authoring_links_to_storage(self):
        """AJAX text update converts [[machine:slug]] to [[machine:id:N]]."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.detail_url,
            {"action": "update_text", "text": f"See [[machine:{self.machine.slug}]]"},
        )

        self.assertEqual(response.status_code, 200)
        self.part_request.refresh_from_db()
        self.assertEqual(self.part_request.text, f"See [[machine:id:{self.machine.pk}]]")

    def test_update_text_syncs_references(self):
        """AJAX text update creates RecordReference rows for links."""
        self.client.force_login(self.maintainer_user)

        self.client.post(
            self.detail_url,
            {"action": "update_text", "text": f"See [[machine:{self.machine.slug}]]"},
        )

        source_ct = ContentType.objects.get_for_model(PartRequest)
        self.assertTrue(
            RecordReference.objects.filter(
                source_type=source_ct,
                source_id=self.part_request.pk,
            ).exists()
        )

    def test_update_text_broken_link_returns_error(self):
        """AJAX text update with broken link returns 400."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.detail_url,
            {"action": "update_text", "text": "See [[machine:nonexistent]]"},
        )

        self.assertEqual(response.status_code, 400)
        self.part_request.refresh_from_db()
        self.assertEqual(self.part_request.text, "Original text")


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

    def test_update_text_converts_authoring_links_to_storage(self):
        """AJAX text update converts [[machine:slug]] to [[machine:id:N]]."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.detail_url,
            {"action": "update_text", "text": f"See [[machine:{self.machine.slug}]]"},
        )

        self.assertEqual(response.status_code, 200)
        self.update.refresh_from_db()
        self.assertEqual(self.update.text, f"See [[machine:id:{self.machine.pk}]]")

    def test_update_text_syncs_references(self):
        """AJAX text update creates RecordReference rows for links."""
        self.client.force_login(self.maintainer_user)

        self.client.post(
            self.detail_url,
            {"action": "update_text", "text": f"See [[machine:{self.machine.slug}]]"},
        )

        source_ct = ContentType.objects.get_for_model(PartRequestUpdate)
        self.assertTrue(
            RecordReference.objects.filter(
                source_type=source_ct,
                source_id=self.update.pk,
            ).exists()
        )

    def test_update_text_broken_link_returns_error(self):
        """AJAX text update with broken link returns 400."""
        self.client.force_login(self.maintainer_user)

        response = self.client.post(
            self.detail_url,
            {"action": "update_text", "text": "See [[machine:nonexistent]]"},
        )

        self.assertEqual(response.status_code, 400)
        self.update.refresh_from_db()
        self.assertEqual(self.update.text, "Original update text")
