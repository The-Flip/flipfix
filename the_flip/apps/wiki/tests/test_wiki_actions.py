"""Tests for wiki template blocks: parsing, rendering, and pre-fill flow."""

from django.test import TestCase, tag
from django.urls import reverse

from the_flip.apps.core.test_utils import (
    SuppressRequestLogsMixin,
    TestDataMixin,
)
from the_flip.apps.wiki.actions import (
    ActionBlock,
    _validate_markers,
    build_create_url,
    build_template_url,
    extract_template_content,
    inject_buttons,
    prepare_for_rendering,
    validate_template_syntax,
)
from the_flip.apps.wiki.models import WikiPage, WikiPageTag
from the_flip.apps.wiki.views import _resolve_template_tags


def _make_content(name="test"):
    """Create template:start/end content block (structural only, no action attrs)."""
    return (
        f'<!-- template:start name="{name}" -->\n'
        f"## {name.title()} Checklist\n\n"
        f"- [ ] step one\n"
        f"- [ ] step two\n"
        f'<!-- template:end name="{name}" -->\n'
    )


def _make_action_marker(
    name="test",
    action="button",
    record_type="problem",
    machine="blackout",
    label="Go",
    **extra,
):
    """Create template:action marker with all attributes."""
    machine_attr = f' machine="{machine}"' if machine else ""
    extra_attrs = "".join(f' {k}="{v}"' for k, v in extra.items() if v)
    return (
        f'<!-- template:action name="{name}" action="{action}" type="{record_type}"'
        f'{machine_attr}{extra_attrs} label="{label}" -->'
    )


def _make_template(
    name="test", action="button", record_type="problem", machine="blackout", label="Go", **extra
):
    """Create a complete template: content block + action marker."""
    return _make_content(name) + _make_action_marker(
        name, action, record_type, machine, label, **extra
    )


# ---------------------------------------------------------------------------
# Structural validation tests (start/end markers only)
# ---------------------------------------------------------------------------


@tag("views")
class ValidateMarkersTests(TestCase):
    """Tests for _validate_markers (structural validation of start/end pairs)."""

    def test_no_markers_returns_valid_empty(self):
        result = _validate_markers("Just plain markdown content.")
        self.assertTrue(result.is_valid)
        self.assertEqual(result.content_blocks, [])

    def test_single_valid_block(self):
        content = _make_content("intake")
        result = _validate_markers(content)
        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.content_blocks), 1)
        self.assertEqual(result.content_blocks[0].name, "intake")

    def test_content_extracted_between_markers(self):
        content = _make_content("intake")
        result = _validate_markers(content)
        self.assertIn("step one", result.content_blocks[0].content)
        self.assertIn("step two", result.content_blocks[0].content)

    def test_multiple_blocks(self):
        content = _make_content("a") + _make_content("b") + _make_content("c")
        result = _validate_markers(content)
        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.content_blocks), 3)
        names = {b.name for b in result.content_blocks}
        self.assertEqual(names, {"a", "b", "c"})

    # --- Structural error cases ---

    def test_duplicate_names_has_errors(self):
        content = (
            '<!-- template:start name="dup" -->\n'
            "content\n"
            '<!-- template:end name="dup" -->\n'
            '<!-- template:start name="dup" -->\n'
            "more\n"
            '<!-- template:end name="dup" -->\n'
        )
        result = _validate_markers(content)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("duplicate" in e for e in result.errors))

    def test_nested_blocks_has_errors(self):
        content = (
            '<!-- template:start name="outer" -->\n'
            '<!-- template:start name="inner" -->\n'
            "content\n"
            '<!-- template:end name="inner" -->\n'
            '<!-- template:end name="outer" -->\n'
        )
        result = _validate_markers(content)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("nested" in e for e in result.errors))

    def test_unmatched_end_has_errors(self):
        content = '<!-- template:end name="orphan" -->\n'
        result = _validate_markers(content)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("unmatched" in e for e in result.errors))

    def test_unclosed_start_has_errors(self):
        content = '<!-- template:start name="x" -->\ncontent\n'
        result = _validate_markers(content)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("missing template:end" in e for e in result.errors))

    def test_mismatched_names_has_errors(self):
        content = '<!-- template:start name="a" -->\ncontent\n<!-- template:end name="b" -->\n'
        result = _validate_markers(content)
        self.assertFalse(result.is_valid)

    def test_markers_inside_code_fence_ignored(self):
        """Template markers inside fenced code blocks are not real markers."""
        content = "```\n" + _make_content("example") + "```\n"
        result = _validate_markers(content)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.content_blocks, [])

    def test_markers_inside_and_outside_code_fence(self):
        """Only markers outside fenced code blocks are validated."""
        real = _make_content("real")
        fenced = "```\n" + _make_content("docs-example") + "```\n"
        content = real + "\n" + fenced
        result = _validate_markers(content)
        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.content_blocks), 1)
        self.assertEqual(result.content_blocks[0].name, "real")


# ---------------------------------------------------------------------------
# Author-facing syntax validation tests
# ---------------------------------------------------------------------------


