"""Tests for LLM integration parsing."""

from unittest.mock import MagicMock

from django.test import TestCase, tag

from the_flip.apps.discord.llm import (
    ChildSuggestion,
    RecordSuggestion,
    RecordType,
    _parse_tool_response,
    flatten_suggestions,
)


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
                    "machine_id": "godzilla",
                    "description": "Fixed the flipper",
                    "source_message_ids": ["123456789"],
                    "author_id": "111222333",
                },
                {
                    "record_type": "problem_report",
                    "machine_id": "metallica",
                    "description": "Left flipper weak",
                    "source_message_ids": ["987654321"],
                    "author_id": "444555666",
                },
            ]
        )

        result = _parse_tool_response(response)

        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], RecordSuggestion)
        self.assertEqual(result[0].record_type, RecordType.LOG_ENTRY)
        self.assertEqual(result[0].slug, "godzilla")
        self.assertEqual(result[0].source_message_ids, ["123456789"])
        self.assertEqual(result[0].author_id, "111222333")
        self.assertEqual(result[1].record_type, RecordType.PROBLEM_REPORT)
        self.assertEqual(result[1].slug, "metallica")
        self.assertEqual(result[1].author_id, "444555666")

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
                    "machine_id": "godzilla",
                    "description": "This should be filtered",
                    "source_message_ids": ["123"],
                    "author_id": "111222333",
                },
                {
                    "record_type": "log_entry",
                    "machine_id": "metallica",
                    "description": "This is valid",
                    "source_message_ids": ["456"],
                    "author_id": "444555666",
                },
            ]
        )

        result = _parse_tool_response(response)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].record_type, RecordType.LOG_ENTRY)

    def test_filters_out_suggestions_missing_required_fields(self):
        """Suggestions missing required fields are filtered out."""
        response = self._make_mock_response(
            [
                {
                    "record_type": "log_entry",
                    # missing machine_id (required for log_entry), description, source_message_ids, author_id
                },
                {
                    "record_type": "problem_report",
                    "machine_id": "godzilla",
                    # missing description, source_message_ids, author_id
                },
                {
                    "record_type": "part_request",
                    # machine_id is optional for part_request
                    "description": "Need new flipper",
                    "source_message_ids": ["789"],
                    "author_id": "111222333",
                },
            ]
        )

        result = _parse_tool_response(response)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].record_type, RecordType.PART_REQUEST)

    def test_filters_out_log_entry_without_machine_id(self):
        """Log entries require machine_id."""
        response = self._make_mock_response(
            [
                {
                    "record_type": "log_entry",
                    # missing machine_id - required for log_entry
                    "description": "Fixed something",
                    "source_message_ids": ["123"],
                    "author_id": "111222333",
                },
            ]
        )

        result = _parse_tool_response(response)

        self.assertEqual(len(result), 0)

    def test_filters_out_problem_report_without_machine_id(self):
        """Problem reports require machine_id."""
        response = self._make_mock_response(
            [
                {
                    "record_type": "problem_report",
                    # missing machine_id - required for problem_report
                    "description": "Something is broken",
                    "source_message_ids": ["123"],
                    "author_id": "111222333",
                },
            ]
        )

        result = _parse_tool_response(response)

        self.assertEqual(len(result), 0)

    def test_part_request_without_machine_id_is_valid(self):
        """Part requests don't require machine_id."""
        response = self._make_mock_response(
            [
                {
                    "record_type": "part_request",
                    # no machine_id - that's OK for part_request
                    "description": "Need new flipper",
                    "source_message_ids": ["123"],
                    "author_id": "111222333",
                },
            ]
        )

        result = _parse_tool_response(response)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].record_type, RecordType.PART_REQUEST)
        self.assertIsNone(result[0].slug)

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
                    "machine_id": "godzilla",
                    "description": "Valid suggestion",
                    "source_message_ids": ["123"],
                    "author_id": "111222333",
                },
            ]
        )

        result = _parse_tool_response(response)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].slug, "godzilla")

    def test_all_valid_record_types_accepted(self):
        """All four valid record types are accepted."""
        response = self._make_mock_response(
            [
                {
                    "record_type": "log_entry",
                    "machine_id": "m1",
                    "description": "Log entry",
                    "source_message_ids": ["1"],
                    "author_id": "111222333",
                },
                {
                    "record_type": "problem_report",
                    "machine_id": "m2",
                    "description": "Problem report",
                    "source_message_ids": ["2"],
                    "author_id": "222333444",
                },
                {
                    "record_type": "part_request",
                    # machine_id optional
                    "description": "Part request",
                    "source_message_ids": ["3"],
                    "author_id": "333444555",
                },
                {
                    "record_type": "part_request_update",
                    # machine_id optional
                    "description": "Part request update",
                    "source_message_ids": ["4"],
                    "parent_record_id": 42,
                    "author_id": "444555666",
                },
            ]
        )

        result = _parse_tool_response(response)

        self.assertEqual(len(result), 4)
        record_types = {r.record_type for r in result}
        self.assertEqual(
            record_types,
            {
                RecordType.LOG_ENTRY,
                RecordType.PROBLEM_REPORT,
                RecordType.PART_REQUEST,
                RecordType.PART_REQUEST_UPDATE,
            },
        )

    def test_parses_parent_record_id(self):
        """Parses optional parent_record_id field."""
        response = self._make_mock_response(
            [
                {
                    "record_type": "log_entry",
                    "machine_id": "godzilla",
                    "description": "Fixed the problem",
                    "source_message_ids": ["123"],
                    "parent_record_id": 42,
                    "author_id": "111222333",
                },
            ]
        )

        result = _parse_tool_response(response)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].parent_record_id, 42)

    def test_source_message_ids_converted_to_strings(self):
        """Source message IDs are converted to strings."""
        response = self._make_mock_response(
            [
                {
                    "record_type": "log_entry",
                    "machine_id": "godzilla",
                    "description": "Fixed something",
                    "source_message_ids": [123456789, 987654321],  # integers
                    "author_id": "111222333",
                },
            ]
        )

        result = _parse_tool_response(response)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].source_message_ids, ["123456789", "987654321"])

    def test_multiple_source_message_ids(self):
        """Multiple source message IDs are parsed correctly."""
        response = self._make_mock_response(
            [
                {
                    "record_type": "log_entry",
                    "machine_id": "godzilla",
                    "description": "Fixed something across multiple messages",
                    "source_message_ids": ["111", "222", "333"],
                    "author_id": "111222333",
                },
            ]
        )

        result = _parse_tool_response(response)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].source_message_ids, ["111", "222", "333"])

    def test_filters_out_empty_source_message_ids(self):
        """Suggestions with empty source_message_ids are filtered out."""
        response = self._make_mock_response(
            [
                {
                    "record_type": "log_entry",
                    "machine_id": "godzilla",
                    "description": "This has empty source_message_ids",
                    "source_message_ids": [],  # Empty - should be filtered
                    "author_id": "111222333",
                },
                {
                    "record_type": "log_entry",
                    "machine_id": "metallica",
                    "description": "This is valid",
                    "source_message_ids": ["123"],
                    "author_id": "444555666",
                },
            ]
        )

        result = _parse_tool_response(response)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].slug, "metallica")

    def test_filters_out_part_request_update_without_parent_record_id(self):
        """Part request updates require parent_record_id."""
        response = self._make_mock_response(
            [
                {
                    "record_type": "part_request_update",
                    "description": "Parts arrived",
                    "source_message_ids": ["123"],
                    "author_id": "111222333",
                    # missing parent_record_id - required for part_request_update
                },
            ]
        )

        result = _parse_tool_response(response)

        self.assertEqual(len(result), 0)

    def test_part_request_update_with_parent_record_id_is_valid(self):
        """Part request updates with parent_record_id are accepted."""
        response = self._make_mock_response(
            [
                {
                    "record_type": "part_request_update",
                    "description": "Parts arrived",
                    "source_message_ids": ["123"],
                    "parent_record_id": 42,
                    "author_id": "111222333",
                },
            ]
        )

        result = _parse_tool_response(response)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].record_type, RecordType.PART_REQUEST_UPDATE)
        self.assertEqual(result[0].parent_record_id, 42)

    def test_filters_out_suggestion_missing_author_id(self):
        """Suggestions missing author_id are filtered out."""
        response = self._make_mock_response(
            [
                {
                    "record_type": "log_entry",
                    "machine_id": "godzilla",
                    "description": "Missing author_id",
                    "source_message_ids": ["123"],
                    # missing author_id - required
                },
                {
                    "record_type": "log_entry",
                    "machine_id": "metallica",
                    "description": "Has author_id",
                    "source_message_ids": ["456"],
                    "author_id": "111222333",
                },
            ]
        )

        result = _parse_tool_response(response)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].slug, "metallica")

    def test_parses_children_on_problem_report(self):
        """Children on problem_report are parsed as log_entry children."""
        response = self._make_mock_response(
            [
                {
                    "record_type": "problem_report",
                    "machine_id": "godzilla",
                    "description": "Left flipper weak",
                    "source_message_ids": ["123"],
                    "author_id": "111222333",
                    "children": [
                        {
                            "description": "Fixed - coil was loose",
                            "source_message_ids": ["456"],
                            "author_id": "444555666",
                        },
                    ],
                },
            ]
        )

        result = _parse_tool_response(response)

        self.assertEqual(len(result), 1)
        self.assertIsNotNone(result[0].children)
        self.assertEqual(len(result[0].children), 1)
        self.assertEqual(result[0].children[0].description, "Fixed - coil was loose")
        self.assertEqual(result[0].children[0].source_message_ids, ["456"])
        self.assertEqual(result[0].children[0].author_id, "444555666")

    def test_parses_children_on_part_request(self):
        """Children on part_request are parsed as part_request_update children."""
        response = self._make_mock_response(
            [
                {
                    "record_type": "part_request",
                    "machine_id": "godzilla",
                    "description": "Need new flipper coil",
                    "source_message_ids": ["123"],
                    "author_id": "111222333",
                    "children": [
                        {
                            "description": "Ordered from Marco",
                            "source_message_ids": ["456"],
                            "author_id": "444555666",
                        },
                        {
                            "description": "Parts arrived",
                            "source_message_ids": ["789"],
                            "author_id": "777888999",
                        },
                    ],
                },
            ]
        )

        result = _parse_tool_response(response)

        self.assertEqual(len(result), 1)
        self.assertIsNotNone(result[0].children)
        self.assertEqual(len(result[0].children), 2)
        self.assertEqual(result[0].children[0].description, "Ordered from Marco")
        self.assertEqual(result[0].children[1].description, "Parts arrived")

    def test_filters_out_invalid_children(self):
        """Invalid children are filtered out, valid ones remain."""
        response = self._make_mock_response(
            [
                {
                    "record_type": "problem_report",
                    "machine_id": "godzilla",
                    "description": "Left flipper weak",
                    "source_message_ids": ["123"],
                    "author_id": "111222333",
                    "children": [
                        {
                            # missing description
                            "source_message_ids": ["456"],
                            "author_id": "444555666",
                        },
                        {
                            "description": "Valid child",
                            "source_message_ids": ["789"],
                            "author_id": "777888999",
                        },
                    ],
                },
            ]
        )

        result = _parse_tool_response(response)

        self.assertEqual(len(result), 1)
        self.assertIsNotNone(result[0].children)
        self.assertEqual(len(result[0].children), 1)
        self.assertEqual(result[0].children[0].description, "Valid child")

    def test_children_without_any_valid_items_is_none(self):
        """When all children are invalid, children is None (same as no children)."""
        response = self._make_mock_response(
            [
                {
                    "record_type": "problem_report",
                    "machine_id": "godzilla",
                    "description": "Left flipper weak",
                    "source_message_ids": ["123"],
                    "author_id": "111222333",
                    "children": [
                        {
                            # missing required fields
                            "description": "Missing author_id",
                        },
                    ],
                },
            ]
        )

        result = _parse_tool_response(response)

        self.assertEqual(len(result), 1)
        # Invalid children are filtered out; if none remain, children is None
        self.assertIsNone(result[0].children)

    def test_no_children_results_in_none(self):
        """When children field is not present, children is None."""
        response = self._make_mock_response(
            [
                {
                    "record_type": "log_entry",
                    "machine_id": "godzilla",
                    "description": "Fixed something",
                    "source_message_ids": ["123"],
                    "author_id": "111222333",
                },
            ]
        )

        result = _parse_tool_response(response)

        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0].children)


