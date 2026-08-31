"""Tests for creating invitations as a maintainer."""

from django.contrib.auth.models import Group, Permission
from django.core import mail
from django.test import tag
from django.urls import reverse
from django.utils import timezone

from flipfix.apps.accounts.models import MAX_OUTSTANDING_INVITES_PER_USER, Invitation
from flipfix.apps.core.test_utils import (
    AccessControlTestCase,
    create_maintainer_user,
    create_superuser,
    create_user,
)


@tag("views")
class InviteCreateAccessTests(AccessControlTestCase):
    """Who may reach the invite pages."""

    def setUp(self):
        """Create the URLs under test."""
        self.list_url = reverse("invite-list")
        self.create_url = reverse("invite-create")

    def test_maintainer_can_reach_the_invite_pages(self):
        """The Maintainers group carries can_invite_users."""
        self.client.force_login(create_maintainer_user())
        self.assertEqual(self.client.get(self.list_url).status_code, 200)
        self.assertEqual(self.client.get(self.create_url).status_code, 200)

    def test_anonymous_is_redirected_to_login(self):
        """Invite pages are not public."""
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_non_maintainer_is_forbidden(self):
        """An authenticated user without portal access gets a 403."""
        self.client.force_login(create_user())
        self.assertEqual(self.client.get(self.list_url).status_code, 403)

    def test_maintainer_without_the_permission_is_forbidden(self):
        """Revoking can_invite_users from a maintainer actually shuts them out.

        This is the whole point of using a permission instead of hanging the
        feature off portal access: one bad actor can be stopped without
        losing their ability to do maintenance work.
        """
        user = create_maintainer_user()
        group = Group.objects.get(name="Maintainers")
        permission = Permission.objects.get(codename="can_invite_users")
        group.permissions.remove(permission)
        self.addCleanup(group.permissions.add, permission)

        self.client.force_login(user)
        self.assertEqual(self.client.get(self.list_url).status_code, 403)
        self.assertEqual(self.client.get(self.create_url).status_code, 403)


@tag("views")
class InviteCreateTests(AccessControlTestCase):
    """Creating an invitation."""

    def setUp(self):
        """Log in a maintainer."""
        self.inviter = create_maintainer_user(username="inviter")
        self.client.force_login(self.inviter)
        self.create_url = reverse("invite-create")

    def test_creates_invitation_attributed_to_the_inviter(self):
        """The chain edge is recorded at creation time."""
        response = self.client.post(self.create_url, {"email": "new@example.com"})

        invitation = Invitation.objects.get(email="new@example.com")
        self.assertEqual(invitation.invited_by, self.inviter)
        self.assertTrue(invitation.is_pending)
        self.assertRedirects(response, invitation.get_absolute_url())

    def test_sends_the_invitation_email(self):
        """Creating an invitation emails the link and stamps last_sent_at."""
        self.client.post(self.create_url, {"email": "new@example.com"})

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["new@example.com"])
        invitation = Invitation.objects.get(email="new@example.com")
        self.assertIsNotNone(invitation.last_sent_at)

    def test_rejects_an_address_that_already_has_an_account(self):
        """Inviting an existing user is a mistake worth catching."""
        create_user(username="existing", email="taken@example.com")

        response = self.client.post(self.create_url, {"email": "taken@example.com"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already has an account")
        self.assertFalse(Invitation.objects.filter(email="taken@example.com").exists())

    def test_reuses_an_existing_pending_invitation(self):
        """Re-inviting somebody resends, rather than minting a second token."""
        existing = Invitation.objects.create(email="again@example.com", invited_by=self.inviter)

        self.client.post(self.create_url, {"email": "again@example.com"})

        self.assertEqual(Invitation.objects.filter(email="again@example.com").count(), 1)
        existing.refresh_from_db()
        self.assertIsNotNone(existing.last_sent_at)
        self.assertEqual(len(mail.outbox), 1)

    def test_a_revoked_invitation_does_not_block_a_new_one(self):
        """Only *open* invitations are reused."""
        Invitation.objects.create(
            email="again@example.com", invited_by=self.inviter, revoked_at=timezone.now()
        )

        self.client.post(self.create_url, {"email": "again@example.com"})

        self.assertEqual(Invitation.objects.filter(email="again@example.com").count(), 2)

    def test_enforces_the_outstanding_invitation_cap(self):
        """A maintainer cannot hold more than the cap in live invitations."""
        for index in range(MAX_OUTSTANDING_INVITES_PER_USER):
            Invitation.objects.create(email=f"p{index}@example.com", invited_by=self.inviter)

        response = self.client.post(self.create_url, {"email": "onemore@example.com"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "which is the maximum")
        self.assertFalse(Invitation.objects.filter(email="onemore@example.com").exists())

    def test_the_cap_counts_only_open_invitations(self):
        """Accepted and revoked invitations don't use up the allowance."""
        for index in range(MAX_OUTSTANDING_INVITES_PER_USER):
            Invitation.objects.create(
                email=f"p{index}@example.com",
                invited_by=self.inviter,
                accepted_at=timezone.now(),
            )

        self.client.post(self.create_url, {"email": "onemore@example.com"})

        self.assertTrue(Invitation.objects.filter(email="onemore@example.com").exists())

    def test_superusers_are_exempt_from_the_cap(self):
        """A superuser onboarding a whole intake shouldn't have to fight it."""
        superuser = create_superuser(username="boss")
        for index in range(MAX_OUTSTANDING_INVITES_PER_USER):
            Invitation.objects.create(email=f"s{index}@example.com", invited_by=superuser)

        self.client.force_login(superuser)
        self.client.post(self.create_url, {"email": "onemore@example.com"})

        self.assertTrue(Invitation.objects.filter(email="onemore@example.com").exists())
