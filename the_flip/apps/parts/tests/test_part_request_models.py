"""Tests for PartRequest and PartRequestUpdate models."""

from datetime import timedelta

from django.test import TestCase, tag
from django.utils import timezone

from the_flip.apps.core.test_utils import (
    TestDataMixin,
    create_part_request,
    create_part_request_update,
)
from the_flip.apps.parts.models import (
    PartRequest,
    PartRequestUpdate,
)


@tag("models")
class PartRequestModelTests(TestDataMixin, TestCase):
    """Tests for the PartRequest model."""

    def test_create_part_request(self):
        """Can create a part request."""
        part_request = PartRequest.objects.create(
            text="Need new flipper rubbers",
            requested_by=self.maintainer,
            machine=self.machine,
        )
        self.assertEqual(part_request.status, PartRequest.Status.REQUESTED)
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

        for status, _ in PartRequest.Status.choices:
            part_request.status = status
            part_request.save()
            part_request.refresh_from_db()
            self.assertEqual(part_request.status, status)

    def test_status_display_class(self):
        """status_display_class returns correct CSS class."""
        part_request = create_part_request(requested_by=self.maintainer)

        part_request.status = PartRequest.Status.REQUESTED
        self.assertEqual(part_request.status_display_class, "requested")

        part_request.status = PartRequest.Status.ORDERED
        self.assertEqual(part_request.status_display_class, "ordered")

        part_request.status = PartRequest.Status.RECEIVED
        self.assertEqual(part_request.status_display_class, "received")

        part_request.status = PartRequest.Status.CANCELLED
        self.assertEqual(part_request.status_display_class, "cancelled")

    def test_requester_display_with_fk(self):
        """requester_display returns maintainer name when FK is set."""
        part_request = create_part_request(requested_by=self.maintainer)
        self.assertEqual(part_request.requester_display, str(self.maintainer))

    def test_requester_display_with_text_field(self):
        """requester_display returns text field when FK is null."""
        part_request = PartRequest.objects.create(
            text="Test request",
            requested_by=None,
            requested_by_name="Jane Visitor",
        )
        self.assertEqual(part_request.requester_display, "Jane Visitor")

    def test_requester_display_prefers_fk_over_text(self):
        """requester_display prefers FK over text field if both set."""
        part_request = PartRequest.objects.create(
            text="Test request",
            requested_by=self.maintainer,
            requested_by_name="Should not show",
        )
        self.assertEqual(part_request.requester_display, str(self.maintainer))


@tag("models")
class PartRequestUpdateModelTests(TestDataMixin, TestCase):
    """Tests for the PartRequestUpdate model."""

    def setUp(self):
        super().setUp()
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
            new_status=PartRequest.Status.ORDERED,
        )
        self.assertEqual(update.new_status, PartRequest.Status.ORDERED)

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
        self.assertEqual(self.part_request.status, PartRequest.Status.REQUESTED)

        create_part_request_update(
            part_request=self.part_request,
            posted_by=self.maintainer,
            new_status=PartRequest.Status.ORDERED,
        )

        self.part_request.refresh_from_db()
        self.assertEqual(self.part_request.status, PartRequest.Status.ORDERED)

    def test_poster_display_with_fk(self):
        """poster_display returns maintainer name when FK is set."""
        update = create_part_request_update(
            part_request=self.part_request,
            posted_by=self.maintainer,
        )
        self.assertEqual(update.poster_display, str(self.maintainer))

    def test_poster_display_with_text_field(self):
        """poster_display returns text field when FK is null."""
        update = PartRequestUpdate.objects.create(
            part_request=self.part_request,
            posted_by=None,
            posted_by_name="Jane Visitor",
            text="Update text",
        )
        self.assertEqual(update.poster_display, "Jane Visitor")

    def test_poster_display_prefers_fk_over_text(self):
        """poster_display prefers FK over text field if both set."""
        update = PartRequestUpdate.objects.create(
            part_request=self.part_request,
            posted_by=self.maintainer,
            posted_by_name="Should not show",
            text="Update text",
        )
        self.assertEqual(update.poster_display, str(self.maintainer))