@tag("tasks")
class FlattenSuggestionsTests(TestCase):
    """Tests for flatten_suggestions() function."""

    def test_suggestion_without_children_unchanged(self):
        """Suggestions without children remain as single items."""
        suggestions = [
            RecordSuggestion(
                record_type=RecordType.LOG_ENTRY,
                description="Fixed something",
                source_message_ids=["123"],
                author_id="111222333",
                slug="godzilla",
            ),
        ]

        result = flatten_suggestions(suggestions)

        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0].parent_index)
        self.assertEqual(result[0].suggestion.description, "Fixed something")

    def test_problem_report_with_log_entry_child(self):
        """Problem report with children creates parent + log_entry child."""
        suggestions = [
            RecordSuggestion(
                record_type=RecordType.PROBLEM_REPORT,
                description="Flipper broken",
                source_message_ids=["123"],
                author_id="111222333",
                slug="godzilla",
                children=[
                    ChildSuggestion(
                        description="Fixed - coil was loose",
                        source_message_ids=["456"],
                        author_id="444555666",
                    ),
                ],
            ),
        ]

        result = flatten_suggestions(suggestions)

        self.assertEqual(len(result), 2)
        # First is parent (problem report)
        self.assertIsNone(result[0].parent_index)
        self.assertEqual(result[0].suggestion.record_type, RecordType.PROBLEM_REPORT)
        # Second is child (log entry)
        self.assertEqual(result[1].parent_index, 0)
        self.assertEqual(result[1].suggestion.record_type, RecordType.LOG_ENTRY)
        self.assertEqual(result[1].suggestion.description, "Fixed - coil was loose")
        self.assertEqual(result[1].suggestion.author_id, "444555666")
        # Child inherits slug from parent
        self.assertEqual(result[1].suggestion.slug, "godzilla")

    def test_part_request_with_update_children(self):
        """Part request with children creates parent + part_request_update children."""
        suggestions = [
            RecordSuggestion(
                record_type=RecordType.PART_REQUEST,
                description="Need flipper coil",
                source_message_ids=["123"],
                author_id="111222333",
                slug="godzilla",
                children=[
                    ChildSuggestion(
                        description="Ordered from Marco",
                        source_message_ids=["456"],
                        author_id="444555666",
                    ),
                    ChildSuggestion(
                        description="Parts arrived",
                        source_message_ids=["789"],
                        author_id="777888999",
                    ),
                ],
            ),
        ]

        result = flatten_suggestions(suggestions)

        self.assertEqual(len(result), 3)
        # First is parent
        self.assertEqual(result[0].suggestion.record_type, RecordType.PART_REQUEST)
        # Second and third are children
        self.assertEqual(result[1].parent_index, 0)
        self.assertEqual(result[1].suggestion.record_type, RecordType.PART_REQUEST_UPDATE)
        self.assertEqual(result[1].suggestion.description, "Ordered from Marco")
        self.assertEqual(result[2].parent_index, 0)
        self.assertEqual(result[2].suggestion.record_type, RecordType.PART_REQUEST_UPDATE)
        self.assertEqual(result[2].suggestion.description, "Parts arrived")

    def test_multiple_suggestions_mixed(self):
        """Multiple suggestions, some with children, are flattened correctly."""
        suggestions = [
            RecordSuggestion(
                record_type=RecordType.PROBLEM_REPORT,
                description="Problem 1",
                source_message_ids=["100"],
                author_id="111",
                slug="m1",
                children=[
                    ChildSuggestion(
                        description="Fix for problem 1",
                        source_message_ids=["101"],
                        author_id="222",
                    ),
                ],
            ),
            RecordSuggestion(
                record_type=RecordType.LOG_ENTRY,
                description="Standalone log",
                source_message_ids=["200"],
                author_id="333",
                slug="m2",
            ),
        ]

        result = flatten_suggestions(suggestions)

        self.assertEqual(len(result), 3)
        # First: problem report (parent)
        self.assertIsNone(result[0].parent_index)
        self.assertEqual(result[0].suggestion.description, "Problem 1")
        # Second: log entry child of problem report
        self.assertEqual(result[1].parent_index, 0)
        self.assertEqual(result[1].suggestion.description, "Fix for problem 1")
        # Third: standalone log entry (no parent)
        self.assertIsNone(result[2].parent_index)
        self.assertEqual(result[2].suggestion.description, "Standalone log")

    def test_child_parent_record_id_starts_none(self):
        """Child suggestions have parent_record_id=None (set at creation time)."""
        suggestions = [
            RecordSuggestion(
                record_type=RecordType.PROBLEM_REPORT,
                description="Problem",
                source_message_ids=["123"],
                author_id="111",
                slug="godzilla",
                children=[
                    ChildSuggestion(
                        description="Fix",
                        source_message_ids=["456"],
                        author_id="222",
                    ),
                ],
            ),
        ]

        result = flatten_suggestions(suggestions)

        # Child's parent_record_id is None - it will be set when parent is created
        self.assertIsNone(result[1].suggestion.parent_record_id)
