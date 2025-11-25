"""Tests for core app template tags and utilities."""

from django.test import TestCase

from the_flip.apps.core.templatetags.core_extras import render_markdown


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
        """JavaScript URLs are stripped for XSS protection."""
        result = render_markdown('[click](javascript:alert(1))')
        # The link should be sanitized - either href removed or link not rendered
        self.assertNotIn("javascript:", result)

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
