"""Tests for pruning an account together with everyone it invited."""

from django.test import tag
from django.urls import reverse
from django.utils import timezone

from flipfix.apps.accounts.models import Invitation
from flipfix.apps.core.test_utils import (
    AccessControlTestCase,
    create_log_entry,
    create_machine,
    create_machine_model,
    create_maintainer_user,
    create_superuser,
)


def invite(inviter, invitee):
    """Record that ``inviter`` brought ``invitee`` in."""
    return Invitation.objects.create(
        email=f"{invitee.username}@example.com",
        invited_by=inviter,
        accepted_by=invitee,
        accepted_at=timezone.now(),
    )


@tag("views")
class InvitePruneTests(AccessControlTestCase):
    """Deactivating a subtree."""

    def setUp(self):
        """A superuser plus a three-deep chain, and one unrelated account."""
        self.superuser = create_superuser(username="boss")
        self.spammer = create_maintainer_user(username="spammer")
        self.recruit = create_maintainer_user(username="recruit")
        self.subrecruit = create_maintainer_user(username="subrecruit")
        self.bystander = create_maintainer_user(username="bystander")
        invite(self.spammer, self.recruit)
        invite(self.recruit, self.subrecruit)

        self.url = reverse("invite-prune", kwargs={"pk": self.spammer.pk})
        self.client.force_login(self.superuser)

    def test_confirmation_page_lists_everyone_affected(self):
        """No surprises: the superuser sees the blast radius before acting."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "spammer")
        self.assertContains(response, "recruit")
        self.assertContains(response, "subrecruit")
        self.assertNotContains(response, "bystander")

    def test_deactivates_the_whole_subtree(self):
        """Transitive, not just direct invitees."""
        self.client.post(self.url)

        for user in (self.spammer, self.recruit, self.subrecruit):
            user.refresh_from_db()
            self.assertFalse(user.is_active, f"{user.username} should be deactivated")

    def test_leaves_unrelated_accounts_alone(self):
        """Pruning is scoped to the chain, not a blanket lockout."""
        self.client.post(self.url)

        self.bystander.refresh_from_db()
        self.assertTrue(self.bystander.is_active)

    def test_revokes_their_outstanding_invitations(self):
        """A pruned account's live links must stop working too."""
        pending = Invitation.objects.create(email="next@example.com", invited_by=self.recruit)

        self.client.post(self.url)

        pending.refresh_from_db()
        self.assertEqual(pending.status, Invitation.Status.REVOKED)

    def test_deletes_nothing(self):
        """The history is the reason the chain exists. It stays."""
        machine = create_machine(model=create_machine_model())
        entry = create_log_entry(machine=machine, text="Real work", created_by=self.recruit)

        self.client.post(self.url)

        entry.refresh_from_db()
        self.assertEqual(entry.text, "Real work")
        self.assertTrue(Invitation.objects.filter(accepted_by=self.recruit).exists())

    def test_refuses_to_prune_yourself(self):
        """A superuser locking themselves out is not a useful outcome."""
        url = reverse("invite-prune", kwargs={"pk": self.superuser.pk})

        self.client.post(url)

        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_active)

    def test_refuses_to_prune_a_superuser(self):
        """Demote first; that way the decision is explicit and separate."""
        other_admin = create_superuser(username="other-boss")
        url = reverse("invite-prune", kwargs={"pk": other_admin.pk})

        self.client.post(url)

        other_admin.refresh_from_db()
        self.assertTrue(other_admin.is_active)

    def test_a_plain_maintainer_cannot_prune(self):
        """Pruning is a superuser action."""
        self.client.force_login(self.bystander)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 403)
        self.spammer.refresh_from_db()
        self.assertTrue(self.spammer.is_active)
