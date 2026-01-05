"""Tests for Discord record creation."""

from datetime import UTC, datetime

from django.test import TestCase, override_settings, tag
from django.utils import timezone as django_timezone

from the_flip.apps.accounts.models import Maintainer
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
    _resolve_occurred_at,
)
from the_flip.apps.discord.types import DiscordUserInfo
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
            occurred_at=django_timezone.now(),
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
            occurred_at=django_timezone.now(),
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
            occurred_at=django_timezone.now(),
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
            occurred_at=django_timezone.now(),
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
            occurred_at=django_timezone.now(),
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
            occurred_at=django_timezone.now(),
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
            occurred_at=django_timezone.now(),
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
                occurred_at=django_timezone.now(),
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
        author_id = "123456789012345678"  # Discord snowflake format
        source_ids = ["111111111", "222222222", "333333333"]
        suggestion = RecordSuggestion(
            record_type=RecordType.PROBLEM_REPORT,
            description="Flipper broken across multiple messages",
            source_message_ids=source_ids,
            author_id=author_id,
            slug=self.machine.slug,
        )

        discord_user = DiscordUserInfo(
            user_id=author_id,
            username="testuser",
            display_name="Test User",
        )
        author_id_map = {author_id: discord_user}
        # Build timestamp map
        now = django_timezone.now()
        message_timestamp_map = dict.fromkeys(source_ids, now)

        # Call the async function synchronously
        result = async_to_sync(create_record)(
            suggestion, author_id, author_id_map, message_timestamp_map
        )

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

        author_id = "234567890123456789"  # Discord snowflake format
        source_ids = ["999999999"]
        suggestion = RecordSuggestion(
            record_type=RecordType.PROBLEM_REPORT,
            description="Something broken",
            source_message_ids=source_ids,
            author_id=author_id,
            slug=self.machine.slug,
        )

        discord_user = DiscordUserInfo(
            user_id=author_id,
            username="anotheruser",
            display_name="Another User",
        )
        author_id_map = {author_id: discord_user}
        message_timestamp_map = {msg_id: django_timezone.now() for msg_id in source_ids}

        async_to_sync(create_record)(suggestion, author_id, author_id_map, message_timestamp_map)

        self.assertTrue(DiscordMessageMapping.is_processed("999999999"))

    def test_log_entry_with_parent_links_correctly(self):
        """Log entry created via create_record links to parent problem report."""
        from asgiref.sync import async_to_sync

        from the_flip.apps.discord.llm import RecordSuggestion, RecordType
        from the_flip.apps.discord.records import create_record
        from the_flip.apps.discord.types import DiscordUserInfo

        # Create a problem report to link to
        problem_report = create_problem_report(machine=self.machine)

        author_id = "345678901234567890"  # Discord snowflake format
        source_ids = ["444444444"]
        suggestion = RecordSuggestion(
            record_type=RecordType.LOG_ENTRY,
            description="Fixed the issue reported earlier",
            source_message_ids=source_ids,
            author_id=author_id,
            slug=self.machine.slug,
            parent_record_id=problem_report.pk,
        )

        discord_user = DiscordUserInfo(
            user_id=author_id,
            username="fixer",
            display_name="The Fixer",
        )
        author_id_map = {author_id: discord_user}
        message_timestamp_map = {msg_id: django_timezone.now() for msg_id in source_ids}

        result = async_to_sync(create_record)(
            suggestion, author_id, author_id_map, message_timestamp_map
        )

        # Verify the log entry links to the problem report
        log_entry = LogEntry.objects.get(pk=result.record_id)
        self.assertEqual(log_entry.problem_report, problem_report)

    def test_log_entry_inherits_machine_from_parent_problem_report(self):
        """Log entry without slug inherits machine from parent problem report."""
        from asgiref.sync import async_to_sync

        from the_flip.apps.discord.llm import RecordSuggestion, RecordType
        from the_flip.apps.discord.records import create_record
        from the_flip.apps.discord.types import DiscordUserInfo

        # Create a problem report on a specific machine
        problem_report = create_problem_report(machine=self.machine)

        author_id = "345678901234567890"
        source_ids = ["555555555"]
        suggestion = RecordSuggestion(
            record_type=RecordType.LOG_ENTRY,
            description="Fixed the issue",
            source_message_ids=source_ids,
            author_id=author_id,
            slug=None,  # No machine specified - should inherit from parent
            parent_record_id=problem_report.pk,
        )

        discord_user = DiscordUserInfo(
            user_id=author_id,
            username="fixer",
            display_name="The Fixer",
        )
        author_id_map = {author_id: discord_user}
        message_timestamp_map = {msg_id: django_timezone.now() for msg_id in source_ids}

        result = async_to_sync(create_record)(
            suggestion, author_id, author_id_map, message_timestamp_map
        )

        # Verify the log entry is on the same machine as the problem report
        log_entry = LogEntry.objects.get(pk=result.record_id)
        self.assertEqual(log_entry.machine, self.machine)
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

        author_id = "456789012345678901"  # Discord snowflake format
        source_ids = ["555555555"]
        suggestion = RecordSuggestion(
            record_type=RecordType.PART_REQUEST_UPDATE,
            description="Parts arrived today!",
            source_message_ids=source_ids,
            author_id=author_id,
            slug=None,  # Optional for updates
            parent_record_id=part_request.pk,
        )

        # Use matching username so maintainer gets linked
        discord_user = DiscordUserInfo(
            user_id=author_id,
            username="partsuser",
            display_name="Parts User",
        )
        author_id_map = {author_id: discord_user}
        message_timestamp_map = {msg_id: django_timezone.now() for msg_id in source_ids}

        result = async_to_sync(create_record)(
            suggestion, author_id, author_id_map, message_timestamp_map
        )

        # Verify the update links to the part request
        from the_flip.apps.parts.models import PartRequestUpdate

        update = PartRequestUpdate.objects.get(pk=result.record_id)
        self.assertEqual(update.part_request, part_request)


