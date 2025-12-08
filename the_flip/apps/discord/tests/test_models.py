"""Tests for Discord models."""

from django.db import IntegrityError
from django.test import TestCase

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.core.test_utils import create_staff_user
from the_flip.apps.discord.models import DiscordUserLink


class DiscordUserLinkModelTests(TestCase):
    """Tests for the DiscordUserLink model."""

    def test_create_user_link(self):
        """Can link a Discord user to a maintainer."""
        staff_user = create_staff_user()
        maintainer = Maintainer.objects.get(user=staff_user)

        link = DiscordUserLink.objects.create(
            discord_user_id="987654321",
            discord_username="testuser",
            discord_display_name="Test User",
            maintainer=maintainer,
        )
        self.assertIn("Test User", str(link))
        self.assertIn(str(maintainer), str(link))

    def test_unique_discord_user_id(self):
        """Cannot link same Discord user twice."""
        staff_user = create_staff_user()
        maintainer = Maintainer.objects.get(user=staff_user)

        DiscordUserLink.objects.create(
            discord_user_id="987654321",
            discord_username="testuser",
            maintainer=maintainer,
        )

        # Create another maintainer
        staff_user2 = create_staff_user(username="staff2")
        maintainer2 = Maintainer.objects.get(user=staff_user2)

        with self.assertRaises(IntegrityError):
            DiscordUserLink.objects.create(
                discord_user_id="987654321",  # Same Discord ID
                discord_username="testuser",
                maintainer=maintainer2,
            )
