"""Tests for the user-directory visibility predicates and capability checks.

Covers the queryset method, the per-user predicate, and the permission
helpers that gate the upcoming ``/users`` directory and ``/users/<username>``
profile pages. These predicates are load-bearing for §5/§6 views, so
locking down the contract here protects those views from regressions.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.test import TestCase, tag

from flipfix.apps.accounts.models import Maintainer
from flipfix.apps.accounts.permissions import (
    can_view_user_profiles,
    is_in_user_directory,
)
from flipfix.apps.core.test_utils import (
    create_maintainer_user,
    create_superuser,
    create_user,
)

User = get_user_model()


@tag("models")
class MaintainerQuerySetInUserDirectoryTests(TestCase):
    """Tests for ``Maintainer.objects.in_user_directory()``.

    Single source of truth for directory visibility: active user, member
    of the Maintainers group, not a shared terminal account.
    """

    def test_active_maintainer_included(self):
        user = create_maintainer_user(username="alice")
        self.assertIn(user.maintainer, Maintainer.objects.in_user_directory())

    def test_inactive_user_excluded(self):
        user = create_maintainer_user(username="bob")
        user.is_active = False
        user.save()
        self.assertNotIn(user.maintainer, Maintainer.objects.in_user_directory())

    def test_shared_account_excluded(self):
        user = create_maintainer_user(username="kiosk")
        user.maintainer.is_shared_account = True
        user.maintainer.save()
        self.assertNotIn(user.maintainer, Maintainer.objects.in_user_directory())

    def test_user_outside_maintainers_group_excluded(self):
        """A Maintainer row whose user isn't in the Maintainers group is excluded.

        Edge case: a Maintainer row can exist without group membership if
        the row is created out-of-band (e.g., admin). The directory only
        shows users actually in the group.
        """
        user = create_user(username="orphan")
        Maintainer.objects.create(user=user)
        # Note: no group assignment
        self.assertNotIn(user.maintainer, Maintainer.objects.in_user_directory())


@tag("models")
class IsInUserDirectoryTests(TestCase):
    """Tests for ``is_in_user_directory(user)``."""

    def test_anonymous_user_false(self):
        self.assertFalse(is_in_user_directory(AnonymousUser()))

    def test_non_maintainer_user_false(self):
        user = create_user(username="visitor")
        self.assertFalse(is_in_user_directory(user))

    def test_active_maintainer_true(self):
        user = create_maintainer_user(username="alice")
        self.assertTrue(is_in_user_directory(user))

    def test_shared_account_false(self):
        user = create_maintainer_user(username="kiosk")
        user.maintainer.is_shared_account = True
        user.maintainer.save()
        self.assertFalse(is_in_user_directory(user))

    def test_inactive_maintainer_false(self):
        user = create_maintainer_user(username="bob")
        user.is_active = False
        user.save()
        self.assertFalse(is_in_user_directory(user))


@tag("models")
class CanViewUserProfilesTests(TestCase):
    """Tests for ``can_view_user_profiles(user)``."""

    def test_maintainer_can_view(self):
        """Maintainers have the permission via the group grant in migration 0009."""
        user = create_maintainer_user(username="alice")
        self.assertTrue(can_view_user_profiles(user))

    def test_non_maintainer_cannot_view(self):
        user = create_user(username="visitor")
        self.assertFalse(can_view_user_profiles(user))

    def test_anonymous_cannot_view(self):
        self.assertFalse(can_view_user_profiles(AnonymousUser()))

    def test_superuser_can_view(self):
        """Superusers auto-pass via ``has_perm()``."""
        user = create_superuser(username="root")
        self.assertTrue(can_view_user_profiles(user))


@tag("models")
class MaintainersGroupHasViewProfilesPermissionTests(TestCase):
    """The Maintainers group must hold ``can_view_user_profiles``.

    This is the deployed outcome of migration 0009. If a future migration
    edits the grant table or someone reverts the migration, this test
    fails loudly.
    """

    def test_maintainers_group_has_permission(self):
        group = Group.objects.get(name="Maintainers")
        perm = Permission.objects.get(
            codename="can_view_user_profiles",
            content_type__app_label="accounts",
            content_type__model="maintainer",
        )
        self.assertIn(perm, group.permissions.all())
