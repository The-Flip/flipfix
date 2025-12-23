"""Tests for QR code views."""

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TestDataMixin,
)


@tag("views", "access-control")
class MachineBulkQRCodeViewAccessTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Tests for MachineBulkQRCodeView access control.

    This view generates bulk QR codes for all machines.
    It requires maintainer portal access (staff or superuser).
    """

    def setUp(self):
        super().setUp()
        self.url = reverse("machine-qr-bulk")

    def test_requires_authentication(self):
        """Anonymous users are redirected to login."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_requires_maintainer_access(self):
        """Regular users (non-maintainers) get 403."""
        self.client.force_login(self.regular_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_accessible_to_maintainer(self):
        """Maintainers (staff users) can access the view."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_accessible_to_superuser(self):
        """Superusers can access the view."""
        self.client.force_login(self.superuser)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
