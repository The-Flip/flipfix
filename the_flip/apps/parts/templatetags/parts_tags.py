"""Parts domain display: settable_part_request_status_pill."""

from django import template

from the_flip.apps.core.templatetags.ui_tags import _settable_pill_context

register = template.Library()


@register.inclusion_tag("components/settable_pill.html")
def settable_part_request_status_pill(part_request):
    """Render a settable status dropdown pill for a part request.

    Usage:
        {% settable_part_request_status_pill part_request %}
    """
    return _settable_pill_context(
        field="status",
        action="update_status",
        current_value=part_request.status,
        display_value=part_request.get_status_display(),
        items=[{"value": v, "label": label} for v, label in type(part_request).Status.choices],
    )
