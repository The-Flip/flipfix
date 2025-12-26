"""Tests for core app template tags and utilities."""

import shutil
import tempfile
from pathlib import Path

from django import forms
from django.test import TestCase, override_settings, tag

from the_flip.apps.core.forms import StyledFormMixin
from the_flip.apps.core.templatetags.core_extras import (
    display_name_with_username,
    icon,
    machine_status_btn_class,
    machine_status_css_class,
    machine_status_icon,
    render_markdown,
)
from the_flip.apps.core.test_utils import create_user


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


@tag("views")
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


@tag("views")
class MachineStatusFilterTests(TestCase):
    """Tests for MachineInstance.operational_status template filters."""

    def test_machine_status_css_class_good(self):
        """Good status returns pill--status-good."""
        self.assertEqual(machine_status_css_class("good"), "pill--status-good")

    def test_machine_status_css_class_fixing(self):
        """Fixing status returns pill--status-fixing."""
        self.assertEqual(machine_status_css_class("fixing"), "pill--status-fixing")

    def test_machine_status_css_class_broken(self):
        """Broken status returns pill--status-broken."""
        self.assertEqual(machine_status_css_class("broken"), "pill--status-broken")

    def test_machine_status_css_class_unknown(self):
        """Unknown status returns pill--neutral."""
        self.assertEqual(machine_status_css_class("unknown"), "pill--neutral")

    def test_machine_status_css_class_fallback(self):
        """Unrecognized status returns pill--neutral."""
        self.assertEqual(machine_status_css_class("invalid"), "pill--neutral")
        self.assertEqual(machine_status_css_class(""), "pill--neutral")
        self.assertEqual(machine_status_css_class(None), "pill--neutral")

    def test_machine_status_icon_good(self):
        """Good status returns check icon (unprefixed for use with {% icon %} tag)."""
        self.assertEqual(machine_status_icon("good"), "check")

    def test_machine_status_icon_fixing(self):
        """Fixing status returns wrench icon (unprefixed for use with {% icon %} tag)."""
        self.assertEqual(machine_status_icon("fixing"), "wrench")

    def test_machine_status_icon_broken(self):
        """Broken status returns circle-xmark icon (unprefixed for use with {% icon %} tag)."""
        self.assertEqual(machine_status_icon("broken"), "circle-xmark")

    def test_machine_status_icon_unknown(self):
        """Unknown status returns circle-question icon (unprefixed for use with {% icon %} tag)."""
        self.assertEqual(machine_status_icon("unknown"), "circle-question")

    def test_machine_status_icon_fallback(self):
        """Unrecognized status returns circle-question icon (unprefixed for use with {% icon %} tag)."""
        self.assertEqual(machine_status_icon("invalid"), "circle-question")
        self.assertEqual(machine_status_icon(""), "circle-question")
        self.assertEqual(machine_status_icon(None), "circle-question")

    def test_machine_status_btn_class_good(self):
        """Good status returns btn--status-good."""
        self.assertEqual(machine_status_btn_class("good"), "btn--status-good")

    def test_machine_status_btn_class_fixing(self):
        """Fixing status returns btn--status-fixing."""
        self.assertEqual(machine_status_btn_class("fixing"), "btn--status-fixing")

    def test_machine_status_btn_class_broken(self):
        """Broken status returns btn--status-broken."""
        self.assertEqual(machine_status_btn_class("broken"), "btn--status-broken")

    def test_machine_status_btn_class_unknown(self):
        """Unknown status returns btn--secondary."""
        self.assertEqual(machine_status_btn_class("unknown"), "btn--secondary")

    def test_machine_status_btn_class_fallback(self):
        """Unrecognized status returns btn--secondary."""
        self.assertEqual(machine_status_btn_class("invalid"), "btn--secondary")
        self.assertEqual(machine_status_btn_class(""), "btn--secondary")
        self.assertEqual(machine_status_btn_class(None), "btn--secondary")


