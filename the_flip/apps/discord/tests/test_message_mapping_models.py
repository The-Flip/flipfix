"""Tests for the DiscordMessageMapping model."""

from django.test import TestCase, tag

from the_flip.apps.core.test_utils import (
    create_machine,
    create_problem_report,
)
from the_flip.apps.discord.models import DiscordMessageMapping


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

    def test_has_mapping_for_returns_true_when_mapping_exists(self):
        """has_mapping_for() checks by model class and ID without fetching object."""
        from the_flip.apps.maintenance.models import ProblemReport

        report = create_problem_report(machine=self.machine)
        DiscordMessageMapping.mark_processed("123456789", report)

        # Should find the mapping using just the model class and ID
        self.assertTrue(DiscordMessageMapping.has_mapping_for(ProblemReport, report.pk))

    def test_has_mapping_for_returns_false_when_no_mapping(self):
        """has_mapping_for() returns False when no mapping exists."""
        from the_flip.apps.maintenance.models import ProblemReport

        report = create_problem_report(machine=self.machine)

        # No mapping created
        self.assertFalse(DiscordMessageMapping.has_mapping_for(ProblemReport, report.pk))