@tag("views")
class ValidateTemplateSyntaxTests(TestCase):
    """Tests for validate_template_syntax (author-facing error messages)."""

    def test_no_markers_returns_empty_list(self):
        self.assertEqual(validate_template_syntax("Just plain markdown."), [])

    def test_valid_template_returns_empty_list(self):
        content = _make_template("intake", action="button", record_type="problem")
        self.assertEqual(validate_template_syntax(content), [])

    def test_action_order_independent(self):
        """action='option,button' is valid (reverse of 'button,option')."""
        content = _make_template("intake", action="option,button", record_type="problem")
        self.assertEqual(validate_template_syntax(content), [])

    def test_invalid_action_part_returns_error(self):
        content = _make_content("intake") + (
            '<!-- template:action name="intake" action="button,widget"'
            ' type="problem" label="Go" -->'
        )
        errors = validate_template_syntax(content)
        self.assertEqual(len(errors), 1)
        self.assertIn("invalid action", errors[0])

    def test_missing_end_returns_error(self):
        content = '<!-- template:start name="x" -->\ncontent\n'
        errors = validate_template_syntax(content)
        self.assertEqual(len(errors), 1)
        self.assertIn("missing template:end", errors[0])
        self.assertIn("'x'", errors[0])

    def test_unmatched_end_returns_error(self):
        content = '<!-- template:end name="orphan" -->\n'
        errors = validate_template_syntax(content)
        self.assertEqual(len(errors), 1)
        self.assertIn("unmatched template:end", errors[0])

    def test_nested_blocks_returns_error(self):
        content = (
            '<!-- template:start name="outer" -->\n'
            '<!-- template:start name="inner" -->\n'
            "content\n"
            '<!-- template:end name="inner" -->\n'
            '<!-- template:end name="outer" -->\n'
        )
        errors = validate_template_syntax(content)
        self.assertTrue(any("nested inside 'outer'" in e for e in errors))

    def test_duplicate_names_returns_error(self):
        content = _make_content("dup") + _make_content("dup")
        errors = validate_template_syntax(content)
        self.assertTrue(any("duplicate name" in e for e in errors))

    def test_invalid_type_returns_error(self):
        content = (
            _make_content("intake")
            + '<!-- template:action name="intake" action="button" type="invalid" label="Go" -->'
        )
        errors = validate_template_syntax(content)
        self.assertEqual(len(errors), 1)
        self.assertIn("invalid type", errors[0])

    def test_missing_required_attrs_returns_error(self):
        content = _make_content("intake") + '<!-- template:action name="intake" -->'
        errors = validate_template_syntax(content)
        self.assertEqual(len(errors), 1)
        self.assertIn("missing required attributes", errors[0])

    def test_orphaned_action_returns_error(self):
        content = _make_action_marker("nonexistent", action="button", record_type="problem")
        errors = validate_template_syntax(content)
        self.assertEqual(len(errors), 1)
        self.assertIn("no matching content block", errors[0])

    def test_invalid_priority_returns_error(self):
        content = (
            _make_content("intake")
            + '<!-- template:action name="intake" action="option" type="problem"'
            ' priority="critical" label="Go" -->'
        )
        errors = validate_template_syntax(content)
        self.assertEqual(len(errors), 1)
        self.assertIn("invalid priority", errors[0])

    def test_unrecognized_marker_reported(self):
        """Typos like 'template:starts' are caught before structural checks."""
        content = (
            '<!-- template:starts name="intake" -->\n'
            "- [ ] step one\n"
            '<!-- template:end name="intake" -->\n'
            + _make_action_marker("intake", action="button", record_type="problem")
        )
        errors = validate_template_syntax(content)
        self.assertEqual(len(errors), 1)
        self.assertIn("template:starts", errors[0])
        self.assertIn("Unrecognized marker", errors[0])

    def test_multiple_unrecognized_markers_reported(self):
        content = '<!-- template:star name="a" -->\n<!-- template:stopp name="a" -->\n'
        errors = validate_template_syntax(content)
        self.assertEqual(len(errors), 2)

    def test_structural_errors_suppress_action_errors(self):
        """Structural errors are reported alone — action errors would be cascading noise."""
        content = (
            '<!-- template:start name="a" -->\ncontent\n'  # missing end
            + _make_action_marker("a", action="button", record_type="problem")
        )
        errors = validate_template_syntax(content)
        self.assertEqual(len(errors), 1)
        self.assertIn("missing template:end", errors[0])

    def test_multiple_action_errors_collected(self):
        """Multiple independent action errors are all reported."""
        content = (
            _make_content("intake")
            + '<!-- template:action name="intake" action="bad" type="problem" label="Go" -->'
            + "\n"
            + _make_action_marker("orphan", action="button", record_type="problem")
        )
        errors = validate_template_syntax(content)
        self.assertEqual(len(errors), 2)

    def test_duplicate_orphaned_action_reported_once(self):
        """Same name missing a content block is reported only once."""
        content = (
            _make_action_marker("orphan", action="button", record_type="problem")
            + "\n"
            + _make_action_marker("orphan", action="option", record_type="problem")
        )
        errors = validate_template_syntax(content)
        self.assertEqual(len(errors), 1)
        self.assertIn("no matching content block", errors[0])

    def test_markers_inside_code_fence_no_errors(self):
        """Template markers inside fenced code blocks produce no validation errors."""
        content = "```\n" + _make_template("example") + "\n```\n"
        self.assertEqual(validate_template_syntax(content), [])

    def test_typo_marker_inside_code_fence_not_flagged(self):
        """Unrecognized marker kinds inside code fences are ignored."""
        content = '```\n<!-- template:bogus name="x" -->\n```\n'
        self.assertEqual(validate_template_syntax(content), [])


# ---------------------------------------------------------------------------
# Token substitution tests
# ---------------------------------------------------------------------------


