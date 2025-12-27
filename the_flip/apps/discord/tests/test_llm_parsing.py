"""Tests for LLM integration parsing and message building."""

from unittest.mock import MagicMock

from django.test import TestCase, tag

from the_flip.apps.discord.llm import (
    MessageContext,
    RecordSuggestion,
    _build_user_message,
    _parse_tool_response,
)


@tag("tasks")
class BuildUserMessageTests(TestCase):
    """Tests for _build_user_message()."""

    def test_includes_all_machines(self):
        """User message includes all machines from the list."""
        machines = [
            {"slug": "godzilla", "name": "Godzilla"},
            {"slug": "metallica", "name": "Metallica"},
        ]
        context = MessageContext(
            messages=[
                {"author": "user", "content": "test", "timestamp": "12:00", "is_target": True}
            ],
            target_message_id=123,
            flipfix_urls=[],
        )

        result = _build_user_message(context, machines)

        self.assertIn("Godzilla (slug: godzilla)", result)
        self.assertIn("Metallica (slug: metallica)", result)

    def test_marks_target_message_with_asterisks(self):
        """Target message is marked with ** markers."""
        machines = [{"slug": "test", "name": "Test"}]
        context = MessageContext(
            messages=[
                {
                    "author": "alice",
                    "content": "context msg",
                    "timestamp": "11:00",
                    "is_target": False,
                },
                {"author": "bob", "content": "target msg", "timestamp": "12:00", "is_target": True},
            ],
            target_message_id=123,
            flipfix_urls=[],
        )

        result = _build_user_message(context, machines)

        # Target message should be wrapped in **
        self.assertIn("**[12:00] bob: target msg**", result)
        # Context message should NOT be wrapped
        self.assertIn("[11:00] alice: context msg", result)
        self.assertNotIn("**[11:00]", result)

    def test_includes_flipfix_urls_when_present(self):
        """Flipfix URLs section appears when URLs are provided."""
        machines = [{"slug": "test", "name": "Test"}]
        context = MessageContext(
            messages=[
                {"author": "user", "content": "test", "timestamp": "12:00", "is_target": True}
            ],
            target_message_id=123,
            flipfix_urls=[
                "https://flipfix.example.com/log/123/",
                "https://flipfix.example.com/problem/456/",
            ],
        )

        result = _build_user_message(context, machines)

        self.assertIn("## Related Flipfix Records", result)
        self.assertIn("https://flipfix.example.com/log/123/", result)
        self.assertIn("https://flipfix.example.com/problem/456/", result)

    def test_omits_flipfix_section_when_no_urls(self):
        """Flipfix URLs section is omitted when no URLs are provided."""
        machines = [{"slug": "test", "name": "Test"}]
        context = MessageContext(
            messages=[
                {"author": "user", "content": "test", "timestamp": "12:00", "is_target": True}
            ],
            target_message_id=123,
            flipfix_urls=[],
        )

        result = _build_user_message(context, machines)

        self.assertNotIn("## Related Flipfix Records", result)

    def test_formats_messages_chronologically(self):
        """Messages appear in the order provided (should be chronological)."""
        machines = [{"slug": "test", "name": "Test"}]
        context = MessageContext(
            messages=[
                {"author": "alice", "content": "first", "timestamp": "10:00", "is_target": False},
                {"author": "bob", "content": "second", "timestamp": "11:00", "is_target": False},
                {"author": "charlie", "content": "third", "timestamp": "12:00", "is_target": True},
            ],
            target_message_id=123,
            flipfix_urls=[],
        )

        result = _build_user_message(context, machines)

        # Check order by finding positions
        pos_first = result.find("first")
        pos_second = result.find("second")
        pos_third = result.find("third")

        self.assertLess(pos_first, pos_second)
        self.assertLess(pos_second, pos_third)


