"""Accounts domain form components: maintainer_autocomplete_field, maintainer_chip_input_field."""

import secrets

from django import template

register = template.Library()


@register.inclusion_tag("components/maintainer_autocomplete_field.html", takes_context=True)
def maintainer_autocomplete_field(
    context,
    field,
    label: str = "",
    placeholder: str = "Search users...",
    size: str = "",
    show_label: bool = True,
    required: bool = False,
    form_id: str = "",
):
    """Render a maintainer autocomplete field with dropdown.

    Usage:
        {% maintainer_autocomplete_field form.requester_name %}
        {% maintainer_autocomplete_field form.requester_name label="Who" size="sm" %}
        {% maintainer_autocomplete_field form.submitter_name show_label=False %}
        {% maintainer_autocomplete_field form.submitter_name required=True %}
        {% maintainer_autocomplete_field form.requester_name form_id="my-form" %}

    Args:
        context: Template context (auto-passed with takes_context=True)
        field: A Django form field (BoundField)
        label: Custom label text (defaults to field.label)
        placeholder: Input placeholder text
        size: Size variant - "" (default) or "sm" for smaller sidebar inputs
        show_label: Whether to show the label (default True)
        required: Whether the field is required (adds HTML required attribute and asterisk)
        form_id: Associate inputs with a form by ID (for inputs outside the form element)
    """
    input_class = "form-input form-input--sm" if size == "sm" else "form-input"

    # Get the hidden username value from POST data (preserves value on form re-render)
    username_value = ""
    request = context.get("request")
    if request and request.method == "POST":
        username_field_name = f"{field.html_name}_username"
        username_value = request.POST.get(username_field_name, "")

    return {
        "field": field,
        "label": label or (field.label if hasattr(field, "label") else ""),
        "placeholder": placeholder,
        "input_class": input_class,
        "show_label": show_label,
        "required": required,
        "username_value": username_value,
        "form_id": form_id,
    }


@register.inclusion_tag("components/maintainer_chip_input_field.html")
def maintainer_chip_input_field(
    label: str = "Who did the work?",
    placeholder: str = "Search users...",
    show_label: bool = True,
    form_id: str = "",
    initial_maintainers: list | None = None,
    initial_freetext: str = "",
    errors: list | None = None,
):
    """Render a chip-based maintainer input for multi-select.

    Used for log entries which have a M2M relationship to maintainers.

    Usage:
        {% maintainer_chip_input_field %}
        {% maintainer_chip_input_field label="Maintainers" %}
        {% maintainer_chip_input_field initial_maintainers=entry.maintainers.all %}
        {% maintainer_chip_input_field initial_freetext=entry.maintainer_names %}
        {% maintainer_chip_input_field errors=maintainer_errors %}

    Args:
        label: Label text (default "Who did the work?")
        placeholder: Input placeholder text
        show_label: Whether to show the label (default True)
        form_id: Associate inputs with a form by ID (for inputs outside the form element)
        initial_maintainers: Queryset or list of Maintainer objects to pre-populate
        initial_freetext: Comma-separated string of freetext names to pre-populate
        errors: List of error messages to display below the input
    """
    # Generate unique ID for the JSON script tag
    script_id = f"maintainer-data-{secrets.token_hex(4)}"

    # Serialize maintainers to list for the template to render via json_script filter
    maintainer_data = None
    if initial_maintainers:
        maintainer_data = [
            {"username": m.user.username, "display_name": m.display_name}
            for m in initial_maintainers
        ]

    # Split freetext into list for hidden input fallback
    freetext_list = []
    if initial_freetext:
        freetext_list = [name.strip() for name in initial_freetext.split(",") if name.strip()]

    return {
        "label": label,
        "placeholder": placeholder,
        "show_label": show_label,
        "form_id": form_id,
        "initial_maintainers_id": script_id if initial_maintainers else "",
        "initial_freetext": initial_freetext,
        "initial_freetext_list": freetext_list,
        "initial_maintainers_data": maintainer_data,
        "errors": errors or [],
    }
