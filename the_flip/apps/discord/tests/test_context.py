"""Tests for Discord context gathering and YAML prompt building."""

from django.test import TestCase, tag

from the_flip.apps.discord.context import (
    ContextMessage,
    FlipfixRecord,
    GatheredContext,
    _is_flipfix_url,
    _parse_flipfix_url,
    _parse_webhook_embed,
)
from the_flip.apps.discord.llm import RecordType, _escape_yaml_string, build_yaml_prompt


class MockEmbed:
    """Mock Discord embed for testing."""

    def __init__(self, url: str | None = None, description: str | None = None):
        self.url = url
        self.description = description


@tag("tasks")
class ParseFlipfixUrlTests(TestCase):
    """Tests for _parse_flipfix_url()."""

    def test_parses_log_entry_url(self):
        """Parses /log/123/ pattern."""
        result = _parse_flipfix_url("https://flipfix.example.com/log/123/")
        self.assertEqual(result, (RecordType.LOG_ENTRY, 123, None))

    def test_parses_problem_report_url(self):
        """Parses /problem/456/ pattern."""
        result = _parse_flipfix_url("https://flipfix.example.com/problem/456/")
        self.assertEqual(result, (RecordType.PROBLEM_REPORT, 456, None))

    def test_parses_part_request_url(self):
        """Parses /parts/request/789/ pattern."""
        result = _parse_flipfix_url("https://flipfix.example.com/parts/request/789/")
        self.assertEqual(result, (RecordType.PART_REQUEST, 789, None))

    def test_parses_machine_log_url(self):
        """Parses /machines/<slug>/log/<id> pattern."""
        result = _parse_flipfix_url("https://flipfix.example.com/machines/godzilla/log/42/")
        self.assertEqual(result, (RecordType.LOG_ENTRY, 42, "godzilla"))

    def test_parses_machine_problem_url(self):
        """Parses /machines/<slug>/problem/<id> pattern."""
        result = _parse_flipfix_url("https://flipfix.example.com/machines/metallica/problem/99/")
        self.assertEqual(result, (RecordType.PROBLEM_REPORT, 99, "metallica"))

    def test_returns_none_for_unknown_pattern(self):
        """Returns None for unrecognized URL patterns."""
        result = _parse_flipfix_url("https://flipfix.example.com/unknown/path/")
        self.assertIsNone(result)

    def test_handles_url_without_trailing_slash(self):
        """Handles URLs without trailing slashes."""
        result = _parse_flipfix_url("https://flipfix.example.com/log/123")
        self.assertEqual(result, (RecordType.LOG_ENTRY, 123, None))


@tag("tasks")
class ParseWebhookEmbedTests(TestCase):
    """Tests for _parse_webhook_embed()."""

    def test_parses_embed_with_author_suffix(self):
        """Parses author from description's — suffix."""
        with self.settings(DISCORD_VALID_DOMAINS=["flipfix.example.com"]):
            embed = MockEmbed(
                url="https://flipfix.example.com/log/123/",
                description="Fixed the flipper coil.\n\n— Bob",
            )
            result = _parse_webhook_embed(embed)

            self.assertIsNotNone(result)
            flipfix_record, author, content = result
            self.assertEqual(flipfix_record.record_type, RecordType.LOG_ENTRY)
            self.assertEqual(flipfix_record.record_id, 123)
            self.assertEqual(author, "Bob")
            self.assertEqual(content, "Fixed the flipper coil.")

    def test_parses_embed_without_author_suffix(self):
        """Handles embeds without — author suffix."""
        with self.settings(DISCORD_VALID_DOMAINS=["flipfix.example.com"]):
            embed = MockEmbed(
                url="https://flipfix.example.com/problem/456/",
                description="Machine is broken",
            )
            result = _parse_webhook_embed(embed)

            self.assertIsNotNone(result)
            flipfix_record, author, content = result
            self.assertEqual(flipfix_record.record_type, RecordType.PROBLEM_REPORT)
            self.assertEqual(author, "")
            self.assertEqual(content, "Machine is broken")

    def test_returns_none_for_non_flipfix_url(self):
        """Returns None for non-Flipfix URLs."""
        with self.settings(DISCORD_VALID_DOMAINS=["flipfix.example.com"]):
            embed = MockEmbed(
                url="https://other-site.com/page/",
                description="Some content",
            )
            result = _parse_webhook_embed(embed)
            self.assertIsNone(result)

    def test_returns_none_for_missing_url(self):
        """Returns None when embed has no URL."""
        embed = MockEmbed(url=None, description="Some content")
        result = _parse_webhook_embed(embed)
        self.assertIsNone(result)


@tag("tasks")
class IsFlipfixUrlTests(TestCase):
    """Tests for _is_flipfix_url()."""

    def test_recognizes_valid_domain(self):
        """Returns True for configured domain."""
        with self.settings(DISCORD_VALID_DOMAINS=["flipfix.example.com"]):
            result = _is_flipfix_url("https://flipfix.example.com/log/123/")
            self.assertTrue(result)

    def test_recognizes_subdomain(self):
        """Returns True for subdomains of configured domain."""
        with self.settings(DISCORD_VALID_DOMAINS=["example.com"]):
            result = _is_flipfix_url("https://flipfix.example.com/log/123/")
            self.assertTrue(result)

    def test_rejects_unrecognized_domain(self):
        """Returns False for unconfigured domain."""
        with self.settings(DISCORD_VALID_DOMAINS=["flipfix.example.com"]):
            result = _is_flipfix_url("https://other-site.com/log/123/")
            self.assertFalse(result)

    def test_handles_empty_domains_list(self):
        """Returns False when no domains configured."""
        with self.settings(DISCORD_VALID_DOMAINS=[]):
            result = _is_flipfix_url("https://any-site.com/")
            self.assertFalse(result)


