"""Core form utilities and mixins."""

from django import forms

# Widget type to CSS class mapping
WIDGET_CSS_CLASSES = {
    forms.TextInput: "form-input",
    forms.EmailInput: "form-input",
    forms.PasswordInput: "form-input",
    forms.NumberInput: "form-input",
    forms.URLInput: "form-input",
    forms.DateInput: "form-input",
    forms.DateTimeInput: "form-input",
    forms.TimeInput: "form-input",
    forms.Textarea: "form-input form-textarea",
    forms.Select: "form-input",
    forms.SelectMultiple: "form-input",
    forms.CheckboxInput: "checkbox",
    # File inputs and RadioSelect are handled separately in templates
}


class StyledFormMixin:
    """
    Mixin that adds CSS classes to form widgets automatically.

    Apply to form classes to enable use of {{ field }} in templates
    while maintaining consistent styling.

    Usage:
        class MyForm(StyledFormMixin, forms.Form):
            name = forms.CharField()

    The mixin preserves any existing widget attrs and only adds
    the CSS class if not already present.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_widget_classes()

    def _apply_widget_classes(self):
        """Apply CSS classes to all field widgets based on widget type."""
        for field in self.fields.values():
            widget = field.widget
            for widget_type, css_class in WIDGET_CSS_CLASSES.items():
                if isinstance(widget, widget_type):
                    existing = widget.attrs.get("class", "")
                    if css_class not in existing:
                        widget.attrs["class"] = f"{existing} {css_class}".strip()
                    break