@tag("views")
class PrepareForRenderingTests(TestCase):
    """Tests for prepare_for_rendering (token substitution)."""

    def test_no_markers_returns_content_unchanged(self):
        content = "Just plain text."
        processed, tokens = prepare_for_rendering(content)
        self.assertEqual(processed, content)
        self.assertEqual(tokens, {})

    def test_markers_stripped_content_preserved(self):
        content = _make_template("intake") + "\nSome other text.\n"
        processed, _tokens = prepare_for_rendering(content)
        self.assertNotIn("template:start", processed)
        self.assertNotIn("template:end", processed)
        self.assertIn("step one", processed)
        self.assertIn("Some other text.", processed)

    def test_button_replaced_with_token(self):
        content = _make_template("intake")
        processed, tokens = prepare_for_rendering(content)
        self.assertNotIn("template:action", processed)
        self.assertEqual(len(tokens), 1)
        the_token = next(iter(tokens))
        self.assertIn(the_token, processed)

    def test_multiple_buttons_for_same_block(self):
        content = (
            _make_content("intake")
            + _make_action_marker("intake")
            + "\n"
            + _make_action_marker("intake")
        )
        processed, tokens = prepare_for_rendering(content)
        self.assertEqual(len(tokens), 2)
        for t in tokens:
            self.assertIn(t, processed)

    def test_orphan_action_silently_removed(self):
        content = _make_content("a") + _make_action_marker("nonexistent")
        processed, tokens = prepare_for_rendering(content)
        self.assertNotIn("template:action", processed)
        for block in tokens.values():
            self.assertNotEqual(block.name, "nonexistent")

    def test_structural_error_returns_original(self):
        content = (
            '<!-- template:start name="outer" -->\n'
            '<!-- template:start name="inner" -->\n'
            "content\n"
            '<!-- template:end name="inner" -->\n'
            '<!-- template:end name="outer" -->\n' + _make_action_marker("outer") + "\n"
        )
        processed, tokens = prepare_for_rendering(content)
        self.assertEqual(tokens, {})
        self.assertIn("template:start", processed)

    def test_orphan_markers_cleaned_when_no_blocks(self):
        content = "Some text\n" + _make_action_marker("missing") + "\nmore text"
        processed, tokens = prepare_for_rendering(content)
        self.assertNotIn("template:action", processed)
        self.assertEqual(tokens, {})

    def test_action_with_invalid_type_skipped(self):
        content = (
            _make_content("x")
            + '<!-- template:action name="x" action="button" type="invalid" label="Go" -->'
        )
        processed, tokens = prepare_for_rendering(content)
        self.assertEqual(tokens, {})
        self.assertNotIn("template:action", processed)

    def test_action_missing_type_skipped(self):
        content = (
            _make_content("x") + '<!-- template:action name="x" action="button" label="Go" -->'
        )
        processed, tokens = prepare_for_rendering(content)
        self.assertEqual(tokens, {})

    def test_action_missing_label_skipped(self):
        content = (
            _make_content("x") + '<!-- template:action name="x" action="button" type="problem" -->'
        )
        processed, tokens = prepare_for_rendering(content)
        self.assertEqual(tokens, {})

    def test_action_invalid_priority_skipped(self):
        content = _make_content("x") + _make_action_marker("x", priority="banana")
        processed, tokens = prepare_for_rendering(content)
        self.assertEqual(tokens, {})
        self.assertNotIn("template:action", processed)

    def test_action_missing_action_attr_skipped(self):
        content = _make_content("x") + '<!-- template:action name="x" type="problem" label="Go" -->'
        processed, tokens = prepare_for_rendering(content)
        self.assertEqual(tokens, {})

    def test_action_invalid_action_attr_skipped(self):
        content = (
            _make_content("x")
            + '<!-- template:action name="x" action="invalid" type="problem" label="Go" -->'
        )
        processed, tokens = prepare_for_rendering(content)
        self.assertEqual(tokens, {})

    def test_action_attrs_populate_action_block(self):
        content = _make_content("intake") + _make_action_marker(
            "intake", "button", "log", "blackout", "Start Log"
        )
        _processed, tokens = prepare_for_rendering(content)
        self.assertEqual(len(tokens), 1)
        block = next(iter(tokens.values()))
        self.assertEqual(block.name, "intake")
        self.assertEqual(block.record_type, "log")
        self.assertEqual(block.machine_slug, "blackout")
        self.assertEqual(block.label, "Start Log")
        self.assertEqual(block.action, "button")
        self.assertIn("step one", block.content)

    def test_action_optional_machine(self):
        content = _make_content("x") + _make_action_marker("x", machine="")
        _processed, tokens = prepare_for_rendering(content)
        self.assertEqual(len(tokens), 1)
        block = next(iter(tokens.values()))
        self.assertEqual(block.machine_slug, "")

    def test_page_type_accepted(self):
        content = _make_content("x") + _make_action_marker("x", record_type="page", machine="")
        _processed, tokens = prepare_for_rendering(content)
        self.assertEqual(len(tokens), 1)
        block = next(iter(tokens.values()))
        self.assertEqual(block.record_type, "page")

    def test_action_tags_populated(self):
        content = _make_content("x") + _make_action_marker(
            "x", record_type="page", machine="", tags="guides,archive"
        )
        _processed, tokens = prepare_for_rendering(content)
        block = next(iter(tokens.values()))
        self.assertEqual(block.tags, "guides,archive")

    def test_action_title_populated(self):
        content = _make_content("x") + _make_action_marker(
            "x", record_type="page", machine="", title="My Title"
        )
        _processed, tokens = prepare_for_rendering(content)
        block = next(iter(tokens.values()))
        self.assertEqual(block.title, "My Title")

    def test_action_priority_populated(self):
        content = _make_content("x") + _make_action_marker("x", priority="task")
        _processed, tokens = prepare_for_rendering(content)
        block = next(iter(tokens.values()))
        self.assertEqual(block.priority, "task")

    def test_action_priority_defaults_to_empty(self):
        content = _make_content("x") + _make_action_marker("x")
        _processed, tokens = prepare_for_rendering(content)
        block = next(iter(tokens.values()))
        self.assertEqual(block.priority, "")

    def test_option_only_marker_stripped_from_display(self):
        """action="option" markers should be stripped, not rendered as buttons."""
        content = _make_content("x") + _make_action_marker("x", action="option")
        processed, tokens = prepare_for_rendering(content)
        self.assertEqual(tokens, {})
        self.assertNotIn("template:action", processed)
        self.assertIn("step one", processed)

    def test_button_option_marker_renders_button(self):
        """action="button,option" markers should render as buttons."""
        content = _make_content("x") + _make_action_marker("x", action="button,option")
        processed, tokens = prepare_for_rendering(content)
        self.assertEqual(len(tokens), 1)
        block = next(iter(tokens.values()))
        self.assertEqual(block.action, "button,option")

    def test_location_attribute_populated(self):
        content = _make_content("x") + _make_action_marker("x", location="main-floor")
        _processed, tokens = prepare_for_rendering(content)
        block = next(iter(tokens.values()))
        self.assertEqual(block.location_slug, "main-floor")

    def test_markers_inside_code_fence_preserved(self):
        """Template markers inside fenced code blocks are kept as literal text."""
        fenced = "```\n" + _make_template("example") + "\n```\n"
        processed, tokens = prepare_for_rendering(fenced)
        self.assertEqual(tokens, {})
        # The markers should still be present as literal text
        self.assertIn('template:start name="example"', processed)
        self.assertIn('template:end name="example"', processed)
        self.assertIn("template:action", processed)

    def test_markers_inside_and_outside_code_fence(self):
        """Markers outside fences are processed; markers inside are preserved."""
        real = _make_template("real")
        fenced = "```\n" + _make_template("docs") + "\n```\n"
        content = real + "\n" + fenced
        processed, tokens = prepare_for_rendering(content)
        # Real template was processed
        self.assertEqual(len(tokens), 1)
        self.assertNotIn('template:start name="real"', processed)
        # Fenced template preserved as literal text
        self.assertIn('template:start name="docs"', processed)
        self.assertIn('template:end name="docs"', processed)


