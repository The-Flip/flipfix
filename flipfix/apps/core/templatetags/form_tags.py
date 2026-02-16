"""Generic form infrastructure: form_field, form_fields, form_label, error/help text."""

from django import template
from django.utils.html import format_html

register = template.Library()


@register.filter
def getfield(form, field_name):
    """Get a field from a form by name."""
    return form[field_name]


@register.simple_tag
def form_label(field):
    """Render a form field label, appending "(optional)" for non-required fields.

    Usage:
        {% form_label field %}

    Args:
        field: A Django form field (BoundField)
    """
    if field.field.required:
        return format_html(
            '<label for="{}" class="form-label">{}</label>',
            field.id_for_label,
            field.label,
        )
    return format_html(
        '<label for="{}" class="form-label">{} <span class="text-muted text-xs">(optional)</span></label>',
        field.id_for_label,
        field.label,
    )


@register.inclusion_tag("components/form_field.html")
def form_field(field, id: str = "", class_: str = ""):
    """Render a form field with label, input, help text, and errors.

    Usage:
        {% form_field form.username %}
        {% form_field form.model_name id="field-model-name" class_="hidden" %}

    Args:
        field: A Django form field (BoundField)
        id: Optional HTML id attribute for the wrapper div
        class_: Optional additional CSS classes for the wrapper div
    """
    return {"field": field, "id": id, "class_": class_}


@register.inclusion_tag("components/form_fields.html")
def form_fields(form):
    """Render all visible fields in a form.

    Usage:
        {% form_fields form %}

    Args:
        form: A Django form instance
    """
    return {"form": form}


@register.inclusion_tag("components/form_non_field_errors.html")
def form_non_field_errors(form):
    """Render non-field errors for a form.

    Only outputs content if there are non-field errors. Renders each error
    in a paragraph with consistent styling.

    Usage:
        {% form_non_field_errors form %}

    Args:
        form: A Django form instance
    """
    return {"form": form}


@register.inclusion_tag("components/field_errors.html")
def field_errors(field):
    """Render errors for a single form field.

    Only outputs content if there are errors. Renders each error
    in a paragraph with consistent styling.

    Usage:
        {% field_errors form.username %}
        {% field_errors field %}

    Args:
        field: A Django form field (BoundField)
    """
    return {"field": field}


@register.inclusion_tag("components/field_help_text.html")
def field_help_text(field):
    """Render help text for a form field if present.

    Only outputs content if the field has help_text defined.

    Usage:
        {% field_help_text form.username %}
        {% field_help_text field %}

    Args:
        field: A Django form field (BoundField)
    """
    return {"field": field}


@register.inclusion_tag("components/media_file_input.html")
def media_file_input(field):
    """Render the media file upload widget with preview row.

    Renders a hidden file input, a paperclip trigger link, field errors,
    and a preview row for selected files.  Uses the project-wide
    ``MEDIA_ACCEPT_ATTR`` for the accept attribute.

    Usage:
        {% media_file_input form.media_file %}

    Args:
        field: A Django form file field (BoundField)
    """
    return {"field": field}
