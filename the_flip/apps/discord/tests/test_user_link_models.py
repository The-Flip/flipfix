"""Tests for the DiscordUserLink model."""

from django.db import IntegrityError
from django.test import TestCase, tag

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.core.test_utils import create_maintainer_user
from the_flip.apps.discord.models import DiscordUserLink


@tag("models")
class DiscordUserLinkModelTests(TestCase):
    """Tests for the DiscordUserLink model."""

    def test_create_user_link(self):
        """Can link a Discord user to a maintainer."""
        maintainer_user = create_maintainer_user()
        maintainer = Maintainer.objects.get(user=maintainer_user)

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
        maintainer_user = create_maintainer_user()
        maintainer = Maintainer.objects.get(user=maintainer_user)

        DiscordUserLink.objects.create(
            discord_user_id="987654321",
            discord_username="testuser",
            maintainer=maintainer,
        )

        # Create another maintainer
        maintainer_user2 = create_maintainer_user(username="maintainer2")
        maintainer2 = Maintainer.objects.get(user=maintainer_user2)

        with self.assertRaises(IntegrityError):
            DiscordUserLink.objects.create(
                discord_user_id="987654321",  # Same Discord ID
                discord_username="testuser",
                maintainer=maintainer2,
            )
