"""Tests for parts management functionality."""

from unittest.mock import patch

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.core.test_utils import (
    create_machine,
    create_part_request,
    create_part_request_update,
    create_staff_user,
    create_user,
)
from the_flip.apps.parts.models import (
    PartRequest,
    PartRequestUpdate,
)
from the_flip.apps.webhooks.formatters import format_discord_message
from the_flip.apps.webhooks.models import (
    WebhookEndpoint,
    WebhookEventSubscription,
)


class PartRequestModelTests(TestCase):
    """Tests for the PartRequest model."""

    def setUp(self):
        self.staff_user = create_staff_user(username="teststaff")
        self.maintainer = Maintainer.objects.get(user=self.staff_user)
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
        self.assertIn("Part Request", result)
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
        self.staff_user = create_staff_user(username="teststaff")
        self.maintainer = Maintainer.objects.get(user=self.staff_user)
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
class PartRequestViewTests(TestCase):
    """Tests for part request views."""

    def setUp(self):
        self.staff_user = create_staff_user(username="staffuser")
        self.maintainer = Maintainer.objects.get(user=self.staff_user)
        self.regular_user = create_user(username="regularuser")
        self.machine = create_machine()

    def test_list_view_requires_authentication(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get(reverse("part-request-list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_list_view_requires_staff_permission(self):
        """Non-staff users should be denied access."""
        self.client.login(username="regularuser", password="testpass123")
        response = self.client.get(reverse("part-request-list"))
        self.assertEqual(response.status_code, 403)

    def test_list_view_accessible_to_staff(self):
        """Staff users should be able to access the list."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(reverse("part-request-list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "parts/part_list.html")

    def test_list_view_shows_part_requests(self):
        """List view shows part requests."""
        self.client.login(username="staffuser", password="testpass123")
        create_part_request(
            text="Flipper rubbers",
            requested_by=self.maintainer,
            machine=self.machine,
        )
        response = self.client.get(reverse("part-request-list"))
        self.assertContains(response, "Flipper rubbers")

    def test_create_view_requires_staff(self):
        """Create view requires staff permission."""
        self.client.login(username="regularuser", password="testpass123")
        response = self.client.get(reverse("part-request-create"))
        self.assertEqual(response.status_code, 403)

    def test_create_view_accessible_to_staff(self):
        """Staff can access create view."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(reverse("part-request-create"))
        self.assertEqual(response.status_code, 200)

    def test_create_part_request(self):
        """Staff can create a part request."""
        self.client.login(username="staffuser", password="testpass123")
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
        self.client.login(username="staffuser", password="testpass123")
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
        self.client.login(username="regularuser", password="testpass123")
        response = self.client.get(reverse("part-request-detail", kwargs={"pk": part_request.pk}))
        self.assertEqual(response.status_code, 403)

    def test_detail_view_accessible_to_staff(self):
        """Staff can access detail view."""
        part_request = create_part_request(
            text="Test part request",
            requested_by=self.maintainer,
        )
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(reverse("part-request-detail", kwargs={"pk": part_request.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test part request")


@tag("views")
class PartRequestUpdateViewTests(TestCase):
    """Tests for part request update views."""

    def setUp(self):
        self.staff_user = create_staff_user(username="staffuser")
        self.maintainer = Maintainer.objects.get(user=self.staff_user)
        self.part_request = create_part_request(requested_by=self.maintainer)

    def test_create_update(self):
        """Staff can create an update on a part request."""
        self.client.login(username="staffuser", password="testpass123")
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
        self.client.login(username="staffuser", password="testpass123")
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


class PartRequestWebhookFormatterTests(TestCase):
    """Tests for part request Discord webhook formatting."""

    def setUp(self):
        self.staff_user = create_staff_user(username="teststaff")
        self.maintainer = Maintainer.objects.get(user=self.staff_user)
        self.machine = create_machine()

    def test_format_part_request_created(self):
        """Format a new part request message."""
        part_request = create_part_request(
            text="Need new flipper rubbers",
            requested_by=self.maintainer,
            machine=self.machine,
        )
        message = format_discord_message("part_request_created", part_request)

        # Verify structure
        self.assertIn("embeds", message)
        self.assertEqual(len(message["embeds"]), 1)
        embed = message["embeds"][0]

        # Required fields exist
        self.assertIn("title", embed)
        self.assertIn("description", embed)
        self.assertIn("url", embed)
        self.assertIn("color", embed)

        # Title includes part request ID
        self.assertIn(f"#{part_request.pk}", embed["title"])

        # Description includes the text
        self.assertIn("flipper rubbers", embed["description"])

        # URL points to the part request
        self.assertIn(f"/parts/{part_request.pk}/", embed["url"])

    def test_format_part_request_status_changed(self):
        """Format a status change message."""
        part_request = create_part_request(
            text="Need new flipper rubbers",
            requested_by=self.maintainer,
            machine=self.machine,
            status=PartRequest.STATUS_ORDERED,
        )
        message = format_discord_message("part_request_status_changed", part_request)

        embed = message["embeds"][0]

        # Title includes status
        self.assertIn("Ordered", embed["title"])

        # Description includes status
        self.assertIn("Status", embed["description"])

    def test_format_part_request_update_created(self):
        """Format a part request update message."""
        part_request = create_part_request(
            text="Need new flipper rubbers",
            requested_by=self.maintainer,
            machine=self.machine,
        )
        update = create_part_request_update(
            part_request=part_request,
            posted_by=self.maintainer,
            text="Ordered from Marco Specialties",
        )
        message = format_discord_message("part_request_update_created", update)

        embed = message["embeds"][0]

        # Title references the part request
        self.assertIn(f"#{part_request.pk}", embed["title"])

        # Description includes the update text
        self.assertIn("Marco Specialties", embed["description"])


class PartRequestWebhookSignalTests(TestCase):
    """Tests for part request webhook signal triggers."""

    def setUp(self):
        self.staff_user = create_staff_user(username="teststaff")
        self.maintainer = Maintainer.objects.get(user=self.staff_user)
        self.machine = create_machine()
        self.endpoint = WebhookEndpoint.objects.create(
            name="Test Endpoint",
            url="https://discord.com/api/webhooks/123/abc",
            is_enabled=True,
        )
        # Subscribe to parts events
        for event_type in [
            WebhookEndpoint.EVENT_PART_REQUEST_CREATED,
            WebhookEndpoint.EVENT_PART_REQUEST_STATUS_CHANGED,
            WebhookEndpoint.EVENT_PART_REQUEST_UPDATE_CREATED,
        ]:
            WebhookEventSubscription.objects.create(
                endpoint=self.endpoint,
                event_type=event_type,
                is_enabled=True,
            )

    @patch("the_flip.apps.webhooks.tasks.async_task")
    def test_signal_fires_on_part_request_created(self, mock_async):
        """Signal fires when a part request is created."""
        part_request = create_part_request(
            requested_by=self.maintainer,
            machine=self.machine,
        )

        # Find the part_request_created call
        calls = [c for c in mock_async.call_args_list if c[0][1] == "part_request_created"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][2], part_request.pk)

    @patch("the_flip.apps.webhooks.tasks.async_task")
    def test_signal_fires_on_part_request_update_created(self, mock_async):
        """Signal fires when a part request update is created."""
        part_request = create_part_request(requested_by=self.maintainer)
        mock_async.reset_mock()

        update = create_part_request_update(
            part_request=part_request,
            posted_by=self.maintainer,
            text="Update text",
        )

        # Find the part_request_update_created call
        calls = [c for c in mock_async.call_args_list if c[0][1] == "part_request_update_created"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][2], update.pk)

    @patch("the_flip.apps.webhooks.tasks.async_task")
    def test_signal_fires_on_status_change_via_update(self, mock_async):
        """Signal fires when status changes via an update."""
        part_request = create_part_request(requested_by=self.maintainer)
        mock_async.reset_mock()

        create_part_request_update(
            part_request=part_request,
            posted_by=self.maintainer,
            text="Ordered it",
            new_status=PartRequest.STATUS_ORDERED,
        )

        # Should fire both update_created and status_changed
        event_types = [c[0][1] for c in mock_async.call_args_list]
        self.assertIn("part_request_update_created", event_types)
        self.assertIn("part_request_status_changed", event_types)


@tag("views")
class PartRequestListFilterTests(TestCase):
    """Tests for part request list filtering."""

    def setUp(self):
        self.staff_user = create_staff_user(username="staffuser")
        self.maintainer = Maintainer.objects.get(user=self.staff_user)
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

    def test_filter_by_status(self):
        """Can filter part requests by status."""
        self.client.login(username="staffuser", password="testpass123")

        # Filter by requested status
        response = self.client.get(reverse("part-request-list") + "?status=requested")
        self.assertContains(response, "Requested part")
        self.assertNotContains(response, "Ordered part")
        self.assertNotContains(response, "Received part")

    def test_filter_by_ordered_status(self):
        """Can filter by 'ordered' status."""
        self.client.login(username="staffuser", password="testpass123")

        response = self.client.get(reverse("part-request-list") + "?status=ordered")
        self.assertContains(response, "Ordered part")
        self.assertNotContains(response, "Requested part")
        self.assertNotContains(response, "Received part")

    def test_search_by_text(self):
        """Can search part requests by text."""
        self.client.login(username="staffuser", password="testpass123")

        response = self.client.get(reverse("part-request-list") + "?q=Ordered")
        self.assertContains(response, "Ordered part")
        self.assertNotContains(response, "Requested part")