# ---------------------------------------------------------------------------
# Button injection tests
# ---------------------------------------------------------------------------


@tag("views")
class InjectButtonsTests(TestCase):
    """Tests for inject_buttons (post-sanitization HTML injection)."""

    def test_token_replaced_with_button_html(self):
        block = ActionBlock("intake", "problem", "blackout", "Start Intake", "content")
        placeholder = "abc123"
        html = f"<p>Before</p>{placeholder}<p>After</p>"
        result = inject_buttons(html, {placeholder: block}, page_pk=42)
        self.assertIn("wiki-template-action", result)
        self.assertIn("Start Intake", result)
        self.assertIn('class="btn btn--secondary"', result)
        self.assertNotIn(placeholder, result)

    def test_button_url_points_to_prefill_endpoint(self):
        block = ActionBlock("intake", "problem", "blackout", "Start Intake", "content")
        placeholder = "abc123"
        html = f"{placeholder}"
        result = inject_buttons(html, {placeholder: block}, page_pk=42)
        expected_url = reverse(
            "wiki-template-prefill", kwargs={"page_pk": 42, "template_name": "intake"}
        )
        self.assertIn(expected_url, result)

    def test_label_html_escaped(self):
        block = ActionBlock("x", "problem", "", '<script>alert("xss")</script>', "")
        placeholder = "placeholder1"
        result = inject_buttons(placeholder, {placeholder: block}, page_pk=1)
        self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result)


# ---------------------------------------------------------------------------
# URL construction tests
# ---------------------------------------------------------------------------


@tag("views")
class URLConstructionTests(TestCase):
    """Tests for build_template_url and build_create_url."""

    def test_build_template_url(self):
        block = ActionBlock("intake", "problem", "blackout", "Go", "")
        url = build_template_url(block, page_pk=42)
        self.assertEqual(
            url,
            reverse("wiki-template-prefill", kwargs={"page_pk": 42, "template_name": "intake"}),
        )

    def test_build_create_url_problem_with_machine(self):
        block = ActionBlock("x", "problem", "test-machine", "Go", "")
        url = build_create_url(block)
        self.assertEqual(
            url, reverse("problem-report-create-machine", kwargs={"slug": "test-machine"})
        )

    def test_build_create_url_problem_global(self):
        block = ActionBlock("x", "problem", "", "Go", "")
        url = build_create_url(block)
        self.assertEqual(url, reverse("problem-report-create"))

    def test_build_create_url_log_with_machine(self):
        block = ActionBlock("x", "log", "test-machine", "Go", "")
        url = build_create_url(block)
        self.assertEqual(url, reverse("log-create-machine", kwargs={"slug": "test-machine"}))

    def test_build_create_url_log_global(self):
        block = ActionBlock("x", "log", "", "Go", "")
        url = build_create_url(block)
        self.assertEqual(url, reverse("log-create-global"))

    def test_build_create_url_partrequest_with_machine(self):
        block = ActionBlock("x", "partrequest", "test-machine", "Go", "")
        url = build_create_url(block)
        self.assertEqual(
            url, reverse("part-request-create-machine", kwargs={"slug": "test-machine"})
        )

    def test_build_create_url_partrequest_global(self):
        block = ActionBlock("x", "partrequest", "", "Go", "")
        url = build_create_url(block)
        self.assertEqual(url, reverse("part-request-create"))

    def test_build_create_url_page_global(self):
        block = ActionBlock("x", "page", "", "Go", "")
        url = build_create_url(block)
        self.assertEqual(url, reverse("wiki-page-create"))

    def test_build_create_url_page_ignores_machine_slug(self):
        block = ActionBlock("x", "page", "some-machine", "Go", "")
        url = build_create_url(block)
        self.assertEqual(url, reverse("wiki-page-create"))


