"""Tests for Discord models."""

from django.db import IntegrityError
from django.test import TestCase, tag

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.core.test_utils import (
    create_machine,
    create_maintainer_user,
    create_problem_report,
)
from the_flip.apps.discord.models import DiscordMessageMapping, DiscordUserLink


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


@tag("models")
class DiscordMessageMappingTests(TestCase):
    """Tests for the DiscordMessageMapping model."""

    def setUp(self):
        self.machine = create_machine()

    def test_was_created_from_discord_returns_true_when_mapping_exists(self):
        """Returns True when record has a DiscordMessageMapping."""
        report = create_problem_report(machine=self.machine)

        # Create a mapping linking this report to a Discord message
        DiscordMessageMapping.mark_processed("123456789", report)

        self.assertTrue(DiscordMessageMapping.was_created_from_discord(report))

    def test_was_created_from_discord_returns_false_when_no_mapping(self):
        """Returns False when record has no DiscordMessageMapping."""
        report = create_problem_report(machine=self.machine)

        # No mapping created - this is a web-originated record
        self.assertFalse(DiscordMessageMapping.was_created_from_discord(report))

    def test_multiple_records_from_same_message(self):
        """One Discord message can create multiple records.

        When Claude analyzes a Discord message, it may suggest multiple records
        (e.g., problems on different machines). Each should get its own mapping.
        """
        from the_flip.apps.core.test_utils import create_log_entry

        report = create_problem_report(machine=self.machine)
        log_entry = create_log_entry(machine=self.machine)

        # Same Discord message creates both records - should NOT raise IntegrityError
        DiscordMessageMapping.mark_processed("same_msg_123", report)
        DiscordMessageMapping.mark_processed("same_msg_123", log_entry)

        # Both should be marked as Discord-originated
        self.assertTrue(DiscordMessageMapping.was_created_from_discord(report))
        self.assertTrue(DiscordMessageMapping.was_created_from_discord(log_entry))

        # is_processed should return True for this message
        self.assertTrue(DiscordMessageMapping.is_processed("same_msg_123"))