@tag("discord")
class ResolveAuthorTests(TestCase):
    """Tests for _resolve_author() function."""

    def test_discord_snowflake_resolves_to_discord_user(self):
        """Discord snowflake ID resolves via author_id_map."""
        from the_flip.apps.discord.records import _resolve_author
        from the_flip.apps.discord.types import DiscordUserInfo

        author_id = "123456789012345678"
        discord_user = DiscordUserInfo(
            user_id=author_id,
            username="testuser",
            display_name="Test User",
        )
        author_id_map = {author_id: discord_user}

        maintainer, display_name = _resolve_author(author_id, author_id_map)

        # No maintainer linked yet, but display_name comes from Discord
        self.assertIsNone(maintainer)
        self.assertEqual(display_name, "Test User")

    def test_flipfix_prefix_resolves_by_name(self) -> None:
        """flipfix/ prefixed author_id resolves via Maintainer.match_by_name."""
        from the_flip.apps.discord.records import _resolve_author

        # Create a maintainer with known name
        user = create_maintainer_user(username="sarahchen", first_name="Sarah", last_name="Chen")
        expected_maintainer = Maintainer.objects.get(user=user)

        author_id = "flipfix/Sarah Chen"
        author_id_map: dict[str, DiscordUserInfo] = {}

        maintainer, display_name = _resolve_author(author_id, author_id_map)

        self.assertEqual(maintainer, expected_maintainer)
        self.assertEqual(display_name, "Sarah Chen")

    def test_flipfix_prefix_returns_name_when_no_match(self) -> None:
        """flipfix/ prefix returns the name even when no maintainer matches."""
        from the_flip.apps.discord.records import _resolve_author

        author_id = "flipfix/Unknown Person"
        author_id_map: dict[str, DiscordUserInfo] = {}

        maintainer, display_name = _resolve_author(author_id, author_id_map)

        self.assertIsNone(maintainer)
        self.assertEqual(display_name, "Unknown Person")

    def test_unknown_author_id_returns_fallback(self) -> None:
        """Unknown author_id not in map returns fallback."""
        from the_flip.apps.discord.records import _resolve_author

        author_id = "999999999999999999"
        author_id_map: dict[str, DiscordUserInfo] = {}

        maintainer, display_name = _resolve_author(author_id, author_id_map)

        self.assertIsNone(maintainer)
        self.assertEqual(display_name, "Discord")


