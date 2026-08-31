"""Tests for the invite chain traversal and the tree page."""

from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from flipfix.apps.accounts.invite_chain import build_chain, descendant_users
from flipfix.apps.accounts.models import Invitation
from flipfix.apps.core.test_utils import (
    AccessControlTestCase,
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


@tag("models")
class BuildChainTests(TestCase):
    """The forest is assembled from the two chain edges."""

    def test_an_account_with_no_invitation_is_a_root(self):
        """Superusers, terminals and pre-tracking accounts have no inviter."""
        user = create_maintainer_user(username="alone")

        roots = build_chain()

        self.assertEqual([node.user for node in roots], [user])
        self.assertIsNone(roots[0].invitation)
        self.assertIsNone(roots[0].inviter)

    def test_a_two_level_chain_nests(self):
        """A invites B invites C."""
        top = create_maintainer_user(username="aaa")
        middle = create_maintainer_user(username="bbb")
        bottom = create_maintainer_user(username="ccc")
        invite(top, middle)
        invite(middle, bottom)

        roots = build_chain()

        self.assertEqual([node.user for node in roots], [top])
        self.assertEqual([node.user for node in roots[0].children], [middle])
        self.assertEqual([node.user for node in roots[0].children[0].children], [bottom])

    def test_descendant_count_is_transitive(self):
        """The count covers the whole subtree, not just direct invitees."""
        top = create_maintainer_user(username="aaa")
        middle = create_maintainer_user(username="bbb")
        bottom = create_maintainer_user(username="ccc")
        invite(top, middle)
        invite(middle, bottom)

        roots = build_chain()

        self.assertEqual(roots[0].descendant_count, 2)

    def test_a_pending_invitation_creates_no_edge(self):
        """Only accepted invitations put somebody in the tree."""
        inviter = create_maintainer_user(username="aaa")
        Invitation.objects.create(email="nobody@example.com", invited_by=inviter)

        roots = build_chain()

        self.assertEqual(roots[0].children, [])

    def test_an_invitee_of_a_deleted_user_becomes_a_root(self):
        """Losing the inviter must not drop their invitees off the page."""
        inviter = create_maintainer_user(username="aaa")
        invitee = create_maintainer_user(username="bbb")
        invite(inviter, invitee)
        inviter.delete()

        roots = build_chain()

        self.assertEqual([node.user for node in roots], [invitee])


@tag("models")
class DescendantUsersTests(TestCase):
    """The transitive set used by pruning."""

    def test_returns_the_whole_subtree(self):
        """Everyone below, not just direct invitees."""
        top = create_maintainer_user(username="aaa")
        middle = create_maintainer_user(username="bbb")
        bottom = create_maintainer_user(username="ccc")
        invite(top, middle)
        invite(middle, bottom)

        self.assertEqual({user.username for user in descendant_users(top)}, {"bbb", "ccc"})

    def test_excludes_unrelated_accounts(self):
        """A separate branch is untouched."""
        top = create_maintainer_user(username="aaa")
        invitee = create_maintainer_user(username="bbb")
        create_maintainer_user(username="zzz")
        invite(top, invitee)

        self.assertEqual([user.username for user in descendant_users(top)], ["bbb"])

    def test_a_leaf_has_no_descendants(self):
        """Somebody who has invited nobody prunes alone."""
        user = create_maintainer_user(username="aaa")
        self.assertEqual(descendant_users(user), [])


@tag("views")
class InviteTreeViewTests(AccessControlTestCase):
    """Access to and rendering of the tree page."""

    def setUp(self):
        """Build a two-level chain."""
        self.superuser = create_superuser(username="boss")
        self.inviter = create_maintainer_user(username="inviter")
        self.invitee = create_maintainer_user(username="invitee")
        invite(self.inviter, self.invitee)
        self.url = reverse("invite-tree")

    def test_superuser_sees_the_chain(self):
        """Both ends of the edge appear."""
        self.client.force_login(self.superuser)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "inviter")
        self.assertContains(response, "invitee")

    def test_roots_are_labelled_unknown_not_self_registered(self):
        """Missing data reads as unknown. We do not know how they joined."""
        self.client.force_login(self.superuser)

        response = self.client.get(self.url)

        self.assertContains(response, "inviter unknown")

    def test_a_plain_maintainer_is_forbidden(self):
        """The tree is a superuser tool."""
        self.client.force_login(self.inviter)
        self.assertEqual(self.client.get(self.url).status_code, 403)
