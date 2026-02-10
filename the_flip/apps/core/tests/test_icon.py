"""Tests for the {% icon %} template tag."""

from django.test import TestCase, tag

from the_flip.apps.core.templatetags.ui_tags import icon


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

    def test_data_attribute(self):
        """Extra kwargs render as HTML attributes (underscores become hyphens)."""
        result = icon("check", **{"class": "meta", "data_pill_icon": ""})
        self.assertEqual(
            result,
            '<i class="fa-solid fa-check meta" data-pill-icon="" aria-hidden="true"></i>',
        )

    def test_machine_status_icon_no_double_prefix(self):
        """Machine status icons work with {% icon %} tag without double fa- prefix.

        Regression test: machine_status_icon filter returns unprefixed names
        (e.g., "check" not "fa-check") so the icon() tag can add the prefix.
        """
        from the_flip.apps.catalog.templatetags.catalog_tags import machine_status_icon

        # Verify filter returns unprefixed names
        self.assertEqual(machine_status_icon("good"), "check")
        self.assertEqual(machine_status_icon("fixing"), "wrench")
        self.assertEqual(machine_status_icon("broken"), "circle-xmark")
        self.assertEqual(machine_status_icon("unknown"), "circle-question")

        # Verify combining with icon() produces correct output (no double prefix)
        result = icon(machine_status_icon("good"))
        self.assertEqual(result, '<i class="fa-solid fa-check" aria-hidden="true"></i>')
        self.assertNotIn("fa-fa-", result)  # No double prefix
