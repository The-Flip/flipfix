"""Wiki domain form components: template_selector_field, tag_chip_input_field."""

from django import template

register = template.Library()


@register.inclusion_tag("components/template_selector.html", takes_context=True)
def template_selector_field(
    context,
    record_type: str,
    machine_slug: str = "",
    location_slug: str = "",
):
    """Render a template selector dropdown for create forms.

    Hidden by JS when no templates match. Fetches options from the wiki
    template list API (URL resolved in the component template).

    Reads ``prefill_template_url`` from the parent context (set by
    ``FormPrefillMixin``) to pre-select a template on button-click flows.

    Usage:
        {% template_selector_field record_type="problem" machine_slug=machine.slug location_slug=machine.location.slug %}
        {% template_selector_field record_type="page" %}

    Args:
        record_type: "problem", "log", "partrequest", or "page"
        machine_slug: Current machine slug (optional, blank = any)
        location_slug: Current location slug (optional, blank = any)
    """
    return {
        "record_type": record_type,
        "machine_slug": machine_slug,
        "location_slug": location_slug,
        "preselect_url": context.get("prefill_template_url", ""),
    }


@register.inclusion_tag("components/tag_chip_input_field.html")
def tag_chip_input_field(
    label: str = "Tags",
    placeholder: str = "Add tag...",
    help_text: str = "",
    show_label: bool = True,
    required: bool = False,
    initial_tags: str = "",
    errors: list | None = None,
):
    """Render a chip-based tag input for wiki pages.

    Usage:
        {% tag_chip_input_field %}
        {% tag_chip_input_field label="Categories" %}
        {% tag_chip_input_field initial_tags="machines, guides" %}

    Args:
        label: Label text (default "Tags")
        placeholder: Input placeholder text
        help_text: Help text shown below input
        show_label: Whether to show the label (default True)
        required: Whether the field is required (affects label display)
        initial_tags: Comma-separated string of tags to pre-populate
        errors: List of error messages to display below the input
    """
    # Split tags into list for hidden input fallback
    tags_list = []
    if initial_tags:
        tags_list = [tag.strip() for tag in initial_tags.split(",") if tag.strip()]

    return {
        "label": label,
        "placeholder": placeholder,
        "help_text": help_text,
        "show_label": show_label,
        "required": required,
        "initial_tags": initial_tags,
        "initial_tags_list": tags_list,
        "errors": errors or [],
    }
