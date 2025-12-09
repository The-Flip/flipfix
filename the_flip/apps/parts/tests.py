"""Tests for parts management functionality."""

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.core.test_utils import (
    AccessControlTestCase,
    create_machine,
    create_maintainer_user,
    create_part_request,
    create_part_request_update,
    create_user,
)
from the_flip.apps.parts.models import (
    PartRequest,
    PartRequestUpdate,
)


class PartRequestModelTests(TestCase):
    """Tests for the PartRequest model."""

    def setUp(self):
        self.maintainer_user = create_maintainer_user()
        self.maintainer = Maintainer.objects.get(user=self.maintainer_user)
        self.machine = create_machine()

    def test_create_part_request(self):
        """Can create a part request."""
        part_request = PartRequest.objects.create(
            text="Need new flipper rubbers",
            requested_by=self.maintainer,
            machine=self.machine,
        )
        self.assertEqual(part_request.status, PartRequest.STATUS_REQUESTED)
        self.assertEqual(part_request.requested_by, self.maintainer)
        self.assertEqual(part_request.machine, self.machine)

    def test_str_representation(self):
        """String representation shows ID and text preview."""
        part_request = create_part_request(
            text="Need flipper rubbers",
            machine=self.machine,
            requested_by=self.maintainer,
        )
        result = str(part_request)
        self.assertIn(f"#{part_request.pk}", result)
        self.assertIn("Parts Request", result)
        self.assertIn("flipper rubbers", result)

    def test_str_with_long_text(self):
        """String representation truncates long text."""
        long_text = "A" * 100
        part_request = create_part_request(
            text=long_text,
            requested_by=self.maintainer,
        )
        result = str(part_request)
        self.assertIn("...", result)

    def test_status_choices(self):
        """All status choices are valid."""
        part_request = create_part_request(requested_by=self.maintainer)

        for status, _ in PartRequest.STATUS_CHOICES:
            part_request.status = status
            part_request.save()
            part_request.refresh_from_db()
            self.assertEqual(part_request.status, status)

    def test_status_display_class(self):
        """status_display_class returns correct CSS class."""
        part_request = create_part_request(requested_by=self.maintainer)

        part_request.status = PartRequest.STATUS_REQUESTED
        self.assertEqual(part_request.status_display_class, "requested")

        part_request.status = PartRequest.STATUS_ORDERED
        self.assertEqual(part_request.status_display_class, "ordered")

        part_request.status = PartRequest.STATUS_RECEIVED
        self.assertEqual(part_request.status_display_class, "received")

        part_request.status = PartRequest.STATUS_CANCELLED
        self.assertEqual(part_request.status_display_class, "cancelled")


class PartRequestUpdateModelTests(TestCase):
    """Tests for the PartRequestUpdate model."""

    def setUp(self):
        self.maintainer_user = create_maintainer_user(username="maintainer")
        self.maintainer = Maintainer.objects.get(user=self.maintainer_user)
        self.part_request = create_part_request(requested_by=self.maintainer)

    def test_create_update(self):
        """Can create an update on a part request."""
        update = PartRequestUpdate.objects.create(
            part_request=self.part_request,
            posted_by=self.maintainer,
            text="Ordered from Marco Specialties",
        )
        self.assertEqual(update.part_request, self.part_request)
        self.assertEqual(update.posted_by, self.maintainer)
        self.assertEqual(update.new_status, "")

    def test_create_update_with_status_change(self):
        """Can create an update that changes the status."""
        update = PartRequestUpdate.objects.create(
            part_request=self.part_request,
            posted_by=self.maintainer,
            text="Ordered from Marco Specialties",
            new_status=PartRequest.STATUS_ORDERED,
        )
        self.assertEqual(update.new_status, PartRequest.STATUS_ORDERED)

    def test_str_representation(self):
        """String representation shows update info."""
        update = create_part_request_update(
            part_request=self.part_request, posted_by=self.maintainer
        )
        result = str(update)
        self.assertIn("Update", result)
        self.assertIn(str(self.part_request.pk), result)
        self.assertIn(str(self.maintainer), result)

    def test_update_changes_part_request_status(self):
        """Creating update with new_status changes the part request status."""
        self.assertEqual(self.part_request.status, PartRequest.STATUS_REQUESTED)

        create_part_request_update(
            part_request=self.part_request,
            posted_by=self.maintainer,
            new_status=PartRequest.STATUS_ORDERED,
        )

        self.part_request.refresh_from_db()
        self.assertEqual(self.part_request.status, PartRequest.STATUS_ORDERED)


