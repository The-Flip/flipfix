"""Tests for Discord record creation."""

from django.test import TestCase, override_settings, tag

from the_flip.apps.core.test_utils import (
    create_machine,
    create_maintainer_user,
    create_part_request,
    create_problem_report,
)
from the_flip.apps.discord.models import DiscordMessageMapping
from the_flip.apps.discord.records import (
    _create_log_entry,
    _create_part_request_update,
)
from the_flip.apps.maintenance.models import LogEntry


@tag("tasks")
class LogEntryParentLinkingTests(TestCase):
    """Tests for log entry linking to parent problem reports."""

    def setUp(self):
        self.machine = create_machine()
        self.user = create_maintainer_user()
        self.maintainer = self.user.maintainer

    def test_log_entry_links_to_problem_report(self):
        """Log entry created with parent_record_id links to that problem report."""
        problem_report = create_problem_report(machine=self.machine)

        log_entry = _create_log_entry(
            machine=self.machine,
            description="Fixed the issue",
            maintainer=self.maintainer,
            discord_display_name=None,
            parent_record_id=problem_report.pk,
        )

        self.assertEqual(log_entry.problem_report, problem_report)
        self.assertEqual(log_entry.problem_report.pk, problem_report.pk)

    def test_log_entry_without_parent_has_no_problem_report(self):
        """Log entry created without parent_record_id has no linked problem report."""
        log_entry = _create_log_entry(
            machine=self.machine,
            description="Fixed something",
            maintainer=self.maintainer,
            discord_display_name=None,
            parent_record_id=None,
        )

        self.assertIsNone(log_entry.problem_report)

    def test_log_entry_with_nonexistent_parent_has_no_problem_report(self):
        """Log entry with invalid parent_record_id gracefully has no link (logs warning)."""
        log_entry = _create_log_entry(
            machine=self.machine,
            description="Fixed something",
            maintainer=self.maintainer,
            discord_display_name=None,
            parent_record_id=99999,  # Non-existent ID
        )

        # Should not raise, just logs warning and creates without link
        self.assertIsNone(log_entry.problem_report)

    def test_log_entry_uses_maintainer_when_provided(self):
        """Log entry associates maintainer when provided."""
        log_entry = _create_log_entry(
            machine=self.machine,
            description="Fixed the flipper",
            maintainer=self.maintainer,
            discord_display_name="Discord User",
            parent_record_id=None,
        )

        self.assertIn(self.maintainer, log_entry.maintainers.all())
        # maintainer_names should be empty when maintainer is linked
        self.assertEqual(log_entry.maintainer_names, "")

    def test_log_entry_uses_fallback_name_when_no_maintainer(self):
        """Log entry uses discord_display_name as fallback when no maintainer."""
        log_entry = _create_log_entry(
            machine=self.machine,
            description="Fixed the flipper",
            maintainer=None,
            discord_display_name="Discord User",
            parent_record_id=None,
        )

        self.assertEqual(log_entry.maintainers.count(), 0)
        self.assertEqual(log_entry.maintainer_names, "Discord User")

    def test_log_entry_uses_discord_fallback_when_no_display_name(self):
        """Log entry uses 'Discord' as fallback when no maintainer or display name."""
        log_entry = _create_log_entry(
            machine=self.machine,
            description="Fixed the flipper",
            maintainer=None,
            discord_display_name=None,
            parent_record_id=None,
        )

        self.assertEqual(log_entry.maintainer_names, "Discord")


