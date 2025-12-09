"""Tests for accounts app models."""

from django.db import IntegrityError
from django.test import TestCase, tag

from the_flip.apps.accounts.models import Invitation, Maintainer
from the_flip.apps.core.test_utils import create_maintainer_user


@tag("models")
class MaintainerModelTests(TestCase):
    """Tests for the Maintainer model."""

    def test_is_shared_account_defaults_to_false(self):
        """New maintainers should not be shared accounts by default."""
        user = create_maintainer_user()
        maintainer = Maintainer.objects.get(user=user)
        self.assertFalse(maintainer.is_shared_account)

    def test_can_create_shared_account(self):
        """Can create a maintainer with is_shared_account=True."""
        user = create_maintainer_user()
        maintainer = Maintainer.objects.get(user=user)
        maintainer.is_shared_account = True
        maintainer.save()

        maintainer.refresh_from_db()
        self.assertTrue(maintainer.is_shared_account)


@tag("models")
class InvitationModelTests(TestCase):
    """Tests for the Invitation model."""

    def test_invitation_generates_unique_token(self):
        """Each invitation should have a unique token."""
        inv1 = Invitation.objects.create(email="user1@example.com")
        inv2 = Invitation.objects.create(email="user2@example.com")
        self.assertNotEqual(inv1.token, inv2.token)
        self.assertTrue(len(inv1.token) > 20)

    def test_invitation_str_pending(self):
        """String representation shows pending status."""
        inv = Invitation.objects.create(email="test@example.com")
        self.assertEqual(str(inv), "test@example.com (pending)")

    def test_invitation_str_used(self):
        """String representation shows used status."""
        inv = Invitation.objects.create(email="test@example.com", used=True)
        self.assertEqual(str(inv), "test@example.com (used)")

    def test_email_must_be_unique(self):
        """Cannot create two invitations with the same email."""
        Invitation.objects.create(email="test@example.com")
        with self.assertRaises(IntegrityError):
            Invitation.objects.create(email="test@example.com")