@tag("views")
class PartRequestViewTests(AccessControlTestCase):
    """Tests for part request views."""

    def setUp(self):
        self.maintainer_user = create_maintainer_user()
        self.maintainer = Maintainer.objects.get(user=self.maintainer_user)
        self.regular_user = create_user()
        self.machine = create_machine()

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
        self.assertTemplateUsed(response, "parts/part_list.html")

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


@tag("views")
class PartRequestUpdateViewTests(TestCase):
    """Tests for part request update views."""

    def setUp(self):
        self.maintainer_user = create_maintainer_user()
        self.maintainer = Maintainer.objects.get(user=self.maintainer_user)
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
                "new_status": PartRequest.STATUS_ORDERED,
            },
        )
        self.assertEqual(response.status_code, 302)
        update = PartRequestUpdate.objects.first()
        self.assertEqual(update.new_status, PartRequest.STATUS_ORDERED)

        # Check the part request status was updated
        self.part_request.refresh_from_db()
        self.assertEqual(self.part_request.status, PartRequest.STATUS_ORDERED)


@tag("views")
class PartRequestListFilterTests(TestCase):
    """Tests for part request list filtering."""

    def setUp(self):
        self.maintainer_user = create_maintainer_user()
        self.maintainer = Maintainer.objects.get(user=self.maintainer_user)
        self.machine = create_machine()

        # Create part requests with different statuses
        self.requested = create_part_request(
            text="Requested part",
            requested_by=self.maintainer,
            status=PartRequest.STATUS_REQUESTED,
        )
        self.ordered = create_part_request(
            text="Ordered part",
            requested_by=self.maintainer,
            status=PartRequest.STATUS_ORDERED,
        )
        self.received = create_part_request(
            text="Received part",
            requested_by=self.maintainer,
            status=PartRequest.STATUS_RECEIVED,
        )
        self.cancelled = create_part_request(
            text="Cancelled part",
            requested_by=self.maintainer,
            status=PartRequest.STATUS_CANCELLED,
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


@tag("feature_flags")
class PartsFeatureFlagTests(TestCase):
    """Tests for the PARTS_ENABLED feature flag."""

    def setUp(self):
        from constance.test import override_config

        self.override_config = override_config
        self.maintainer_user = create_maintainer_user()
        self.maintainer = Maintainer.objects.get(user=self.maintainer_user)
        self.machine = create_machine()

    def test_nav_link_hidden_when_disabled(self):
        """Parts nav link is hidden when PARTS_ENABLED is False."""
        self.client.force_login(self.maintainer_user)

        with self.override_config(PARTS_ENABLED=False):
            response = self.client.get(reverse("maintainer-machine-list"))
            # The nav link to parts should not be present
            self.assertNotContains(response, 'href="/parts/"')

    def test_nav_link_shown_when_enabled(self):
        """Parts nav link is shown when PARTS_ENABLED is True."""
        self.client.force_login(self.maintainer_user)

        with self.override_config(PARTS_ENABLED=True):
            response = self.client.get(reverse("maintainer-machine-list"))
            # The nav link to parts should be present
            self.assertContains(response, 'href="/parts/"')

    def test_activity_feed_excludes_parts_when_disabled(self):
        """Machine activity feed excludes parts when PARTS_ENABLED is False."""
        from the_flip.apps.catalog.views import get_activity_entries

        # Create a part request for this machine
        create_part_request(
            text="Test part",
            requested_by=self.maintainer,
            machine=self.machine,
        )

        with self.override_config(PARTS_ENABLED=False):
            logs, reports, part_requests, part_updates = get_activity_entries(self.machine)
            # Parts querysets should be empty
            self.assertEqual(list(part_requests), [])
            self.assertEqual(list(part_updates), [])

    def test_activity_feed_includes_parts_when_enabled(self):
        """Machine activity feed includes parts when PARTS_ENABLED is True."""
        from the_flip.apps.catalog.views import get_activity_entries

        # Create a part request for this machine
        part = create_part_request(
            text="Test part",
            requested_by=self.maintainer,
            machine=self.machine,
        )

        with self.override_config(PARTS_ENABLED=True):
            logs, reports, part_requests, part_updates = get_activity_entries(self.machine)
            # Parts should be included
            self.assertEqual(list(part_requests), [part])
