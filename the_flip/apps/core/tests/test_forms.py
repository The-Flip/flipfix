"""Tests for form utilities."""

from django import forms
from django.test import TestCase, tag

from the_flip.apps.core.forms import MarkdownTextarea, StyledFormMixin


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


@tag("forms")
class MarkdownTextareaTests(TestCase):
    """Tests for the MarkdownTextarea widget."""

    def test_default_attrs_present(self):
        """Widget includes all markdown editing data attributes."""
        widget = MarkdownTextarea()
        self.assertEqual(widget.attrs["data-text-textarea"], "")
        self.assertEqual(widget.attrs["data-link-autocomplete"], "")
        self.assertEqual(widget.attrs["data-task-list-enter"], "")
        # reverse_lazy returns a lazy string; str() to compare
        self.assertEqual(str(widget.attrs["data-link-api-url"]), "/api/link-targets/")

    def test_custom_attrs_merge(self):
        """Custom attrs merge with defaults (custom wins on conflict)."""
        widget = MarkdownTextarea(attrs={"rows": 20, "placeholder": "Write..."})
        self.assertEqual(widget.attrs["rows"], 20)
        self.assertEqual(widget.attrs["placeholder"], "Write...")
        # Defaults still present
        self.assertEqual(widget.attrs["data-text-textarea"], "")

    def test_custom_attrs_override_defaults(self):
        """Custom attrs can override default values."""
        widget = MarkdownTextarea(attrs={"data-link-api-url": "/custom/"})
        self.assertEqual(widget.attrs["data-link-api-url"], "/custom/")

    def test_styled_form_mixin_adds_css_classes(self):
        """StyledFormMixin adds textarea CSS classes to MarkdownTextarea."""

        class TestForm(StyledFormMixin, forms.Form):
            content = forms.CharField(widget=MarkdownTextarea())

        form = TestForm()
        classes = form.fields["content"].widget.attrs.get("class", "")
        self.assertIn("form-input", classes)
        self.assertIn("form-textarea", classes)
