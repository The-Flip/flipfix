"""Tests for parts feature flag behavior."""

from constance.test import override_config
from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.core.test_utils import (
    TestDataMixin,
    create_part_request,
)


@tag("feature_flags")
class PartsFeatureFlagTests(TestDataMixin, TestCase):
    """Tests for the PARTS_ENABLED feature flag."""

    def test_nav_link_hidden_when_disabled(self):
        """Parts nav link is hidden when PARTS_ENABLED is False."""
        self.client.force_login(self.maintainer_user)

        with override_config(PARTS_ENABLED=False):
            response = self.client.get(reverse("maintainer-machine-list"))
            # The nav link to parts should not be present
            self.assertNotContains(response, 'href="/parts/"')

    def test_nav_link_shown_when_enabled(self):
        """Parts nav link is shown when PARTS_ENABLED is True."""
        self.client.force_login(self.maintainer_user)

        with override_config(PARTS_ENABLED=True):
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

        with override_config(PARTS_ENABLED=False):
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

        with override_config(PARTS_ENABLED=True):
            logs, reports, part_requests, part_updates = get_activity_entries(self.machine)
            # Parts should be included
            self.assertEqual(list(part_requests), [part])