@tag("tasks")
class EscapeYamlStringTests(TestCase):
    """Tests for _escape_yaml_string()."""

    def test_escapes_quotes(self):
        """Escapes double quotes."""
        result = _escape_yaml_string('He said "hello"')
        self.assertEqual(result, 'He said \\"hello\\"')

    def test_escapes_newlines(self):
        """Converts newlines to \\n."""
        result = _escape_yaml_string("Line 1\nLine 2")
        self.assertEqual(result, "Line 1\\nLine 2")

    def test_escapes_backslashes(self):
        """Escapes backslashes."""
        result = _escape_yaml_string("path\\to\\file")
        self.assertEqual(result, "path\\\\to\\\\file")

    def test_handles_combined_escapes(self):
        """Correctly orders escaping for combined special chars."""
        result = _escape_yaml_string('Quote: "test"\nBackslash: \\')
        self.assertEqual(result, 'Quote: \\"test\\"\\nBackslash: \\\\')


@tag("tasks")
class BuildYamlPromptTests(TestCase):
    """Tests for build_yaml_prompt()."""

    def test_includes_machines_section(self):
        """Outputs machines section with id and name."""
        machines = [
            {"slug": "godzilla", "name": "Godzilla (Premium)"},
            {"slug": "metallica", "name": "Metallica"},
        ]
        context = GatheredContext(
            messages=[
                ContextMessage(
                    id="123",
                    author="alice",
                    content="test",
                    timestamp="2025-01-15T14:00:00Z",
                    is_target=True,
                )
            ],
            target_message_id="123",
        )

        result = build_yaml_prompt(context, machines)

        self.assertIn("machines:", result)
        self.assertIn("- id: godzilla", result)
        self.assertIn('name: "Godzilla (Premium)"', result)
        self.assertIn("- id: metallica", result)

    def test_includes_message_fields(self):
        """Outputs message with all fields."""
        context = GatheredContext(
            messages=[
                ContextMessage(
                    id="456",
                    author="bob",
                    content="Fixed the flipper",
                    timestamp="2025-01-15T14:30:00Z",
                    is_target=True,
                    reply_to_id="123",
                )
            ],
            target_message_id="456",
        )

        result = build_yaml_prompt(context, [])

        self.assertIn('id: "456"', result)
        self.assertIn('author: "bob"', result)
        self.assertIn('content: "Fixed the flipper"', result)
        self.assertIn('timestamp: "2025-01-15T14:30:00Z"', result)
        self.assertIn('reply_to_id: "123"', result)
        self.assertIn("is_target: true", result)

    def test_omits_optional_fields_when_absent(self):
        """Doesn't include reply_to_id or is_target when not set."""
        context = GatheredContext(
            messages=[
                ContextMessage(
                    id="789",
                    author="charlie",
                    content="Context message",
                    timestamp="2025-01-15T13:00:00Z",
                    is_target=False,
                )
            ],
            target_message_id="456",
        )

        result = build_yaml_prompt(context, [])

        self.assertNotIn("reply_to_id:", result)
        self.assertNotIn("is_target:", result)

    def test_includes_flipfix_record(self):
        """Outputs flipfix_record when present."""
        context = GatheredContext(
            messages=[
                ContextMessage(
                    id="100",
                    author="Flipfix",
                    content="Work was logged",
                    timestamp="2025-01-15T15:00:00Z",
                    flipfix_record=FlipfixRecord(
                        record_type=RecordType.LOG_ENTRY,
                        record_id=42,
                        machine_id="godzilla",
                    ),
                )
            ],
            target_message_id="100",
        )

        result = build_yaml_prompt(context, [])

        self.assertIn("flipfix_record:", result)
        self.assertIn("type: log_entry", result)
        self.assertIn("id: 42", result)
        self.assertIn("machine_id: godzilla", result)

    def test_nests_thread_messages(self):
        """Thread messages are nested under parent."""
        context = GatheredContext(
            messages=[
                ContextMessage(
                    id="200",
                    author="alice",
                    content="Thread starter",
                    timestamp="2025-01-15T14:00:00Z",
                    thread=[
                        ContextMessage(
                            id="201",
                            author="bob",
                            content="Thread reply 1",
                            timestamp="2025-01-15T14:05:00Z",
                        ),
                        ContextMessage(
                            id="202",
                            author="charlie",
                            content="Thread reply 2",
                            timestamp="2025-01-15T14:10:00Z",
                            is_target=True,
                        ),
                    ],
                )
            ],
            target_message_id="202",
        )

        result = build_yaml_prompt(context, [])

        # Thread messages should be indented under parent
        self.assertIn("thread:", result)
        self.assertIn('id: "201"', result)
        self.assertIn('id: "202"', result)
        self.assertIn('author: "bob"', result)
        self.assertIn('author: "charlie"', result)

    def test_escapes_special_characters_in_content(self):
        """Properly escapes quotes and newlines in content."""
        context = GatheredContext(
            messages=[
                ContextMessage(
                    id="300",
                    author="dave",
                    content='Said "hello"\nOn two lines',
                    timestamp="2025-01-15T16:00:00Z",
                )
            ],
            target_message_id="300",
        )

        result = build_yaml_prompt(context, [])

        self.assertIn('\\"hello\\"', result)
        self.assertIn("\\n", result)