# ---------------------------------------------------------------------------
# Content extraction tests
# ---------------------------------------------------------------------------


@tag("views")
class ExtractTemplateContentTests(TestCase):
    """Tests for extract_template_content."""

    def test_extract_existing_block(self):
        content = _make_template("intake", "button", "problem")
        block = extract_template_content(content, "intake")
        self.assertIsNotNone(block)
        self.assertEqual(block.name, "intake")
        self.assertEqual(block.record_type, "problem")
        self.assertIn("step one", block.content)

    def test_extract_nonexistent_returns_none(self):
        content = _make_template("intake")
        self.assertIsNone(extract_template_content(content, "missing"))

    def test_extract_correct_block_from_multiple(self):
        content = _make_template("a", "button", "problem") + _make_template("b", "button", "log")
        block = extract_template_content(content, "b")
        self.assertIsNotNone(block)
        self.assertEqual(block.record_type, "log")

    def test_extract_returns_none_on_structural_error(self):
        content = (
            '<!-- template:start name="outer" -->\n'
            '<!-- template:start name="inner" -->\n'
            "content\n"
            '<!-- template:end name="inner" -->\n'
            '<!-- template:end name="outer" -->\n'
        )
        self.assertIsNone(extract_template_content(content, "outer"))

    def test_extract_returns_none_without_action_marker(self):
        """Content block exists but no action marker → None."""
        content = _make_content("intake")
        self.assertIsNone(extract_template_content(content, "intake"))

    def test_extract_returns_none_with_invalid_type(self):
        """Content block exists but action marker has invalid type → None."""
        content = (
            _make_content("x")
            + '<!-- template:action name="x" action="button" type="invalid" label="Go" -->'
        )
        self.assertIsNone(extract_template_content(content, "x"))

    def test_extract_returns_none_with_invalid_priority(self):
        content = _make_content("x") + _make_action_marker("x", priority="banana")
        self.assertIsNone(extract_template_content(content, "x"))

    def test_extract_page_type_with_tags_and_title(self):
        content = _make_content("eval") + _make_action_marker(
            "eval", record_type="page", machine="", tags="@source", title="Evaluation"
        )
        block = extract_template_content(content, "eval")
        self.assertIsNotNone(block)
        self.assertEqual(block.record_type, "page")
        self.assertEqual(block.tags, "@source")
        self.assertEqual(block.title, "Evaluation")

    def test_extract_problem_type_with_priority(self):
        content = _make_content("x") + _make_action_marker("x", priority="task")
        block = extract_template_content(content, "x")
        self.assertIsNotNone(block)
        self.assertEqual(block.priority, "task")

    def test_extract_option_only_marker(self):
        """action="option" markers are still extractable."""
        content = _make_content("x") + _make_action_marker("x", action="option")
        block = extract_template_content(content, "x")
        self.assertIsNotNone(block)
        self.assertEqual(block.action, "option")

    def test_extract_button_option_marker(self):
        content = _make_content("x") + _make_action_marker("x", action="button,option")
        block = extract_template_content(content, "x")
        self.assertIsNotNone(block)
        self.assertEqual(block.action, "button,option")

    def test_extract_location_attribute(self):
        content = _make_content("x") + _make_action_marker("x", location="main-floor")
        block = extract_template_content(content, "x")
        self.assertIsNotNone(block)
        self.assertEqual(block.location_slug, "main-floor")

    def test_extract_template_inside_code_fence_returns_none(self):
        """Templates only inside fenced code blocks are not extractable."""
        content = "```\n" + _make_template("example") + "\n```\n"
        self.assertIsNone(extract_template_content(content, "example"))


# ---------------------------------------------------------------------------
# _resolve_template_tags tests (DB-aware)
# ---------------------------------------------------------------------------


@tag("views")
class ResolveTemplateTagsTests(TestDataMixin, TestCase):
    """Tests for _resolve_template_tags."""

    def _create_page_with_tags(self, *tags):
        page = WikiPage.objects.create(title="Template", slug="template", content="")
        for t in tags:
            WikiPageTag.objects.create(page=page, tag=t, slug="template")
        return page

    def test_explicit_tag(self):
        page = self._create_page_with_tags("guides")
        result = _resolve_template_tags("evaluations", page)
        self.assertEqual(result, ["evaluations"])

    def test_multiple_explicit_tags(self):
        page = self._create_page_with_tags("guides")
        result = _resolve_template_tags("evaluations,archive", page)
        self.assertEqual(result, ["evaluations", "archive"])

    def test_source_expands_to_page_tags(self):
        page = self._create_page_with_tags("guides", "templates")
        result = _resolve_template_tags("@source", page)
        self.assertIn("guides", result)
        self.assertIn("templates", result)

    def test_source_excludes_untagged_sentinel(self):
        # WikiPage post_save signal auto-creates the untagged sentinel tag,
        # so a page with no explicit tags already has only the sentinel.
        page = WikiPage.objects.create(title="Untagged", slug="untagged", content="")
        result = _resolve_template_tags("@source", page)
        self.assertEqual(result, [])

    def test_mixed_source_and_explicit(self):
        page = self._create_page_with_tags("guides")
        result = _resolve_template_tags("@source,archive", page)
        self.assertEqual(result, ["guides", "archive"])

    def test_deduplicates_preserving_order(self):
        page = self._create_page_with_tags("evaluations")
        result = _resolve_template_tags("@source,evaluations,extra", page)
        self.assertEqual(result, ["evaluations", "extra"])

    def test_empty_string_returns_empty(self):
        page = self._create_page_with_tags("guides")
        result = _resolve_template_tags("", page)
        self.assertEqual(result, [])

    def test_whitespace_stripped(self):
        page = self._create_page_with_tags("guides")
        result = _resolve_template_tags("  evaluations , archive  ", page)
        self.assertEqual(result, ["evaluations", "archive"])


