"""Tests for the Invitation model and its queryset."""

from datetime import timedelta

from django.test import TestCase, tag
from django.utils import timezone

from flipfix.apps.accounts.models import INVITATION_TTL, Invitation
from flipfix.apps.core.test_utils import create_maintainer_user


@tag("models")
class InvitationModelTests(TestCase):
    """Tests for the Invitation model."""

    def test_invitation_generates_unique_token(self):
        """Each invitation should have a unique token."""
        inv1 = Invitation.objects.create(email="user1@example.com")
        inv2 = Invitation.objects.create(email="user2@example.com")
        self.assertNotEqual(inv1.token, inv2.token)
        self.assertTrue(len(inv1.token) > 20)

    def test_invitation_defaults_to_pending(self):
        """A fresh invitation is pending and expires two weeks out."""
        inv = Invitation.objects.create(email="test@example.com")
        self.assertEqual(inv.status, Invitation.Status.PENDING)
        self.assertTrue(inv.is_pending)
        self.assertAlmostEqual(
            inv.expires_at,
            timezone.now() + INVITATION_TTL,
            delta=timedelta(minutes=1),
        )

    def test_invitation_str_pending(self):
        """String representation shows pending status."""
        inv = Invitation.objects.create(email="test@example.com")
        self.assertEqual(str(inv), "test@example.com (pending)")

    def test_invitation_str_accepted(self):
        """String representation shows accepted status."""
        inv = Invitation.objects.create(email="test@example.com", accepted_at=timezone.now())
        self.assertEqual(str(inv), "test@example.com (accepted)")

    def test_multiple_invitations_per_email_are_allowed(self):
        """Email is deliberately not unique.

        The old unique constraint made re-inviting somebody raise
        IntegrityError. The rule we want ("one *open* invitation per
        address") depends on expiry, so it is enforced by the create view
        reusing the pending invitation instead.
        """
        Invitation.objects.create(email="test@example.com", revoked_at=timezone.now())
        second = Invitation.objects.create(email="test@example.com")
        self.assertEqual(Invitation.objects.filter(email="test@example.com").count(), 2)
        self.assertTrue(second.is_pending)


@tag("models")
class InvitationStatusTests(TestCase):
    """The derived status covers all four states, in the right priority."""

    def test_accepted(self):
        """An invitation with accepted_at reads as accepted."""
        inv = Invitation.objects.create(email="a@example.com", accepted_at=timezone.now())
        self.assertEqual(inv.status, Invitation.Status.ACCEPTED)
        self.assertEqual(inv.status_label, "Accepted")
        self.assertFalse(inv.is_pending)

    def test_revoked(self):
        """An invitation with revoked_at reads as revoked."""
        inv = Invitation.objects.create(email="b@example.com", revoked_at=timezone.now())
        self.assertEqual(inv.status, Invitation.Status.REVOKED)
        self.assertFalse(inv.is_pending)

    def test_expired(self):
        """An invitation past expires_at reads as expired."""
        inv = Invitation.objects.create(
            email="c@example.com", expires_at=timezone.now() - timedelta(seconds=1)
        )
        self.assertEqual(inv.status, Invitation.Status.EXPIRED)
        self.assertFalse(inv.is_pending)

    def test_revoked_beats_expired(self):
        """Revoking is the deliberate act, so it is what gets reported."""
        inv = Invitation.objects.create(
            email="d@example.com",
            revoked_at=timezone.now(),
            expires_at=timezone.now() - timedelta(days=1),
        )
        self.assertEqual(inv.status, Invitation.Status.REVOKED)

    def test_revoked_beats_accepted(self):
        """A revoked invitation reads as revoked even if it was accepted."""
        inv = Invitation.objects.create(
            email="e@example.com", revoked_at=timezone.now(), accepted_at=timezone.now()
        )
        self.assertEqual(inv.status, Invitation.Status.REVOKED)


@tag("models")
class InvitationQuerySetTests(TestCase):
    """pending() is the single source of truth for "still usable"."""

    def setUp(self):
        """Create one invitation in each state."""
        self.inviter = create_maintainer_user(username="inviter")
        self.open_invite = Invitation.objects.create(
            email="open@example.com", invited_by=self.inviter
        )
        self.accepted = Invitation.objects.create(
            email="accepted@example.com", invited_by=self.inviter, accepted_at=timezone.now()
        )
        self.revoked = Invitation.objects.create(
            email="revoked@example.com", invited_by=self.inviter, revoked_at=timezone.now()
        )
        self.expired = Invitation.objects.create(
            email="expired@example.com",
            invited_by=self.inviter,
            expires_at=timezone.now() - timedelta(seconds=1),
        )

    def test_pending_returns_only_open_invitations(self):
        """Accepted, revoked and expired invitations are all excluded."""
        self.assertQuerySetEqual(Invitation.objects.pending(), [self.open_invite])

    def test_accepted_returns_only_accepted(self):
        """accepted() matches on accepted_at, not on status."""
        self.assertQuerySetEqual(Invitation.objects.accepted(), [self.accepted])

    def test_sent_by_scopes_to_one_inviter(self):
        """sent_by() filters on invited_by."""
        other = create_maintainer_user(username="other")
        Invitation.objects.create(email="theirs@example.com", invited_by=other)
        self.assertEqual(Invitation.objects.sent_by(self.inviter).count(), 4)
        self.assertEqual(Invitation.objects.sent_by(other).count(), 1)
