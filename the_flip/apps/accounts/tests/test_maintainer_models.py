"""Tests for the Maintainer model."""

from django.test import TestCase, tag

from the_flip.apps.accounts.models import Maintainer
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