# ---------------------------------------------------------------------------
# Integration: rendering (template tag)
# ---------------------------------------------------------------------------


@tag("views")
class WikiContentRenderingTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Integration tests: wiki page renders template buttons correctly."""

    def _create_page(self, content):
        page = WikiPage.objects.create(title="Test Page", slug="test-page", content=content)
        WikiPageTag.objects.create(page=page, tag="docs", slug="test-page")
        return page

    def _get_page_html(self, path="docs/test-page"):
        self.client.force_login(self.maintainer_user)
        response = self.client.get(reverse("wiki-page-detail", args=[path]))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_page_without_templates_renders_normally(self):
        self._create_page("Just some **bold** text.")
        html = self._get_page_html()
        self.assertIn("<strong>bold</strong>", html)
        self.assertNotIn("wiki-template-action", html)

    def test_template_content_renders_as_markdown(self):
        self._create_page(_make_template("intake"))
        html = self._get_page_html()
        self.assertIn("step one", html)
        self.assertIn("task-list-item", html)

    def test_button_renders_in_output(self):
        self._create_page(_make_template("intake"))
        html = self._get_page_html()
        self.assertIn("wiki-template-action", html)
        self.assertIn("Go", html)
        self.assertIn("btn btn--secondary", html)

    def test_button_links_to_prefill_endpoint(self):
        page = self._create_page(_make_template("intake"))
        html = self._get_page_html()
        expected_url = reverse(
            "wiki-template-prefill", kwargs={"page_pk": page.pk, "template_name": "intake"}
        )
        self.assertIn(expected_url, html)

    def test_multiple_buttons_render(self):
        content = (
            _make_content("a")
            + _make_content("b")
            + _make_action_marker("a", "button", "problem", "test-machine", "Report Problem")
            + _make_action_marker("b", "button", "log", "test-machine", "Log Entry")
        )
        self._create_page(content)
        html = self._get_page_html()
        self.assertIn("Report Problem", html)
        self.assertIn("Log Entry", html)

    def test_markers_not_visible_in_output(self):
        self._create_page(_make_template("intake"))
        html = self._get_page_html()
        # Check the rendered content area only (not the hidden textarea
        # which contains raw markdown for checkbox toggle JS).
        display_html = html.split("data-text-display")[1].split("data-text-textarea")[0]
        self.assertNotIn("template:start", display_html)
        self.assertNotIn("template:end", display_html)
        self.assertNotIn("template:action", display_html)

    def test_malformed_markers_degrade_gracefully(self):
        content = '<!-- template:start name="x" -->\ncontent\n'
        self._create_page(content)
        html = self._get_page_html()
        self.assertNotIn("wiki-template-action", html)
        self.assertIn("content", html)


# ---------------------------------------------------------------------------
# wiki_tags template library
# ---------------------------------------------------------------------------


@tag("views")
class WikiTagsLibraryTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Smoke test for the wiki_tags template tag library."""

    def test_render_wiki_content_loads_and_renders(self):
        """{% load wiki_tags %} and {% render_wiki_content page %} work."""
        page = WikiPage.objects.create(title="Smoke", slug="smoke", content="**bold**")
        WikiPageTag.objects.create(page=page, tag="docs", slug="smoke")
        self.client.force_login(self.maintainer_user)
        response = self.client.get(reverse("wiki-page-detail", args=["docs/smoke"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<strong>bold</strong>")


# ---------------------------------------------------------------------------
# Integration: prefill view
# ---------------------------------------------------------------------------


@tag("views")
class WikiTemplatePrefillViewTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Integration tests for WikiTemplatePrefillView."""

    def _create_page(self, content):
        return WikiPage.objects.create(title="Test Page", slug="test-page", content=content)

    def test_redirects_to_problem_create(self):
        page = self._create_page(
            _make_template("intake", "button", "problem", "test-machine", "Go")
        )
        self.client.force_login(self.maintainer_user)
        url = reverse(
            "wiki-template-prefill", kwargs={"page_pk": page.pk, "template_name": "intake"}
        )
        response = self.client.get(url)
        expected = reverse("problem-report-create-machine", kwargs={"slug": "test-machine"})
        self.assertRedirects(response, expected, fetch_redirect_response=False)

    def test_redirects_to_log_create(self):
        page = self._create_page(_make_template("x", "button", "log", "test-machine", "Go"))
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-template-prefill", kwargs={"page_pk": page.pk, "template_name": "x"})
        response = self.client.get(url)
        expected = reverse("log-create-machine", kwargs={"slug": "test-machine"})
        self.assertRedirects(response, expected, fetch_redirect_response=False)

    def test_redirects_to_partrequest_create(self):
        page = self._create_page(_make_template("x", "button", "partrequest", "", "Go"))
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-template-prefill", kwargs={"page_pk": page.pk, "template_name": "x"})
        response = self.client.get(url)
        expected = reverse("part-request-create")
        self.assertRedirects(response, expected, fetch_redirect_response=False)

    def test_stores_correct_field_in_session(self):
        page = self._create_page(_make_template("intake", "button", "problem"))
        self.client.force_login(self.maintainer_user)
        url = reverse(
            "wiki-template-prefill", kwargs={"page_pk": page.pk, "template_name": "intake"}
        )
        self.client.get(url)
        prefill = self.client.session.get("form_prefill")
        self.assertIsNotNone(prefill)
        self.assertEqual(prefill["field"], "description")
        self.assertIn("step one", prefill["content"])

    def test_log_type_uses_text_field(self):
        page = self._create_page(_make_template("x", "button", "log"))
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-template-prefill", kwargs={"page_pk": page.pk, "template_name": "x"})
        self.client.get(url)
        self.assertEqual(self.client.session["form_prefill"]["field"], "text")

    def test_partrequest_type_uses_text_field(self):
        page = self._create_page(_make_template("x", "button", "partrequest"))
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-template-prefill", kwargs={"page_pk": page.pk, "template_name": "x"})
        self.client.get(url)
        self.assertEqual(self.client.session["form_prefill"]["field"], "text")

    def test_missing_page_returns_404(self):
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-template-prefill", kwargs={"page_pk": 99999, "template_name": "x"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_missing_template_returns_404(self):
        page = self._create_page(_make_template("intake"))
        self.client.force_login(self.maintainer_user)
        url = reverse(
            "wiki-template-prefill", kwargs={"page_pk": page.pk, "template_name": "missing"}
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_requires_login(self):
        page = self._create_page(_make_template("intake"))
        url = reverse(
            "wiki-template-prefill", kwargs={"page_pk": page.pk, "template_name": "intake"}
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_page_type_redirects_to_wiki_create(self):
        content = _make_content("eval") + _make_action_marker(
            "eval", record_type="page", machine="", label="Go"
        )
        page = self._create_page(content)
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-template-prefill", kwargs={"page_pk": page.pk, "template_name": "eval"})
        response = self.client.get(url)
        self.assertRedirects(response, reverse("wiki-page-create"), fetch_redirect_response=False)

    def test_page_type_stores_content_field(self):
        content = _make_content("eval") + _make_action_marker(
            "eval", record_type="page", machine="", label="Go"
        )
        page = self._create_page(content)
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-template-prefill", kwargs={"page_pk": page.pk, "template_name": "eval"})
        self.client.get(url)
        prefill = self.client.session.get("form_prefill")
        self.assertEqual(prefill["field"], "content")
        self.assertIn("step one", prefill["content"])

    def test_page_type_stores_tags_in_session(self):
        content = _make_content("eval") + _make_action_marker(
            "eval", record_type="page", machine="", tags="guides", label="Go"
        )
        page = self._create_page(content)
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-template-prefill", kwargs={"page_pk": page.pk, "template_name": "eval"})
        self.client.get(url)
        self.assertEqual(self.client.session.get("form_prefill_tags"), ["guides"])

    def test_page_type_stores_title_in_session(self):
        content = _make_content("eval") + _make_action_marker(
            "eval", record_type="page", machine="", title="Evaluation", label="Go"
        )
        page = self._create_page(content)
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-template-prefill", kwargs={"page_pk": page.pk, "template_name": "eval"})
        self.client.get(url)
        self.assertEqual(self.client.session.get("form_prefill_title"), "Evaluation")

    def test_page_type_resolves_source_tags(self):
        content = _make_content("eval") + _make_action_marker(
            "eval", record_type="page", machine="", tags="@source", label="Go"
        )
        page = self._create_page(content)
        WikiPageTag.objects.create(page=page, tag="templates", slug="test-page")
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-template-prefill", kwargs={"page_pk": page.pk, "template_name": "eval"})
        self.client.get(url)
        # _create_page doesn't add tags, but we added "templates" above
        self.assertIn("templates", self.client.session.get("form_prefill_tags", []))

    def test_page_type_no_tags_omits_session_key(self):
        content = _make_content("eval") + _make_action_marker(
            "eval", record_type="page", machine="", label="Go"
        )
        page = self._create_page(content)
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-template-prefill", kwargs={"page_pk": page.pk, "template_name": "eval"})
        self.client.get(url)
        self.assertNotIn("form_prefill_tags", self.client.session)

    def test_page_type_no_title_omits_session_key(self):
        content = _make_content("eval") + _make_action_marker(
            "eval", record_type="page", machine="", label="Go"
        )
        page = self._create_page(content)
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-template-prefill", kwargs={"page_pk": page.pk, "template_name": "eval"})
        self.client.get(url)
        self.assertNotIn("form_prefill_title", self.client.session)

    def test_priority_stored_in_session_extra_initial(self):
        page = self._create_page(_make_content("x") + _make_action_marker("x", priority="task"))
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-template-prefill", kwargs={"page_pk": page.pk, "template_name": "x"})
        self.client.get(url)
        prefill = self.client.session.get("form_prefill")
        self.assertEqual(prefill["extra_initial"], {"priority": "task"})

    def test_no_priority_omits_extra_initial(self):
        page = self._create_page(_make_template("x"))
        self.client.force_login(self.maintainer_user)
        url = reverse("wiki-template-prefill", kwargs={"page_pk": page.pk, "template_name": "x"})
        self.client.get(url)
        prefill = self.client.session.get("form_prefill")
        self.assertNotIn("extra_initial", prefill)

    def test_stores_template_content_url_in_session(self):
        page = self._create_page(_make_template("intake", "button", "problem"))
        self.client.force_login(self.maintainer_user)
        url = reverse(
            "wiki-template-prefill", kwargs={"page_pk": page.pk, "template_name": "intake"}
        )
        self.client.get(url)
        prefill = self.client.session.get("form_prefill")
        expected_url = reverse(
            "api-wiki-template-content",
            kwargs={"page_pk": page.pk, "template_name": "intake"},
        )
        self.assertEqual(prefill["template_content_url"], expected_url)


# ---------------------------------------------------------------------------
# Integration: FormPrefillMixin
# ---------------------------------------------------------------------------


@tag("views")
class FormPrefillMixinTests(SuppressRequestLogsMixin, TestDataMixin, TestCase):
    """Integration tests for FormPrefillMixin via actual create views."""

    def test_problem_report_form_prefilled(self):
        self.client.force_login(self.maintainer_user)
        session = self.client.session
        session["form_prefill"] = {"field": "description", "content": "Pre-filled text"}
        session.save()
        response = self.client.get(reverse("problem-report-create"))
        self.assertContains(response, "Pre-filled text")

    def test_extra_initial_prefills_priority(self):
        self.client.force_login(self.maintainer_user)
        session = self.client.session
        session["form_prefill"] = {
            "field": "description",
            "content": "Task text",
            "extra_initial": {"priority": "task"},
        }
        session.save()
        response = self.client.get(reverse("problem-report-create"))
        self.assertContains(response, "Task text")
        # Priority "task" should be pre-selected in the dropdown
        self.assertContains(response, '<option value="task" selected')

    def test_log_entry_form_prefilled(self):
        self.client.force_login(self.maintainer_user)
        session = self.client.session
        session["form_prefill"] = {"field": "text", "content": "Log content here"}
        session.save()
        response = self.client.get(reverse("log-create-global"))
        self.assertContains(response, "Log content here")

    def test_part_request_form_prefilled(self):
        self.client.force_login(self.maintainer_user)
        session = self.client.session
        session["form_prefill"] = {"field": "text", "content": "Part request text"}
        session.save()
        response = self.client.get(reverse("part-request-create"))
        self.assertContains(response, "Part request text")

    def test_session_cleared_after_prefill(self):
        self.client.force_login(self.maintainer_user)
        session = self.client.session
        session["form_prefill"] = {"field": "description", "content": "one-shot"}
        session.save()
        self.client.get(reverse("problem-report-create"))
        self.assertNotIn("form_prefill", self.client.session)

    def test_no_session_data_form_unchanged(self):
        self.client.force_login(self.maintainer_user)
        response = self.client.get(reverse("problem-report-create"))
        self.assertEqual(response.status_code, 200)

    def test_wiki_page_content_prefilled(self):
        self.client.force_login(self.maintainer_user)
        session = self.client.session
        session["form_prefill"] = {"field": "content", "content": "- [ ] checklist item"}
        session.save()
        response = self.client.get(reverse("wiki-page-create"))
        self.assertContains(response, "- [ ] checklist item")

    def test_wiki_page_title_prefilled(self):
        self.client.force_login(self.maintainer_user)
        session = self.client.session
        session["form_prefill_title"] = "Evaluation Checklist"
        session.save()
        response = self.client.get(reverse("wiki-page-create"))
        self.assertContains(response, "Evaluation Checklist")

    def test_wiki_page_tags_prefilled(self):
        self.client.force_login(self.maintainer_user)
        session = self.client.session
        session["form_prefill_tags"] = ["guides", "evaluations"]
        session.save()
        response = self.client.get(reverse("wiki-page-create"))
        # Tags render in the tag chip component's data attribute and hidden inputs
        self.assertContains(response, 'data-initial-tags="guides, evaluations"')
        self.assertContains(response, 'name="tags" value="guides"')
        self.assertContains(response, 'name="tags" value="evaluations"')

    def test_wiki_page_session_cleared_after_prefill(self):
        self.client.force_login(self.maintainer_user)
        session = self.client.session
        session["form_prefill"] = {"field": "content", "content": "template"}
        session["form_prefill_tags"] = ["guides"]
        session["form_prefill_title"] = "Title"
        session.save()
        self.client.get(reverse("wiki-page-create"))
        self.assertNotIn("form_prefill", self.client.session)
        self.assertNotIn("form_prefill_tags", self.client.session)
        self.assertNotIn("form_prefill_title", self.client.session)

    def test_template_content_url_in_context(self):
        """Prefill with template_content_url renders data-preselect-url."""
        self.client.force_login(self.maintainer_user)
        session = self.client.session
        session["form_prefill"] = {
            "field": "description",
            "content": "Template content",
            "template_content_url": "/api/wiki/pages/1/templates/intake/content/",
        }
        session.save()
        response = self.client.get(reverse("problem-report-create"))
        self.assertContains(
            response,
            'data-preselect-url="/api/wiki/pages/1/templates/intake/content/"',
        )

    def test_no_template_url_no_preselect_attr(self):
        """Prefill without template_content_url omits data-preselect-url."""
        self.client.force_login(self.maintainer_user)
        session = self.client.session
        session["form_prefill"] = {
            "field": "description",
            "content": "Plain prefill",
        }
        session.save()
        response = self.client.get(reverse("problem-report-create"))
        self.assertNotContains(response, "data-preselect-url")