@tag("tasks")
class ParseToolResponseTests(TestCase):
    """Tests for _parse_tool_response()."""

    def _make_mock_response(self, suggestions: list[dict]) -> MagicMock:
        """Create a mock Anthropic response with tool_use content."""
        tool_use = MagicMock()
        tool_use.type = "tool_use"
        tool_use.name = "record_suggestions"
        tool_use.input = {"suggestions": suggestions}

        response = MagicMock()
        response.content = [tool_use]
        return response

    def test_parses_valid_suggestions(self):
        """Parses valid suggestion data into RecordSuggestion objects."""
        response = self._make_mock_response(
            [
                {
                    "record_type": "log_entry",
                    "machine_slug": "godzilla",
                    "machine_name": "Godzilla",
                    "description": "Fixed the flipper",
                },
                {
                    "record_type": "problem_report",
                    "machine_slug": "metallica",
                    "machine_name": "Metallica",
                    "description": "Left flipper weak",
                },
            ]
        )

        result = _parse_tool_response(response)

        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], RecordSuggestion)
        self.assertEqual(result[0].record_type, "log_entry")
        self.assertEqual(result[0].machine_slug, "godzilla")
        self.assertEqual(result[1].record_type, "problem_report")
        self.assertEqual(result[1].machine_slug, "metallica")

    def test_returns_empty_list_for_empty_suggestions(self):
        """Returns empty list when suggestions array is empty."""
        response = self._make_mock_response([])

        result = _parse_tool_response(response)

        self.assertEqual(result, [])

    def test_filters_out_invalid_record_types(self):
        """Suggestions with invalid record_type are filtered out."""
        response = self._make_mock_response(
            [
                {
                    "record_type": "invalid_type",
                    "machine_slug": "godzilla",
                    "machine_name": "Godzilla",
                    "description": "This should be filtered",
                },
                {
                    "record_type": "log_entry",
                    "machine_slug": "metallica",
                    "machine_name": "Metallica",
                    "description": "This is valid",
                },
            ]
        )

        result = _parse_tool_response(response)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].record_type, "log_entry")

    def test_filters_out_suggestions_missing_required_fields(self):
        """Suggestions missing required fields are filtered out."""
        response = self._make_mock_response(
            [
                {
                    "record_type": "log_entry",
                    # missing machine_slug, machine_name, description
                },
                {
                    "record_type": "problem_report",
                    "machine_slug": "godzilla",
                    # missing machine_name, description
                },
                {
                    "record_type": "part_request",
                    "machine_slug": "metallica",
                    "machine_name": "Metallica",
                    "description": "Need new flipper",
                },
            ]
        )

        result = _parse_tool_response(response)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].record_type, "part_request")

    def test_returns_empty_list_when_no_tool_use_block(self):
        """Returns empty list when response has no tool_use content."""
        text_content = MagicMock()
        text_content.type = "text"
        text_content.text = "Some text response"

        response = MagicMock()
        response.content = [text_content]

        result = _parse_tool_response(response)

        self.assertEqual(result, [])

    def test_returns_empty_list_when_tool_input_not_dict(self):
        """Returns empty list when tool input is not a dict."""
        tool_use = MagicMock()
        tool_use.type = "tool_use"
        tool_use.name = "record_suggestions"
        tool_use.input = "not a dict"

        response = MagicMock()
        response.content = [tool_use]

        result = _parse_tool_response(response)

        self.assertEqual(result, [])

    def test_returns_empty_list_when_suggestions_not_list(self):
        """Returns empty list when suggestions is not a list."""
        tool_use = MagicMock()
        tool_use.type = "tool_use"
        tool_use.name = "record_suggestions"
        tool_use.input = {"suggestions": "not a list"}

        response = MagicMock()
        response.content = [tool_use]

        result = _parse_tool_response(response)

        self.assertEqual(result, [])

    def test_skips_non_dict_items_in_suggestions(self):
        """Non-dict items in suggestions array are skipped."""
        response = self._make_mock_response(
            [
                "not a dict",
                123,
                {
                    "record_type": "log_entry",
                    "machine_slug": "godzilla",
                    "machine_name": "Godzilla",
                    "description": "Valid suggestion",
                },
            ]
        )

        result = _parse_tool_response(response)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].machine_slug, "godzilla")

    def test_all_valid_record_types_accepted(self):
        """All three valid record types are accepted."""
        response = self._make_mock_response(
            [
                {
                    "record_type": "log_entry",
                    "machine_slug": "m1",
                    "machine_name": "Machine 1",
                    "description": "Log entry",
                },
                {
                    "record_type": "problem_report",
                    "machine_slug": "m2",
                    "machine_name": "Machine 2",
                    "description": "Problem report",
                },
                {
                    "record_type": "part_request",
                    "machine_slug": "m3",
                    "machine_name": "Machine 3",
                    "description": "Part request",
                },
            ]
        )

        result = _parse_tool_response(response)

        self.assertEqual(len(result), 3)
        record_types = {r.record_type for r in result}
        self.assertEqual(record_types, {"log_entry", "problem_report", "part_request"})
