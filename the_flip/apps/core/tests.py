"""Tests for core app template tags and utilities."""

import shutil
import tempfile
from pathlib import Path

from django.test import TestCase, override_settings, tag

from the_flip.apps.core.templatetags.core_extras import (
    display_name_with_username,
    render_markdown,
)
from the_flip.apps.core.test_utils import create_user


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
        result = render_markdown("[click](javascript:alert(1))")
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


class DisplayNameWithUsernameFilterTests(TestCase):
    """Tests for the display_name_with_username template filter."""

    def test_none_returns_empty_string(self):
        """None input returns empty string."""
        self.assertEqual(display_name_with_username(None), "")

    def test_username_only(self):
        """User with no name returns just username."""
        user = create_user(username="jsmith")
        self.assertEqual(display_name_with_username(user), "jsmith")

    def test_first_name_only(self):
        """User with only first name returns 'First (username)'."""
        user = create_user(username="jsmith", first_name="John")
        self.assertEqual(display_name_with_username(user), "John (jsmith)")

    def test_last_name_only(self):
        """User with only last name returns 'Last (username)'."""
        user = create_user(username="jsmith", last_name="Smith")
        self.assertEqual(display_name_with_username(user), "Smith (jsmith)")

    def test_full_name(self):
        """User with full name returns 'First Last (username)'."""
        user = create_user(username="jsmith", first_name="John", last_name="Smith")
        self.assertEqual(display_name_with_username(user), "John Smith (jsmith)")


@tag("views")
@override_settings(MEDIA_URL="/media/")
class ServeMediaViewTests(TestCase):
    """Tests for the serve_media view that serves user-uploaded files."""

    def setUp(self):
        """Create a temporary directory with test files."""
        self.temp_dir = tempfile.mkdtemp()
        self.media_root = Path(self.temp_dir)

        # Create test files
        self.test_image = self.media_root / "test-image.jpg"
        self.test_image.write_bytes(b"\xff\xd8\xff\xe0")  # JPEG magic bytes

        self.test_video = self.media_root / "test-video.mp4"
        self.test_video.write_bytes(b"\x00\x00\x00\x18ftypmp42")

        # Create a subdirectory with a file
        subdir = self.media_root / "uploads"
        subdir.mkdir()
        self.nested_file = subdir / "nested.txt"
        self.nested_file.write_text("nested content")

    def tearDown(self):
        """Clean up temporary files."""
        shutil.rmtree(self.temp_dir)

    def test_serves_file_with_correct_content_type(self):
        """Valid file returns 200 with correct Content-Type."""
        with override_settings(MEDIA_ROOT=self.media_root):
            response = self.client.get("/media/test-image.jpg")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")

    def test_serves_file_with_cache_control_header(self):
        """Media files include immutable Cache-Control header for 1 year."""
        with override_settings(MEDIA_ROOT=self.media_root):
            response = self.client.get("/media/test-image.jpg")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "public, max-age=31536000, immutable")

    def test_serves_file_with_content_length(self):
        """Response includes Content-Length header."""
        with override_settings(MEDIA_ROOT=self.media_root):
            response = self.client.get("/media/test-image.jpg")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Length"], "4")  # 4 bytes of JPEG magic

    def test_serves_nested_file(self):
        """Files in subdirectories are served correctly."""
        with override_settings(MEDIA_ROOT=self.media_root):
            response = self.client.get("/media/uploads/nested.txt")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain")

    def test_serves_video_with_correct_content_type(self):
        """Video files return correct Content-Type."""
        with override_settings(MEDIA_ROOT=self.media_root):
            response = self.client.get("/media/test-video.mp4")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "video/mp4")

    def test_missing_file_returns_404(self):
        """Non-existent file returns 404."""
        with override_settings(MEDIA_ROOT=self.media_root):
            response = self.client.get("/media/nonexistent.jpg")

        self.assertEqual(response.status_code, 404)

    def test_directory_traversal_blocked(self):
        """Path traversal attempts return 404."""
        with override_settings(MEDIA_ROOT=self.media_root):
            # Attempt to escape MEDIA_ROOT
            response = self.client.get("/media/../../../etc/passwd")

        self.assertEqual(response.status_code, 404)

    def test_directory_traversal_encoded_blocked(self):
        """URL-encoded path traversal attempts return 404."""
        with override_settings(MEDIA_ROOT=self.media_root):
            # %2e = '.', %2f = '/'
            response = self.client.get("/media/%2e%2e/%2e%2e/etc/passwd")

        self.assertEqual(response.status_code, 404)

    def test_directory_returns_404(self):
        """Requesting a directory (not a file) returns 404."""
        with override_settings(MEDIA_ROOT=self.media_root):
            response = self.client.get("/media/uploads/")

        self.assertEqual(response.status_code, 404)

    def test_empty_path_returns_404(self):
        """Requesting /media/ with no file path returns 404."""
        with override_settings(MEDIA_ROOT=self.media_root):
            response = self.client.get("/media/")

        self.assertEqual(response.status_code, 404)
