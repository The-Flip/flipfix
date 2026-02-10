"""Tests for the render_markdown template filter."""

from django.test import TestCase, tag

from the_flip.apps.core.markdown import (
    _convert_task_list_items,
    fenced_code_ranges,
    render_markdown_html,
)

# Tests use the pipeline function directly; the template filter is a thin mark_safe wrapper.
render_markdown = render_markdown_html


@tag("views")
class RenderMarkdownFilterTests(TestCase):
    """Tests for the render_markdown template filter."""

    def test_empty_text_returns_empty_string(self):
        """Empty or None input returns empty string."""
        self.assertEqual(render_markdown(""), "")
        self.assertEqual(render_markdown(None), "")

    def test_basic_markdown_rendering(self):
        """Basic markdown syntax is converted to HTML."""
        # Bold
        result = render_markdown("**bold text**")
        self.assertIn("<strong>bold text</strong>", result)

        # Italic
        result = render_markdown("*italic text*")
        self.assertIn("<em>italic text</em>", result)

        # Inline code
        result = render_markdown("`code`")
        self.assertIn("<code>code</code>", result)

    def test_table_rendering(self):
        """GFM-style pipe tables are converted to HTML tables."""
        result = render_markdown("| a | b |\n| - | - |\n| 1 | 2 |")
        self.assertIn("<table>", result)
        self.assertIn("<th>a</th>", result)
        self.assertIn("<td>1</td>", result)

    def test_strikethrough_rendering(self):
        """Double tildes render as strikethrough."""
        result = render_markdown("~~deleted~~")
        self.assertIn("<s>deleted</s>", result)

    def test_list_rendering(self):
        """Markdown lists are converted to HTML lists."""
        # Unordered list
        result = render_markdown("- item 1\n- item 2")
        self.assertIn("<ul>", result)
        self.assertIn("<li>item 1</li>", result)
        self.assertIn("<li>item 2</li>", result)

        # Ordered list
        result = render_markdown("1. first\n2. second")
        self.assertIn("<ol>", result)
        self.assertIn("<li>first</li>", result)
        self.assertIn("<li>second</li>", result)

    def test_list_after_paragraph_without_blank_line(self):
        """Lists work without a blank line after a paragraph (CommonMark behavior)."""
        # Unordered
        result = render_markdown("Here is some text:\n- item 1\n- item 2")
        self.assertIn("<ul>", result)
        self.assertIn("<li>item 1</li>", result)

        # Ordered
        result = render_markdown("Here is some text:\n1. first\n2. second")
        self.assertIn("<ol>", result)
        self.assertIn("<li>first</li>", result)

    def test_newlines_converted_to_breaks(self):
        """Single newlines are converted to <br> tags (nl2br extension)."""
        result = render_markdown("line 1\nline 2")
        self.assertIn("<br", result)

    def test_fenced_code_blocks(self):
        """Fenced code blocks are rendered as pre/code."""
        result = render_markdown("```\ncode block\n```")
        self.assertIn("<pre>", result)
        self.assertIn("<code>", result)

    def test_links_rendered_with_href(self):
        """Links are rendered with href attribute preserved."""
        result = render_markdown("[link text](https://example.com)")
        self.assertIn("<a", result)
        self.assertIn('href="https://example.com"', result)
        self.assertIn("link text</a>", result)

    def test_xss_script_tags_stripped(self):
        """Script tags are stripped for XSS protection."""
        result = render_markdown("<script>alert('xss')</script>")
        self.assertNotIn("<script>", result)
        self.assertNotIn("</script>", result)

    def test_xss_event_handlers_stripped(self):
        """Event handler attributes are stripped for XSS protection."""
        result = render_markdown('<a href="#" onclick="alert(1)">click</a>')
        self.assertNotIn("onclick", result)

    def test_xss_javascript_urls_stripped(self):
        """JavaScript URLs are not rendered as clickable links."""
        result = render_markdown("[click](javascript:alert(1))")
        # markdown-it-py refuses to render javascript: URLs as links entirely,
        # so no <a> tag is created. Verify no clickable link exists.
        self.assertNotIn("<a", result)

    def test_dangerous_tags_stripped(self):
        """Dangerous HTML tags are stripped."""
        # iframe
        result = render_markdown('<iframe src="http://evil.com"></iframe>')
        self.assertNotIn("<iframe", result)

        # object
        result = render_markdown('<object data="http://evil.com"></object>')
        self.assertNotIn("<object", result)

        # style (can be used for CSS injection)
        result = render_markdown("<style>body{display:none}</style>")
        self.assertNotIn("<style>", result)

    def test_safe_html_tags_preserved(self):
        """Allowed HTML tags in markdown are preserved."""
        # Blockquote
        result = render_markdown("> quoted text")
        self.assertIn("<blockquote>", result)

        # Headings
        result = render_markdown("## Heading")
        self.assertIn("<h2>", result)


