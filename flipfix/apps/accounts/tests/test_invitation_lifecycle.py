"""Tests for resending, revoking, and viewing a single invitation."""

from datetime import timedelta

from django.core import mail
from django.test import Client, tag
from django.urls import reverse
from django.utils import timezone

from flipfix.apps.accounts.models import Invitation
from flipfix.apps.core.test_utils import (
    AccessControlTestCase,
    create_maintainer_user,
    create_superuser,
)


@tag("views")
class InviteDetailTests(AccessControlTestCase):
    """The detail page and the link it hands out."""

    def setUp(self):
        """Log in a maintainer holding one open invitation."""
        self.inviter = create_maintainer_user(username="inviter")
        self.client.force_login(self.inviter)
        self.invitation = Invitation.objects.create(
            email="new@example.com", invited_by=self.inviter
        )

    def test_shows_an_absolute_shareable_link(self):
        """The copyable link must be absolute — it gets pasted elsewhere."""
        response = self.client.get(self.invitation.get_absolute_url())

        register_path = reverse("invitation-register", kwargs={"token": self.invitation.token})
        self.assertContains(response, f"http://testserver{register_path}")

    def test_hides_the_link_once_revoked(self):
        """A dead link must not be offered for copying."""
        self.invitation.revoked_at = timezone.now()
        self.invitation.save()

        response = self.client.get(self.invitation.get_absolute_url())

        self.assertNotContains(response, self.invitation.token)
        self.assertContains(response, "no longer works")

    def test_hides_the_link_once_expired(self):
        """Same for an expired invitation."""
        self.invitation.expires_at = timezone.now() - timedelta(seconds=1)
        self.invitation.save()

        response = self.client.get(self.invitation.get_absolute_url())

        self.assertNotContains(response, self.invitation.token)


@tag("views")
class InviteResendTests(AccessControlTestCase):
    """Resending an invitation."""

    def setUp(self):
        """Log in a maintainer holding one open invitation."""
        self.inviter = create_maintainer_user(username="inviter")
        self.client.force_login(self.inviter)
        self.invitation = Invitation.objects.create(
            email="new@example.com",
            invited_by=self.inviter,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.resend_url = reverse("invite-resend", kwargs={"pk": self.invitation.pk})

    def test_keeps_the_same_token(self):
        """Somebody holding the first email must not find their link broken."""
        original_token = self.invitation.token

        self.client.post(self.resend_url)

        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.token, original_token)

    def test_extends_the_expiry_and_stamps_last_sent_at(self):
        """Resending gives the recipient a fresh two weeks."""
        original_expiry = self.invitation.expires_at

        self.client.post(self.resend_url)

        self.invitation.refresh_from_db()
        self.assertGreater(self.invitation.expires_at, original_expiry)
        self.assertIsNotNone(self.invitation.last_sent_at)
        self.assertEqual(len(mail.outbox), 1)

    def test_refuses_to_resend_an_accepted_invitation(self):
        """There is nothing left to send once somebody has signed up."""
        self.invitation.accepted_at = timezone.now()
        self.invitation.save()

        self.client.post(self.resend_url)

        self.assertEqual(len(mail.outbox), 0)

    def test_refuses_to_resend_a_revoked_invitation(self):
        """Revoking must not be undoable by pressing resend."""
        self.invitation.revoked_at = timezone.now()
        self.invitation.save()

        self.client.post(self.resend_url)

        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.status, Invitation.Status.REVOKED)
        self.assertEqual(len(mail.outbox), 0)


@tag("views")
class InviteRevokeTests(AccessControlTestCase):
    """Revoking an invitation."""

    def setUp(self):
        """Log in a maintainer holding one open invitation."""
        self.inviter = create_maintainer_user(username="inviter")
        self.client.force_login(self.inviter)
        self.invitation = Invitation.objects.create(
            email="new@example.com", invited_by=self.inviter
        )
        self.revoke_url = reverse("invite-revoke", kwargs={"pk": self.invitation.pk})

    def test_revoking_kills_the_link(self):
        """After revoking, the registration URL stops working."""
        self.client.post(self.revoke_url)

        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.status, Invitation.Status.REVOKED)

        # A fresh client rather than self.client.logout(): the project's
        # logout signal posts a message, which needs a real request.
        anonymous = Client()
        register_url = reverse("invitation-register", kwargs={"token": self.invitation.token})
        response = anonymous.get(register_url, follow=True)
        self.assertRedirects(response, reverse("login"))

    def test_cannot_revoke_an_accepted_invitation(self):
        """An accepted invitation has no link left to revoke."""
        self.invitation.accepted_at = timezone.now()
        self.invitation.save()

        self.client.post(self.revoke_url)

        self.invitation.refresh_from_db()
        self.assertIsNone(self.invitation.revoked_at)


@tag("views")
class InviteOwnershipTests(AccessControlTestCase):
    """A maintainer may only act on their own invitations."""

    def setUp(self):
        """Two maintainers, one invitation belonging to the other one."""
        self.owner = create_maintainer_user(username="owner")
        self.other = create_maintainer_user(username="other")
        self.invitation = Invitation.objects.create(
            email="theirs@example.com", invited_by=self.owner
        )

    def test_another_maintainer_cannot_open_it(self):
        """Scoped out of the queryset, so it 404s rather than 403s.

        404 is deliberate: a 403 would confirm that an invitation with that
        id exists and who it belongs to.
        """
        self.client.force_login(self.other)
        response = self.client.get(self.invitation.get_absolute_url())
        self.assertEqual(response.status_code, 404)

    def test_another_maintainer_cannot_revoke_it(self):
        """Ownership is enforced on the write paths too, not just the read."""
        self.client.force_login(self.other)
        url = reverse("invite-revoke", kwargs={"pk": self.invitation.pk})

        response = self.client.post(url)

        self.assertEqual(response.status_code, 404)
        self.invitation.refresh_from_db()
        self.assertIsNone(self.invitation.revoked_at)

    def test_another_maintainer_cannot_resend_it(self):
        """Same for resend."""
        self.client.force_login(self.other)
        url = reverse("invite-resend", kwargs={"pk": self.invitation.pk})

        response = self.client.post(url)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(len(mail.outbox), 0)

    def test_the_list_shows_only_your_own(self):
        """The listing is scoped the same way."""
        Invitation.objects.create(email="mine@example.com", invited_by=self.other)
        self.client.force_login(self.other)

        response = self.client.get(reverse("invite-list"))

        self.assertContains(response, "mine@example.com")
        self.assertNotContains(response, "theirs@example.com")

    def test_a_superuser_sees_everything(self):
        """Superusers are the escalation path when a maintainer is unavailable."""
        self.client.force_login(create_superuser(username="boss"))

        response = self.client.get(self.invitation.get_absolute_url())

        self.assertEqual(response.status_code, 200)
