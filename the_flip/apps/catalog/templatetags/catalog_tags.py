"""Catalog domain display: machine status pills, status/icon filters, manufacturer_year."""

from django import template

from the_flip.apps.core.templatetags.ui_tags import _settable_pill_context

register = template.Library()

# ---- Machine operational status display mappings ----------------------------

_MACHINE_STATUS_CSS_CLASSES = {
    "good": "pill--status-good",
    "fixing": "pill--status-fixing",
    "broken": "pill--status-broken",
}

_MACHINE_STATUS_ICONS = {
    "good": "check",
    "fixing": "wrench",
    "broken": "circle-xmark",
}

_MACHINE_STATUS_BTN_CLASSES = {
    "good": "btn--status-good",
    "fixing": "btn--status-fixing",
    "broken": "btn--status-broken",
}


@register.filter
def machine_status_css_class(status):
    """Return pill CSS class for MachineInstance.operational_status.

    Usage:
        {{ machine.operational_status|machine_status_css_class }}
    """
    return _MACHINE_STATUS_CSS_CLASSES.get(status, "pill--neutral")


@register.filter
def machine_status_icon(status):
    """Return Font Awesome icon class for MachineInstance.operational_status.

    Usage:
        {{ machine.operational_status|machine_status_icon }}
    """
    return _MACHINE_STATUS_ICONS.get(status, "circle-question")


@register.filter
def machine_status_btn_class(status):
    """Return button CSS class for MachineInstance.operational_status.

    Usage:
        {{ machine.operational_status|machine_status_btn_class }}
    """
    return _MACHINE_STATUS_BTN_CLASSES.get(status, "btn--secondary")


@register.filter
def manufacturer_year(model):
    """Return 'Manufacturer . Year' string for a machine model.

    Handles cases where manufacturer or year may be missing.

    Usage:
        {{ machine.model|manufacturer_year }}
        {{ machine_model|manufacturer_year }}
    """
    parts = []
    if model.manufacturer:
        parts.append(model.manufacturer)
    if model.year:
        parts.append(str(model.year))
    return " \u00b7 ".join(parts)


# ---- Settable pills ---------------------------------------------------------


@register.inclusion_tag("components/settable_pill.html")
def settable_machine_status_pill(machine, trigger_style="pill"):
    """Render a settable operational-status dropdown for a machine.

    Usage::

        {% settable_machine_status_pill machine %}
        {% settable_machine_status_pill machine trigger_style="button" %}

    With ``trigger_style="button"`` renders an icon-only button suitable
    for mobile action bars instead of the default pill with label text.
    """
    items = [
        {
            "value": v,
            "label": label,
            "pill_class": machine_status_css_class(v),
            "icon": machine_status_icon(v),
            "btn_class": machine_status_btn_class(v),
        }
        for v, label in type(machine).OperationalStatus.choices
    ]
    btn_cls = ""
    aria_label = ""
    title = ""
    title_prefix = ""
    if trigger_style == "button":
        btn_cls = f"btn btn--dropdown {machine_status_btn_class(machine.operational_status)}"
        aria_label = "Change status"
        title_prefix = "Status: "
        title = f"{title_prefix}{machine.get_operational_status_display()}"
    return _settable_pill_context(
        field="operational_status",
        action="update_status",
        current_value=machine.operational_status,
        display_value=machine.get_operational_status_display(),
        pill_class=machine_status_css_class(machine.operational_status),
        icon_name=machine_status_icon(machine.operational_status),
        items=items,
        trigger_style=trigger_style,
        btn_class=btn_cls,
        aria_label=aria_label,
        title=title,
        title_prefix=title_prefix,
    )


@register.inclusion_tag("components/settable_pill.html")
def settable_machine_location_pill(machine, locations, trigger_style="pill"):
    """Render a settable location dropdown for a machine.

    Usage::

        {% settable_machine_location_pill machine locations %}
        {% settable_machine_location_pill machine locations trigger_style="button" %}

    With ``trigger_style="button"`` renders an icon-only button suitable
    for mobile action bars instead of the default pill with label text.
    """
    current = machine.location.slug if machine.location else ""
    display = machine.location.name if machine.location else "No Location"
    items = [{"value": loc.slug, "label": loc.name} for loc in locations]
    items.append({"value": "", "label": "No Location"})
    btn_cls = ""
    aria_label = ""
    title = ""
    title_prefix = ""
    if trigger_style == "button":
        btn_cls = "btn btn--dropdown btn--secondary"
        aria_label = "Change location"
        title_prefix = "Location: "
        title = f"{title_prefix}{display}"
    return _settable_pill_context(
        field="location",
        action="update_location",
        current_value=current,
        display_value=display,
        icon_name="location-dot",
        items=items,
        trigger_style=trigger_style,
        btn_class=btn_cls,
        aria_label=aria_label,
        title=title,
        title_prefix=title_prefix,
    )