@tag("discord")
class ResolveOccurredAtTests(TestCase):
    """Tests for _resolve_occurred_at() function."""

    def test_returns_latest_timestamp_from_multiple_messages(self):
        """Given multiple timestamps, returns the latest (most recent) one."""
        earliest = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        middle = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        latest = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)

        message_timestamp_map = {
            "111": earliest,
            "222": middle,
            "333": latest,
        }

        result = _resolve_occurred_at(["111", "222", "333"], message_timestamp_map)

        self.assertEqual(result, latest)

    def test_returns_single_timestamp_when_one_message(self):
        """Single source message returns its timestamp."""
        timestamp = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        message_timestamp_map = {"123": timestamp}

        result = _resolve_occurred_at(["123"], message_timestamp_map)

        self.assertEqual(result, timestamp)

    def test_falls_back_to_now_when_no_timestamps_found(self) -> None:
        """Falls back to current time if no source messages in map."""
        message_timestamp_map: dict[str, datetime] = {}

        before = django_timezone.now()
        result = _resolve_occurred_at(["missing_id"], message_timestamp_map)
        after = django_timezone.now()

        # Result should be between before and after
        self.assertGreaterEqual(result, before)
        self.assertLessEqual(result, after)

    def test_ignores_missing_message_ids(self):
        """Only considers timestamps for message IDs that exist in the map."""
        early = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        late = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)

        message_timestamp_map = {
            "111": early,
            "333": late,
            # "222" is missing
        }

        # source_message_ids includes a missing ID
        result = _resolve_occurred_at(["111", "222", "333"], message_timestamp_map)

        # Should still return latest from available timestamps
        self.assertEqual(result, late)


@tag("discord")
@override_settings(SITE_URL="https://flipfix.example.com")
class TimestampPreservationTests(TestCase):
    """Tests for timestamp preservation in record creation."""

    def setUp(self):
        self.machine = create_machine()
        self.user = create_maintainer_user()
        self.maintainer = self.user.maintainer

    def test_log_entry_uses_timestamp_from_source_message(self):
        """Log entry created from Discord uses source message timestamp."""
        # Discord message posted at 2pm
        discord_timestamp = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)

        log_entry = _create_log_entry(
            machine=self.machine,
            description="Fixed the flipper",
            maintainer=self.maintainer,
            discord_display_name=None,
            parent_record_id=None,
            occurred_at=discord_timestamp,
        )

        self.assertEqual(log_entry.occurred_at, discord_timestamp)

    def test_record_uses_latest_timestamp_from_multiple_sources(self):
        """Record created from multiple messages uses latest timestamp."""
        from asgiref.sync import async_to_sync

        from the_flip.apps.discord.llm import RecordSuggestion, RecordType
        from the_flip.apps.discord.records import create_record
        from the_flip.apps.discord.types import DiscordUserInfo

        # Three messages at different times
        early = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        middle = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        late = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)

        author_id = "123456789012345678"
        source_ids = ["msg1", "msg2", "msg3"]
        suggestion = RecordSuggestion(
            record_type=RecordType.PROBLEM_REPORT,
            description="Flipper problem discussed over time",
            source_message_ids=source_ids,
            author_id=author_id,
            slug=self.machine.slug,
        )

        discord_user = DiscordUserInfo(
            user_id=author_id,
            username="testuser",
            display_name="Test User",
        )
        author_id_map = {author_id: discord_user}
        message_timestamp_map = {
            "msg1": early,
            "msg2": middle,
            "msg3": late,
        }

        result = async_to_sync(create_record)(
            suggestion, author_id, author_id_map, message_timestamp_map
        )

        # Verify record uses the latest timestamp
        from the_flip.apps.maintenance.models import ProblemReport

        problem_report = ProblemReport.objects.get(pk=result.record_id)
        self.assertEqual(problem_report.occurred_at, late)