@tag("views")
class LinkifyTests(TestCase):
    """Tests for automatic URL linkification in markdown."""

    def test_bare_url_linked(self):
        """Bare URLs are converted to clickable links."""
        result = render_markdown("Visit https://example.com for details")
        self.assertIn('<a href="https://example.com"', result)

    def test_www_url_linked(self):
        """www URLs without scheme are linked."""
        result = render_markdown("Visit www.example.com for details")
        self.assertIn("example.com", result)
        self.assertIn("<a", result)

    def test_url_in_markdown_link_not_double_linked(self):
        """URLs already in markdown link syntax are not double-linked."""
        result = render_markdown("[click here](https://example.com)")
        # Should have exactly one <a> tag, not nested
        self.assertEqual(result.count("<a"), 1)

    def test_url_in_inline_code_not_linked(self):
        """URLs inside inline code are NOT converted to links."""
        result = render_markdown("Use `https://example.com/api` for the endpoint")
        # The URL inside backticks should not be wrapped in <a>
        self.assertIn("<code>https://example.com/api</code>", result)
        # Only the code tag, no link inside it
        self.assertNotIn("<a", result)

    def test_url_in_fenced_code_block_not_linked(self):
        """URLs inside fenced code blocks are NOT converted to links."""
        result = render_markdown("```\nhttps://example.com\n```")
        self.assertIn("<pre>", result)
        self.assertNotIn("<a", result)

    def test_url_with_trailing_period(self):
        """Trailing period is not included in the URL."""
        result = render_markdown("See https://example.com.")
        self.assertIn('href="https://example.com"', result)
        # Period should be outside the link
        self.assertNotIn('href="https://example.com."', result)


