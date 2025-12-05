"""Tests for Discord message parsing."""

from django.core.cache import cache
from django.test import TestCase

from the_flip.apps.core.test_utils import (
    create_machine,
    create_machine_model,
    create_part_request,
    create_part_request_update,
    create_problem_report,
    create_staff_user,
)
from the_flip.apps.discord.parsers import RecordType, parse_message
from the_flip.apps.discord.parsers.references import parse_url
from the_flip.apps.discord.parsers.types import ReferenceType


class MessageParserTests(TestCase):
    """Tests for Discord message parsing."""

    def setUp(self):
        # Clear the machine cache to avoid stale data between tests
        cache.delete("machines_for_matching")

        model = create_machine_model(name="Godzilla (Premium)")
        self.machine = create_machine(model=model)
        self.staff_user = create_staff_user()

    def test_parse_explicit_pr_reference(self):
        """Parses explicit PR #123 reference."""
        report = create_problem_report(machine=self.machine)
        content = f"Fixed the issue on PR #{report.pk}"

        result = parse_message(content)

        self.assertEqual(result.record_type, RecordType.LOG_ENTRY)
        self.assertEqual(result.problem_report, report)
        self.assertEqual(result.machine, self.machine)

    def test_parse_url_to_problem_report(self):
        """Parses URL to problem report."""
        report = create_problem_report(machine=self.machine)
        content = f"Working on https://theflip.app/problem-reports/{report.pk}/"

        result = parse_message(content)

        self.assertEqual(result.record_type, RecordType.LOG_ENTRY)
        self.assertEqual(result.problem_report, report)

    def test_parse_machine_name_exact(self):
        """Finds machine by exact name."""
        content = "Fixed the flipper on Godzilla (Premium)"

        result = parse_message(content)

        self.assertEqual(result.machine, self.machine)

    def test_parse_machine_name_prefix(self):
        """Finds machine by prefix (Godzilla matches Godzilla (Premium))."""
        content = "Fixed the flipper on Godzilla"

        result = parse_message(content)

        self.assertEqual(result.machine, self.machine)

    def test_parse_problem_keywords(self):
        """Recognizes problem keywords and creates problem report action."""
        content = "Godzilla ball is stuck again"

        result = parse_message(content)

        self.assertEqual(result.record_type, RecordType.PROBLEM_REPORT)
        self.assertEqual(result.machine, self.machine)

    def test_parse_work_keywords(self):
        """Recognizes work keywords and creates log entry action."""
        content = "Fixed the flipper on Godzilla"

        result = parse_message(content)

        self.assertEqual(result.record_type, RecordType.LOG_ENTRY)
        self.assertEqual(result.machine, self.machine)

    def test_parse_parts_keywords(self):
        """Recognizes parts keywords and creates part request action."""
        content = "Need to order new flipper coil for Godzilla"

        result = parse_message(content)

        self.assertEqual(result.record_type, RecordType.PART_REQUEST)
        self.assertEqual(result.machine, self.machine)

    def test_parse_no_machine_ignores(self):
        """Ignores messages with no machine reference."""
        content = "Hey everyone, meeting at 3pm"

        result = parse_message(content)

        self.assertIsNone(result.record_type)

    def test_parse_reply_to_problem_report_url(self):
        """Reply to webhook post creates log entry linked to PR."""
        report = create_problem_report(machine=self.machine)
        reply_url = f"https://theflip.app/problem-reports/{report.pk}/"

        result = parse_message(
            content="Checked this out, needs new flipper",
            reply_to_embed_url=reply_url,
        )

        self.assertEqual(result.record_type, RecordType.LOG_ENTRY)
        self.assertEqual(result.problem_report, report)
        self.assertEqual(result.machine, self.machine)

    def test_parse_ambiguous_machine_ignores(self):
        """Ignores when multiple machines match."""
        # Create another machine that also matches "Godzilla"
        model2 = create_machine_model(name="Godzilla (LE)")
        create_machine(model=model2)

        content = "Fixed Godzilla"

        result = parse_message(content)

        # Should ignore because "Godzilla" matches both
        self.assertIsNone(result.record_type)

    def test_parse_url_to_part_request_update(self):
        """Parses URL to part request update."""
        part_request = create_part_request(machine=self.machine)
        update = create_part_request_update(part_request=part_request)
        content = f"See https://theflip.app/parts/updates/{update.pk}/"

        result = parse_message(content)

        self.assertEqual(result.record_type, RecordType.PART_REQUEST_UPDATE)
        self.assertEqual(result.part_request, part_request)
        self.assertEqual(result.machine, self.machine)

    def test_parse_reply_to_part_request_update_url(self):
        """Reply to part request update webhook creates another update."""
        part_request = create_part_request(machine=self.machine)
        update = create_part_request_update(part_request=part_request)
        reply_url = f"https://theflip.app/parts/updates/{update.pk}/"

        result = parse_message(
            content="Parts arrived today!",
            reply_to_embed_url=reply_url,
        )

        self.assertEqual(result.record_type, RecordType.PART_REQUEST_UPDATE)
        self.assertEqual(result.part_request, part_request)
        self.assertEqual(result.machine, self.machine)


class ParseUrlTests(TestCase):
    """Unit tests for parse_url function."""

    def test_parse_part_request_update_url(self):
        """Parses /parts/updates/123/ URL pattern."""
        ref = parse_url("https://theflip.app/parts/updates/42/")

        self.assertIsNotNone(ref)
        self.assertEqual(ref.ref_type, ReferenceType.PART_REQUEST_UPDATE)
        self.assertEqual(ref.object_id, 42)

    def test_parse_part_request_url(self):
        """Parses /parts/123/ URL pattern (not confused with updates)."""
        ref = parse_url("https://theflip.app/parts/99/")

        self.assertIsNotNone(ref)
        self.assertEqual(ref.ref_type, ReferenceType.PART_REQUEST)
        self.assertEqual(ref.object_id, 99)

    def test_parse_log_entry_url(self):
        """Parses /logs/123/ URL pattern."""
        ref = parse_url("https://theflip.app/logs/77/")

        self.assertIsNotNone(ref)
        self.assertEqual(ref.ref_type, ReferenceType.LOG_ENTRY)
        self.assertEqual(ref.object_id, 77)

    def test_parse_problem_report_url(self):
        """Parses /problem-reports/123/ URL pattern."""
        ref = parse_url("https://theflip.app/problem-reports/55/")

        self.assertIsNotNone(ref)
        self.assertEqual(ref.ref_type, ReferenceType.PROBLEM_REPORT)
        self.assertEqual(ref.object_id, 55)

    def test_parse_machine_url(self):
        """Parses /machines/slug/ URL pattern."""
        ref = parse_url("https://theflip.app/machines/medieval-madness/")

        self.assertIsNotNone(ref)
        self.assertEqual(ref.ref_type, ReferenceType.MACHINE)
        self.assertEqual(ref.machine_slug, "medieval-madness")

    def test_ignores_invalid_domain(self):
        """Ignores URLs from non-theflip.app domains."""
        ref = parse_url("https://example.com/parts/updates/42/")

        self.assertIsNone(ref)
