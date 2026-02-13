"""Sidebar component tags: sidebar_section, editable_sidebar_card."""

from django import template
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from the_flip.apps.core.templatetags.ui_tags import icon as icon_tag

register = template.Library()


@register.simple_block_tag
def sidebar_section(content, label=""):
    """Wrap content in a sidebar section with optional label.

    Usage:
        {% sidebar_section label="Machine" %}
          <div class="sidebar__title">Ballyhoo</div>
        {% endsidebar_section %}
    """
    label_html = ""
    if label:
        label_html = f'<div class="sidebar__label">{label}</div>\n'
    return format_html(
        '<div class="sidebar__section">\n{}{}</div>',
        mark_safe(label_html),  # noqa: S308 - label is from template, not user input
        content,
    )


@register.simple_block_tag
def editable_sidebar_card(
    content,
    editable=False,
    edit_type="machine",
    current_value="",
    current_machine_slug="",
    csrf_token="",
    label="",
    placeholder="",
):
    """Wrap a sidebar card with optional edit functionality.

    When editable=True, wraps the card in an edit wrapper with a hover-reveal
    edit button and dropdown for changing the value.

    Usage:
        {% editable_sidebar_card editable=True edit_type="machine" current_value=machine.slug csrf_token=csrf_token %}
          <a href="..." class="sidebar-card">...</a>
        {% endeditable_sidebar_card %}

        {% editable_sidebar_card editable=True edit_type="problem" current_value=report.pk current_machine_slug=machine.slug csrf_token=csrf_token label="Link to problem" %}
          <div class="sidebar-card">...</div>
        {% endeditable_sidebar_card %}

    Args:
        content: The card content (captured between tags)
        editable: Whether to show edit controls
        edit_type: "machine" or "problem" (determines data attributes and API URL)
        current_value: Current value (slug for machine, id for problem)
        current_machine_slug: Current machine slug (only for problem type)
        csrf_token: CSRF token for form submission
        label: Aria label/title for edit button (defaults based on edit_type)
        placeholder: Search input placeholder (defaults based on edit_type)
    """
    if not editable:
        return content

    # Set defaults based on edit type
    if edit_type == "machine":
        data_attr = "data-sidebar-machine-edit"
        api_url = reverse("api-machine-autocomplete")
        value_attrs = f'data-current-slug="{current_value}"'
        label = label or "Change machine"
        placeholder = placeholder or "Search machines..."
    else:  # problem
        current_id = current_value if current_value else "null"
        data_attr = "data-sidebar-problem-edit"
        api_url = reverse("api-problem-report-autocomplete")
        value_attrs = (
            f'data-current-id="{current_id}" data-current-machine-slug="{current_machine_slug}"'
        )
        # Use different default label based on whether linked to a problem report
        if not label:
            label = "Change problem report" if current_value else "Link to problem report"
        placeholder = placeholder or "Search problem reports..."

    pencil_icon = icon_tag("pencil")
    xmark_icon = icon_tag("xmark")

    return format_html(
        '<div class="sidebar-card-wrapper" {data_attr} data-api-url="{api_url}" {value_attrs} data-csrf-token="{csrf_token}">\n'
        '  <button type="button" class="sidebar-card__edit" data-edit-btn aria-label="{label}" title="{label}">\n'
        "    {pencil_icon}\n"
        "  </button>\n"
        "  {content}\n"
        '  <div class="sidebar-card-edit-dropdown hidden" data-dropdown>\n'
        '    <div class="sidebar-card-edit-dropdown__header">\n'
        '      <span class="sidebar-card-edit-dropdown__title">{label}</span>\n'
        '      <button type="button" class="sidebar-card-edit-dropdown__close" data-edit-btn aria-label="Close">\n'
        "        {xmark_icon}\n"
        "      </button>\n"
        "    </div>\n"
        '    <div class="sidebar-card-edit-dropdown__search">\n'
        '      <input type="text" class="form-input form-input--sm" placeholder="{placeholder}" autocomplete="off" data-search>\n'
        "    </div>\n"
        "    <div data-list></div>\n"
        "  </div>\n"
        "</div>",
        data_attr=mark_safe(data_attr),  # noqa: S308 - hardcoded value
        api_url=api_url,
        value_attrs=mark_safe(value_attrs),  # noqa: S308 - built from template values
        csrf_token=csrf_token,
        label=label,
        content=content,
        placeholder=placeholder,
        pencil_icon=pencil_icon,
        xmark_icon=xmark_icon,
    )