@tag("views")
class TaskListCheckboxTests(TestCase):
    """Tests for task list checkbox rendering in markdown."""

    def test_unchecked_checkbox_rendered(self):
        """Unchecked task list items render as checkbox inputs."""
        result = render_markdown("- [ ] todo item")
        self.assertIn('class="task-list-item"', result)
        self.assertIn('type="checkbox"', result)
        self.assertIn('data-checkbox-index="0"', result)
        self.assertIn("disabled", result)
        # Should NOT have checked attribute
        self.assertNotIn(" checked", result)

    def test_unchecked_empty_brackets_rendered(self):
        """Empty brackets [] (no space) also render as unchecked checkbox."""
        result = render_markdown("- [] todo item")
        self.assertIn('class="task-list-item"', result)
        self.assertIn('type="checkbox"', result)
        self.assertIn('data-checkbox-index="0"', result)
        self.assertNotIn(" checked", result)

    def test_unchecked_multiple_spaces_rendered(self):
        """Multiple spaces [  ] also render as unchecked checkbox (graceful handling)."""
        result = render_markdown("- [  ] todo item")
        self.assertIn('class="task-list-item"', result)
        self.assertIn('type="checkbox"', result)
        self.assertIn('data-checkbox-index="0"', result)
        self.assertNotIn(" checked", result)

    def test_checked_checkbox_rendered(self):
        """Checked task list items render as checked checkbox inputs."""
        result = render_markdown("- [x] done item")
        self.assertIn('class="task-list-item"', result)
        self.assertIn('type="checkbox"', result)
        self.assertIn(" checked", result)
        self.assertIn('data-checkbox-index="0"', result)

    def test_checked_uppercase_rendered(self):
        """Uppercase [X] also renders as checked."""
        result = render_markdown("- [X] done item")
        self.assertIn(" checked", result)
        self.assertIn('type="checkbox"', result)

    def test_multiple_checkboxes_sequential_indices(self):
        """Multiple checkboxes get sequential indices in document order."""
        result = render_markdown("- [ ] first\n- [x] second\n- [ ] third")
        self.assertIn('data-checkbox-index="0"', result)
        self.assertIn('data-checkbox-index="1"', result)
        self.assertIn('data-checkbox-index="2"', result)

    def test_index_ordering_matches_document_order(self):
        """Indices follow document order, not grouping by checked/unchecked."""
        result = render_markdown("- [x] checked\n- [ ] unchecked\n- [x] checked2")
        # Split by task-list-item to check each one
        parts = result.split('class="task-list-item"')
        # First checkbox (checked) should be index 0
        self.assertIn('data-checkbox-index="0"', parts[1])
        self.assertIn(" checked", parts[1])
        # Second checkbox (unchecked) should be index 1
        self.assertIn('data-checkbox-index="1"', parts[2])
        # Third checkbox (checked) should be index 2
        self.assertIn('data-checkbox-index="2"', parts[3])

    def test_checkboxes_render_disabled(self):
        """All checkboxes render with disabled attribute by default."""
        result = render_markdown("- [ ] item\n- [x] item")
        # Count disabled attributes - should be 2
        self.assertEqual(result.count("disabled"), 2)

    def test_checkbox_not_in_paragraph(self):
        """Text like [ ] outside a list item is NOT converted to checkbox."""
        result = render_markdown("[ ] not a checkbox")
        self.assertNotIn('type="checkbox"', result)
        self.assertNotIn("task-list-item", result)

    def test_regular_list_items_unchanged(self):
        """Regular list items without [ ] are not affected."""
        result = render_markdown("- regular item")
        self.assertNotIn("task-list-item", result)
        self.assertNotIn('type="checkbox"', result)
        self.assertIn("<li>regular item</li>", result)

    def test_mixed_regular_and_task_items(self):
        """Regular and task list items coexist correctly."""
        result = render_markdown("- regular\n- [ ] task\n- also regular")
        self.assertEqual(result.count("task-list-item"), 1)
        self.assertEqual(result.count('type="checkbox"'), 1)
        self.assertIn("<li>regular</li>", result)
        self.assertIn("<li>also regular</li>", result)

    def test_checkbox_with_inline_formatting(self):
        """Checkboxes work with bold, italic, code, and links in the text."""
        result = render_markdown("- [ ] item with **bold** and `code`")
        self.assertIn('type="checkbox"', result)
        self.assertIn("<strong>bold</strong>", result)
        self.assertIn("<code>code</code>", result)

    def test_nested_task_in_regular_list(self):
        """Task list nested inside regular list works correctly."""
        result = render_markdown("- Parent\n  - [ ] nested task")
        self.assertIn("task-list-item", result)
        self.assertIn('type="checkbox"', result)

    def test_multi_line_list_item(self):
        """Multi-line list items with continuation work correctly."""
        result = render_markdown("- [ ] Task with\n  continuation text")
        self.assertIn("task-list-item", result)
        self.assertIn('type="checkbox"', result)

    def test_code_block_not_converted(self):
        """Task list markers inside code blocks are NOT converted."""
        result = render_markdown("```\n- [ ] inside code\n```")
        self.assertNotIn("task-list-item", result)
        self.assertNotIn('type="checkbox"', result)
        # The literal text should be preserved in the code block
        self.assertIn("[ ]", result)

    def test_tilde_code_block_not_converted(self):
        """Task list markers inside tilde-fenced code blocks are NOT converted."""
        result = render_markdown("~~~\n- [ ] inside tilde code\n~~~")
        self.assertNotIn("task-list-item", result)
        self.assertNotIn('type="checkbox"', result)
        self.assertIn("[ ]", result)

    def test_inline_code_not_converted(self):
        """Task list markers inside inline code are NOT converted."""
        result = render_markdown("Use `- [ ] syntax` for tasks")
        self.assertNotIn("task-list-item", result)
        self.assertNotIn('type="checkbox"', result)

    def test_blockquote_with_task_list(self):
        """Task lists inside blockquotes ARE converted (valid use case)."""
        result = render_markdown("> - [ ] quoted task")
        self.assertIn("task-list-item", result)
        self.assertIn('type="checkbox"', result)
        self.assertIn("<blockquote>", result)

    def test_ordered_list_task_items(self):
        """Task list markers work with ordered lists too."""
        result = render_markdown("1. [ ] first task\n2. [x] second task")
        self.assertIn("task-list-item", result)
        self.assertEqual(result.count('type="checkbox"'), 2)

    def test_convert_task_list_items_directly(self):
        """Test the _convert_task_list_items function directly."""
        # Test unchecked
        html = "<li>[ ] task</li>"
        result = _convert_task_list_items(html)
        self.assertIn('class="task-list-item"', result)
        self.assertIn('data-checkbox-index="0"', result)
        self.assertNotIn(" checked", result)

        # Test checked
        html = "<li>[x] task</li>"
        result = _convert_task_list_items(html)
        self.assertIn(" checked", result)

    def test_whitespace_between_li_and_bracket(self):
        """Whitespace between <li> and [ ] is handled correctly."""
        html = "<li>  [ ] task with leading spaces</li>"
        result = _convert_task_list_items(html)
        self.assertIn("task-list-item", result)
        self.assertIn('type="checkbox"', result)

    def test_blank_line_between_items_produces_paragraph_wrapped_checkbox(self):
        """Blank lines between list items wrap content in <p> tags - must still work."""
        # Blank lines between items cause markdown to wrap content in <p> tags
        result = render_markdown("- [ ] item one\n\n- [x] item two")
        self.assertIn("task-list-item", result)
        self.assertEqual(result.count('type="checkbox"'), 2)
        # First should be unchecked, second checked
        self.assertIn('data-checkbox-index="0"', result)
        self.assertIn('data-checkbox-index="1"', result)


@tag("views")
class FencedCodeRangesTests(TestCase):
    """Tests for fenced_code_ranges (character-position ranges of code fences)."""

    def test_single_backtick_fence(self):
        content = "before\n```\ncode\n```\nafter\n"
        ranges = fenced_code_ranges(content)
        self.assertEqual(len(ranges), 1)
        start, end = ranges[0]
        # The range should cover the entire fenced block including markers
        self.assertEqual(content[start:end].strip(), "```\ncode\n```")

    def test_multiple_fenced_code_blocks(self):
        content = "```\nfirst\n```\ntext\n```\nsecond\n```\n"
        ranges = fenced_code_ranges(content)
        self.assertEqual(len(ranges), 2)

    def test_no_fenced_code_blocks(self):
        content = "Just plain text with no fences."
        self.assertEqual(fenced_code_ranges(content), [])

    def test_tilde_fence(self):
        content = "~~~\ntilde code\n~~~\n"
        ranges = fenced_code_ranges(content)
        self.assertEqual(len(ranges), 1)
        start, end = ranges[0]
        self.assertIn("tilde code", content[start:end])
