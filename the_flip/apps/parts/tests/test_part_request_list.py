"""Tests for part request list view and search functionality."""

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TestDataMixin,
    create_part_request,
)
from the_flip.apps.parts.models import (
    PartRequest,
    PartRequestUpdate,
)


@tag("views")
class PartRequestListViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for part request list view access."""

    def test_list_view_requires_authentication(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get(reverse("part-request-list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_list_view_requires_staff_permission(self):
        """Non-staff users should be denied access."""
        self.client.force_login(self.regular_user)
        response = self.client.get(reverse("part-request-list"))
        self.assertEqual(response.status_code, 403)

    def test_list_view_accessible_to_staff(self):
        """Staff users should be able to access the list."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(reverse("part-request-list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "parts/part_request_list.html")

    def test_list_view_shows_part_requests(self):
        """List view shows part requests."""
        self.client.force_login(self.maintainer_user)
        create_part_request(
            text="Flipper rubbers",
            requested_by=self.maintainer,
            machine=self.machine,
        )
        response = self.client.get(reverse("part-request-list"))
        self.assertContains(response, "Flipper rubbers")


@tag("views")
class PartRequestListFilterTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for part request list filtering."""

    def setUp(self):
        super().setUp()

        # Create part requests with different statuses
        self.requested = create_part_request(
            text="Requested part",
            requested_by=self.maintainer,
            status=PartRequest.Status.REQUESTED,
        )
        self.ordered = create_part_request(
            text="Ordered part",
            requested_by=self.maintainer,
            status=PartRequest.Status.ORDERED,
        )
        self.received = create_part_request(
            text="Received part",
            requested_by=self.maintainer,
            status=PartRequest.Status.RECEIVED,
        )
        self.cancelled = create_part_request(
            text="Cancelled part",
            requested_by=self.maintainer,
            status=PartRequest.Status.CANCELLED,
        )

    def test_search_by_status_requested(self):
        """Can search part requests by status 'requested'."""
        self.client.force_login(self.maintainer_user)

        response = self.client.get(reverse("part-request-list") + "?q=requested")
        self.assertContains(response, "Requested part")
        self.assertNotContains(response, "Ordered part")
        self.assertNotContains(response, "Received part")
        self.assertNotContains(response, "Cancelled part")

    def test_search_by_status_ordered(self):
        """Can search part requests by status 'ordered'."""
        self.client.force_login(self.maintainer_user)

        response = self.client.get(reverse("part-request-list") + "?q=ordered")
        self.assertContains(response, "Ordered part")
        self.assertNotContains(response, "Requested part")
        self.assertNotContains(response, "Received part")
        self.assertNotContains(response, "Cancelled part")

    def test_search_by_text(self):
        """Can search part requests by text."""
        self.client.force_login(self.maintainer_user)

        response = self.client.get(reverse("part-request-list") + "?q=Ordered")
        self.assertContains(response, "Ordered part")
        self.assertNotContains(response, "Requested part")


@tag("views")
class PartRequestSearchFreeTextNameTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for searching part requests by free-text name fields."""

    def test_search_by_requested_by_name(self):
        """Can find part requests by free-text requester name."""
        # Create a part request with free-text name (no FK)
        PartRequest.objects.create(
            text="Need flipper rubbers",
            requested_by=None,
            requested_by_name="Wandering Willie",
        )

        self.client.force_login(self.maintainer_user)
        response = self.client.get(reverse("part-request-list") + "?q=Wandering")

        self.assertContains(response, "flipper rubbers")

    def test_search_by_posted_by_name(self):
        """Can find part requests by free-text update poster name."""
        # Create a part request and update with free-text poster name
        part_request = PartRequest.objects.create(
            text="Need flipper rubbers",
            requested_by=self.maintainer,
        )
        PartRequestUpdate.objects.create(
            part_request=part_request,
            text="Ordered from Marco",
            posted_by=None,
            posted_by_name="Visiting Vera",
        )

        self.client.force_login(self.maintainer_user)
        response = self.client.get(reverse("part-request-list") + "?q=Visiting")

        self.assertContains(response, "flipper rubbers")

    def test_search_updates_by_posted_by_name(self):
        """Can find updates by free-text poster name on detail page."""
        # Create a part request and update with free-text poster name
        part_request = PartRequest.objects.create(
            text="Need flipper rubbers",
            requested_by=self.maintainer,
        )
        PartRequestUpdate.objects.create(
            part_request=part_request,
            text="Ordered from Marco",
            posted_by=None,
            posted_by_name="Visiting Vera",
        )

        self.client.force_login(self.maintainer_user)
        response = self.client.get(
            reverse("part-request-detail", kwargs={"pk": part_request.pk}) + "?q=Visiting"
        )

        self.assertContains(response, "Ordered from Marco")

    def test_search_updates_does_not_match_parent_request_text(self):
        """Part request detail update search should NOT match the request's text.

        Since the user is already viewing a specific part request's updates,
        searching for the request's text would be redundant and confusing -
        it would match all updates on this request rather than filtering
        by update content.
        """
        # Create part request with distinctive text
        part_request = PartRequest.objects.create(
            text="Need special flipper coil assembly",
            requested_by=self.maintainer,
        )
        # Create updates with different text
        PartRequestUpdate.objects.create(
            part_request=part_request,
            text="Checking inventory",
            posted_by=self.maintainer,
        )
        PartRequestUpdate.objects.create(
            part_request=part_request,
            text="Placed order",
            posted_by=self.maintainer,
        )

        self.client.force_login(self.maintainer_user)

        # Search for the parent part request's text
        response = self.client.get(
            reverse("part-request-detail", kwargs={"pk": part_request.pk})
            + "?q=flipper coil assembly"
        )

        # Neither update should appear because parent request text
        # is not a search field in this scoped context
        self.assertNotContains(response, "Checking inventory")
        self.assertNotContains(response, "Placed order")