@tag("views")
class IconTagTests(TestCase):
    """Tests for the {% icon %} template tag."""

    def test_basic_icon_output(self):
        """Basic icon renders with fa-solid prefix and aria-hidden."""
        result = icon("check")
        self.assertEqual(result, '<i class="fa-solid fa-check" aria-hidden="true"></i>')

    def test_icon_with_extra_class(self):
        """Icon with class parameter includes extra classes."""
        result = icon("check", **{"class": "meta"})
        self.assertEqual(result, '<i class="fa-solid fa-check meta" aria-hidden="true"></i>')

    def test_icon_with_multiple_classes(self):
        """Icon with multiple classes in class parameter."""
        result = icon("check", **{"class": "meta space-right-sm"})
        self.assertEqual(
            result,
            '<i class="fa-solid fa-check meta space-right-sm" aria-hidden="true"></i>',
        )

    def test_icon_with_label(self):
        """Icon with label adds visually-hidden span."""
        result = icon("bug", label="Problem")
        self.assertEqual(
            result,
            '<i class="fa-solid fa-bug" aria-hidden="true"></i>'
            '<span class="visually-hidden">Problem</span>',
        )

    def test_icon_brands_style(self):
        """Icon with style='brands' uses fa-brands prefix."""
        result = icon("discord", style="brands")
        self.assertEqual(result, '<i class="fa-brands fa-discord" aria-hidden="true"></i>')

    def test_icon_regular_style(self):
        """Icon with style='regular' uses fa-regular prefix."""
        result = icon("heart", style="regular")
        self.assertEqual(result, '<i class="fa-regular fa-heart" aria-hidden="true"></i>')

    def test_invalid_style_raises_error(self):
        """Invalid style parameter raises ValueError."""
        with self.assertRaises(ValueError) as context:
            icon("check", style="invalid")
        self.assertIn("Invalid icon style 'invalid'", str(context.exception))
        self.assertIn("brands", str(context.exception))
        self.assertIn("regular", str(context.exception))
        self.assertIn("solid", str(context.exception))

    def test_label_html_is_escaped(self):
        """HTML in label parameter is escaped for XSS protection."""
        result = icon("bug", label="<script>alert('xss')</script>")
        self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result)

    def test_class_ordering(self):
        """Style class comes before icon name, then extra classes."""
        result = icon("check", **{"class": "meta"})
        # Verify class ordering: fa-solid, fa-check, meta
        self.assertIn('class="fa-solid fa-check meta"', result)

    def test_icon_with_label_and_class(self):
        """Icon with both label and class works correctly."""
        result = icon("bug", label="Problem", **{"class": "meta"})
        self.assertIn('class="fa-solid fa-bug meta"', result)
        self.assertIn('<span class="visually-hidden">Problem</span>', result)

    def test_machine_status_icon_no_double_prefix(self):
        """Machine status icons work with {% icon %} tag without double fa- prefix.

        Regression test: machine_status_icon filter returns unprefixed names
        (e.g., "check" not "fa-check") so the icon() tag can add the prefix.
        """
        from the_flip.apps.core.templatetags.core_extras import machine_status_icon

        # Verify filter returns unprefixed names
        self.assertEqual(machine_status_icon("good"), "check")
        self.assertEqual(machine_status_icon("fixing"), "wrench")
        self.assertEqual(machine_status_icon("broken"), "circle-xmark")
        self.assertEqual(machine_status_icon("unknown"), "circle-question")

        # Verify combining with icon() produces correct output (no double prefix)
        result = icon(machine_status_icon("good"))
        self.assertEqual(result, '<i class="fa-solid fa-check" aria-hidden="true"></i>')
        self.assertNotIn("fa-fa-", result)  # No double prefix


@tag("forms")
class StyledFormMixinTests(TestCase):
    """Tests for the StyledFormMixin that auto-applies CSS classes to form widgets."""

    def test_applies_form_input_to_text_input(self):
        """TextInput widget gets form-input class."""

        class TestForm(StyledFormMixin, forms.Form):
            name = forms.CharField()

        form = TestForm()
        self.assertEqual(form.fields["name"].widget.attrs.get("class"), "form-input")

    def test_applies_form_input_to_textarea(self):
        """Textarea widget gets form-input and form-textarea classes."""

        class TestForm(StyledFormMixin, forms.Form):
            notes = forms.CharField(widget=forms.Textarea())

        form = TestForm()
        self.assertEqual(form.fields["notes"].widget.attrs.get("class"), "form-input form-textarea")

    def test_applies_checkbox_class_to_checkbox(self):
        """CheckboxInput widget gets checkbox class."""

        class TestForm(StyledFormMixin, forms.Form):
            agree = forms.BooleanField()

        form = TestForm()
        self.assertEqual(form.fields["agree"].widget.attrs.get("class"), "checkbox")

    def test_preserves_existing_classes(self):
        """Existing widget classes are preserved."""

        class TestForm(StyledFormMixin, forms.Form):
            name = forms.CharField(widget=forms.TextInput(attrs={"class": "custom-class"}))

        form = TestForm()
        classes = form.fields["name"].widget.attrs.get("class", "")
        self.assertIn("custom-class", classes)
        self.assertIn("form-input", classes)

    def test_does_not_duplicate_classes(self):
        """Classes already present are not duplicated."""

        class TestForm(StyledFormMixin, forms.Form):
            name = forms.CharField(widget=forms.TextInput(attrs={"class": "form-input"}))

        form = TestForm()
        classes = form.fields["name"].widget.attrs.get("class", "")
        # Should be exactly one form-input, not duplicated
        self.assertEqual(classes.count("form-input"), 1)

    def test_uses_word_boundary_matching_not_substring(self):
        """CSS class matching uses word boundaries, not substring matching.

        Regression test: A widget with class="form-input--width-8" should still
        get "form-input" added because "form-input--width-8" is not the same
        class as "form-input".
        """

        class TestForm(StyledFormMixin, forms.Form):
            year = forms.IntegerField(
                widget=forms.NumberInput(attrs={"class": "form-input--width-8"})
            )

        form = TestForm()
        classes = form.fields["year"].widget.attrs.get("class", "")
        class_list = classes.split()

        # Should have both classes - the modifier class doesn't satisfy form-input
        self.assertIn("form-input", class_list)
        self.assertIn("form-input--width-8", class_list)

    def test_widget_with_base_and_modifier_class(self):
        """Widget with both base and modifier class doesn't get duplicate base."""

        class TestForm(StyledFormMixin, forms.Form):
            year = forms.IntegerField(
                widget=forms.NumberInput(attrs={"class": "form-input form-input--width-8"})
            )

        form = TestForm()
        classes = form.fields["year"].widget.attrs.get("class", "")
        class_list = classes.split()
        # form-input should appear exactly once (using word-based count, not substring)
        self.assertEqual(class_list.count("form-input"), 1)
        self.assertIn("form-input--width-8", class_list)

    def test_select_widget_gets_form_input_class(self):
        """Select widget gets form-input class."""

        class TestForm(StyledFormMixin, forms.Form):
            choice = forms.ChoiceField(choices=[("a", "A"), ("b", "B")])

        form = TestForm()
        self.assertEqual(form.fields["choice"].widget.attrs.get("class"), "form-input")
