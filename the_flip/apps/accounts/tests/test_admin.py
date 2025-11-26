"""Tests for accounts admin interface."""

from django.test import TestCase, tag

from the_flip.apps.accounts.models import Invitation
from the_flip.apps.core.test_utils import create_staff_user, create_superuser


@tag("admin")
class InvitationAdminTests(TestCase):
    """Tests for the Invitation admin interface."""

    def setUp(self):
        """Set up test data."""
        self.superuser = create_superuser(username="admin")
        self.staff_user = create_staff_user(username="staffuser")
        self.admin_url = "/admin/accounts/invitation/"

    def test_superuser_can_access_invitation_admin(self):
        """Superusers should be able to access the invitation admin."""
        self.client.login(username="admin", password="testpass123")
        response = self.client.get(self.admin_url)
        self.assertEqual(response.status_code, 200)

    def test_staff_user_cannot_access_invitation_admin(self):
        """Non-superuser staff should not see the invitation admin."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.admin_url)
        # Should get 403 since they don't have permission
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_create_invitation(self):
        """Superusers should be able to create invitations."""
        self.client.login(username="admin", password="testpass123")
        add_url = "/admin/accounts/invitation/add/"
        response = self.client.post(add_url, {"email": "invite@example.com"})
        self.assertEqual(response.status_code, 302)  # Redirect after success
        self.assertTrue(Invitation.objects.filter(email="invite@example.com").exists())