@tag("tasks")
class PartRequestUpdateParentLinkingTests(TestCase):
    """Tests for part request update linking to parent part requests."""

    def setUp(self):
        self.machine = create_machine()
        self.user = create_maintainer_user()
        self.maintainer = self.user.maintainer

    def test_update_links_to_part_request(self):
        """Part request update links to the specified parent part request."""
        part_request = create_part_request(
            machine=self.machine,
            requested_by=self.maintainer,
        )

        update = _create_part_request_update(
            parent_record_id=part_request.pk,
            description="Parts arrived!",
            maintainer=self.maintainer,
        )

        self.assertEqual(update.part_request, part_request)
        self.assertEqual(update.part_request.pk, part_request.pk)

    def test_update_with_nonexistent_parent_raises(self):
        """Part request update with invalid parent_record_id raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            _create_part_request_update(
                parent_record_id=99999,  # Non-existent ID
                description="Parts arrived!",
                maintainer=self.maintainer,
            )

        self.assertIn("Part request not found", str(ctx.exception))


@tag("tasks")
@override_settings(SITE_URL="https://flipfix.example.com")
class MultiMessageSourceTrackingTests(TestCase):
    """Tests for marking multiple source messages as processed."""

    def setUp(self):
        self.machine = create_machine()

    def test_all_source_messages_marked_processed(self):
        """All source_message_ids are marked as processed."""
        from asgiref.sync import async_to_sync

        from the_flip.apps.discord.llm import RecordSuggestion, RecordType
        from the_flip.apps.discord.records import create_record
        from the_flip.apps.discord.types import DiscordUserInfo

        # Create suggestion with multiple source message IDs
        suggestion = RecordSuggestion(
            record_type=RecordType.PROBLEM_REPORT,
            description="Flipper broken across multiple messages",
            source_message_ids=["111111111", "222222222", "333333333"],
            author_id="discord123",
            slug=self.machine.slug,
        )

        discord_user = DiscordUserInfo(
            user_id="discord123",
            username="testuser",
            display_name="Test User",
        )

        # Call the async function synchronously
        result = async_to_sync(create_record)(suggestion, discord_user)

        # All three messages should be marked as processed
        self.assertTrue(DiscordMessageMapping.is_processed("111111111"))
        self.assertTrue(DiscordMessageMapping.is_processed("222222222"))
        self.assertTrue(DiscordMessageMapping.is_processed("333333333"))

        # Verify all map to the same record
        from the_flip.apps.maintenance.models import ProblemReport

        self.assertTrue(DiscordMessageMapping.has_mapping_for(ProblemReport, result.record_id))

    def test_single_source_message_marked_processed(self):
        """Single source_message_id is marked as processed."""
        from asgiref.sync import async_to_sync

        from the_flip.apps.discord.llm import RecordSuggestion, RecordType
        from the_flip.apps.discord.records import create_record
        from the_flip.apps.discord.types import DiscordUserInfo

        suggestion = RecordSuggestion(
            record_type=RecordType.PROBLEM_REPORT,
            description="Something broken",
            source_message_ids=["999999999"],
            author_id="discord456",
            slug=self.machine.slug,
        )

        discord_user = DiscordUserInfo(
            user_id="discord456",
            username="anotheruser",
            display_name="Another User",
        )

        async_to_sync(create_record)(suggestion, discord_user)

        self.assertTrue(DiscordMessageMapping.is_processed("999999999"))

    def test_log_entry_with_parent_links_correctly(self):
        """Log entry created via create_record links to parent problem report."""
        from asgiref.sync import async_to_sync

        from the_flip.apps.discord.llm import RecordSuggestion, RecordType
        from the_flip.apps.discord.records import create_record
        from the_flip.apps.discord.types import DiscordUserInfo

        # Create a problem report to link to
        problem_report = create_problem_report(machine=self.machine)

        suggestion = RecordSuggestion(
            record_type=RecordType.LOG_ENTRY,
            description="Fixed the issue reported earlier",
            source_message_ids=["444444444"],
            author_id="discord789",
            slug=self.machine.slug,
            parent_record_id=problem_report.pk,
        )

        discord_user = DiscordUserInfo(
            user_id="discord789",
            username="fixer",
            display_name="The Fixer",
        )

        result = async_to_sync(create_record)(suggestion, discord_user)

        # Verify the log entry links to the problem report
        log_entry = LogEntry.objects.get(pk=result.record_id)
        self.assertEqual(log_entry.problem_report, problem_report)

    def test_part_request_update_links_correctly(self):
        """Part request update created via create_record links to parent."""
        from asgiref.sync import async_to_sync

        from the_flip.apps.discord.llm import RecordSuggestion, RecordType
        from the_flip.apps.discord.records import create_record
        from the_flip.apps.discord.types import DiscordUserInfo

        user = create_maintainer_user(username="partsuser")
        maintainer = user.maintainer

        # Create a part request to update
        part_request = create_part_request(
            machine=self.machine,
            requested_by=maintainer,
        )

        suggestion = RecordSuggestion(
            record_type=RecordType.PART_REQUEST_UPDATE,
            description="Parts arrived today!",
            source_message_ids=["555555555"],
            author_id="discord_parts",
            slug=None,  # Optional for updates
            parent_record_id=part_request.pk,
        )

        # Use matching username so maintainer gets linked
        discord_user = DiscordUserInfo(
            user_id="discord_parts",
            username="partsuser",
            display_name="Parts User",
        )

        result = async_to_sync(create_record)(suggestion, discord_user)

        # Verify the update links to the part request
        from the_flip.apps.parts.models import PartRequestUpdate

        update = PartRequestUpdate.objects.get(pk=result.record_id)
        self.assertEqual(update.part_request, part_request)