@tag("models")
class PartRequestOccurredAtTests(TestDataMixin, TestCase):
    """Tests for PartRequest occurred_at field."""

    def test_occurred_at_defaults_to_now(self):
        """occurred_at defaults to current time when not specified."""
        before = timezone.now()
        part_request = create_part_request(requested_by=self.maintainer, text="Test request")
        after = timezone.now()

        self.assertIsNotNone(part_request.occurred_at)
        self.assertGreaterEqual(part_request.occurred_at, before)
        self.assertLessEqual(part_request.occurred_at, after)

    def test_occurred_at_can_be_set_explicitly(self):
        """occurred_at can be set to a specific datetime (e.g., Discord sync)."""
        specific_date = timezone.now() - timedelta(days=5)
        part_request = create_part_request(
            requested_by=self.maintainer,
            text="Historical request",
            occurred_at=specific_date,
        )
        self.assertEqual(part_request.occurred_at, specific_date)

    def test_part_requests_ordered_by_occurred_at_descending(self):
        """Part requests are ordered by occurred_at descending by default.

        Creates records where created_at order differs from occurred_at order
        to ensure we're actually sorting by occurred_at, not created_at.
        """
        now = timezone.now()

        # Create in this order: middle, oldest, newest
        # If sorting by created_at, we'd get: middle, oldest, newest
        # If sorting by occurred_at desc, we should get: newest, middle, oldest
        middle = create_part_request(
            requested_by=self.maintainer,
            text="Middle request",
            occurred_at=now - timedelta(days=5),
        )
        oldest = create_part_request(
            requested_by=self.maintainer,
            text="Oldest request",
            occurred_at=now - timedelta(days=10),
        )
        newest = create_part_request(
            requested_by=self.maintainer,
            text="Newest request",
            occurred_at=now,
        )

        requests = list(PartRequest.objects.all())
        self.assertEqual(requests, [newest, middle, oldest])


@tag("models")
class PartRequestUpdateOccurredAtTests(TestDataMixin, TestCase):
    """Tests for PartRequestUpdate occurred_at field."""

    def setUp(self):
        super().setUp()
        self.part_request = create_part_request(requested_by=self.maintainer)

    def test_occurred_at_defaults_to_now(self):
        """occurred_at defaults to current time when not specified."""
        before = timezone.now()
        update = create_part_request_update(
            part_request=self.part_request,
            posted_by=self.maintainer,
            text="Test update",
        )
        after = timezone.now()

        self.assertIsNotNone(update.occurred_at)
        self.assertGreaterEqual(update.occurred_at, before)
        self.assertLessEqual(update.occurred_at, after)

    def test_occurred_at_can_be_set_explicitly(self):
        """occurred_at can be set to a specific datetime (e.g., Discord sync)."""
        specific_date = timezone.now() - timedelta(days=5)
        update = create_part_request_update(
            part_request=self.part_request,
            posted_by=self.maintainer,
            text="Historical update",
            occurred_at=specific_date,
        )
        self.assertEqual(update.occurred_at, specific_date)

    def test_updates_ordered_by_occurred_at_descending(self):
        """Updates are ordered by occurred_at descending (newest first).

        Creates records where created_at order differs from occurred_at order
        to ensure we're actually sorting by occurred_at, not created_at.
        """
        now = timezone.now()

        # Create in this order: middle, oldest, newest
        # If sorting by created_at desc, we'd get: newest, oldest, middle
        # If sorting by occurred_at desc, we should get: newest, middle, oldest
        middle = create_part_request_update(
            part_request=self.part_request,
            posted_by=self.maintainer,
            text="Middle update",
            occurred_at=now - timedelta(days=5),
        )
        oldest = create_part_request_update(
            part_request=self.part_request,
            posted_by=self.maintainer,
            text="Oldest update",
            occurred_at=now - timedelta(days=10),
        )
        newest = create_part_request_update(
            part_request=self.part_request,
            posted_by=self.maintainer,
            text="Newest update",
            occurred_at=now,
        )

        updates = list(PartRequestUpdate.objects.all())
        self.assertEqual(updates, [newest, middle, oldest])
