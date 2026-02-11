"""Atomic UI primitives: icon, pill, smart_date, month_name, addstr.

Also provides ``_settable_pill_context``, a shared helper for building
settable dropdown pill context dicts.  App-level tag libraries import it::

    from the_flip.apps.core.templatetags.ui_tags import _settable_pill_context
"""

from django import template
from django.utils import timezone
from django.utils.html import format_html, format_html_join

register = template.Library()

# ---- Icon -------------------------------------------------------------------

# Whitelist of valid Font Awesome styles with their CSS class prefixes
ICON_STYLES = {
    "solid": "fa-solid",
    "brands": "fa-brands",
    "regular": "fa-regular",
}


@register.simple_tag
def icon(name: str, style: str = "solid", label: str | None = None, **kwargs: str) -> str:
    """Render a Font Awesome icon with proper accessibility.

    All icons include aria-hidden="true" by default since they are decorative.
    For icons that convey meaning, use the label parameter to add screen reader text.

    Usage:
        {% icon "check" %}
        {% icon "check" class="meta" %}
        {% icon "bug" label="Problem" %}
        {% icon "discord" style="brands" %}
        {% icon "check" class="meta" data_pill_icon="" %}

    Args:
        name: Icon name without fa- prefix (e.g., "check", "bug")
        style: "solid" (default), "brands", or "regular"
        label: Screen reader text (adds visually-hidden span)
        class: Additional CSS classes (via kwargs to avoid Python keyword)
        **kwargs: Extra kwargs become HTML attributes (underscores -> hyphens).
            E.g., ``data_pill_icon=""`` renders as ``data-pill-icon=""``.

    Returns:
        Safe HTML string with the icon element

    Raises:
        ValueError: If style is not in ICON_STYLES whitelist
    """
    if style not in ICON_STYLES:
        valid = ", ".join(sorted(ICON_STYLES.keys()))
        raise ValueError(f"Invalid icon style '{style}'. Must be one of: {valid}")

    style_class = ICON_STYLES[style]
    extra_class = kwargs.pop("class", "")
    classes = f"{style_class} fa-{name}"
    if extra_class:
        classes = f"{classes} {extra_class}"

    # Render remaining kwargs as HTML attributes (underscores -> hyphens)
    extra_attrs = format_html_join(
        "", ' {}="{}"', ((k.replace("_", "-"), v) for k, v in kwargs.items())
    )

    icon_html = format_html('<i class="{}"{} aria-hidden="true"></i>', classes, extra_attrs)

    if label:
        return format_html(
            '{}<span class="visually-hidden">{}</span>',
            icon_html,
            label,
        )
    return icon_html


# ---- Pill -------------------------------------------------------------------


@register.inclusion_tag("components/pill.html")
def pill(label: str, variant: str = "neutral", icon: str = ""):
    """Render a pill/badge component.

    Usage:
        {% pill label="Open" variant="open" %}
        {% pill label="Closed" variant="closed" %}
        {% pill label="Fixing" variant="status-fixing" icon="wrench" %}

    Args:
        label: Text to display
        variant: Style variant - semantic (open, closed) or CSS class
                 (neutral, status-fixing, status-good, status-broken)
        icon: Optional FontAwesome icon name (without fa- prefix)
    """
    return {
        "label": label,
        "variant": variant,
        "icon": icon,
    }


# ---- Filters ----------------------------------------------------------------


@register.filter
def smart_date(value):
    """Render a datetime as a <time> element for client-side formatting."""
    if not value:
        return ""
    if timezone.is_naive(value):
        value = timezone.make_aware(value)
    iso_format = value.isoformat()
    return format_html(
        '<time datetime="{}" class="smart-date">{}</time>',
        iso_format,
        iso_format,
    )


@register.filter
def addstr(value, arg):
    """Concatenate two values as strings.

    Usage:
        {{ "Problem Report #"|addstr:report.pk }}
    """
    return f"{value}{arg}"


@register.filter
def month_name(month_number):
    """Convert month number (1-12) to month name."""
    if not month_number:
        return ""
    month_names = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    try:
        return month_names[int(month_number) - 1]
    except (ValueError, IndexError):
        return ""


# ---- Settable pill helper ---------------------------------------------------


def _settable_pill_context(
    *,
    field: str,
    action: str,
    current_value: str,
    display_value: str,
    items: list[dict],
    pill_class: str = "pill--neutral",
    icon_name: str | None = None,
    trigger_style: str = "pill",
    btn_class: str = "",
    aria_label: str = "",
    title: str = "",
    title_prefix: str = "",
) -> dict:
    """Build template context for a settable dropdown pill.

    All ``settable_*_pill`` inclusion tags delegate here so the shared
    template (``components/settable_pill.html``) is the single source of
    truth for ARIA roles, keyboard attributes, and dropdown structure.

    Args:
        field: POST field name (e.g. ``"status"``, ``"operational_status"``).
        action: POST action value (e.g. ``"update_status"``).
        current_value: Current field value (for selected/checked state).
        display_value: Display label shown on the pill trigger.
        items: List of dicts, each with ``value``, ``label``, and optionally
            ``pill_class``, ``btn_class``, and ``icon``.
        pill_class: CSS class for the pill trigger (default ``pill--neutral``).
        icon_name: Icon name (without ``fa-`` prefix) for the trigger, or
            ``None`` for no icon.
        trigger_style: ``"pill"`` (default) or ``"button"`` for icon-only
            button rendering used in mobile action bars.
        btn_class: Full CSS class string for button-style triggers
            (e.g. ``"btn btn--dropdown btn--status-good"``).
        aria_label: Accessible label for icon-only button triggers.
        title: Tooltip text for button triggers.
        title_prefix: Prefix for dynamic title updates via JS
            (e.g. ``"Status: "``). Rendered as ``data-title-prefix``.
    """
    for item in items:
        item["selected"] = str(item["value"]) == str(current_value)
    return {
        "field": field,
        "action": action,
        "pill_class": pill_class,
        "icon_name": icon_name,
        "display_value": display_value,
        "items": items,
        "trigger_style": trigger_style,
        "btn_class": btn_class,
        "aria_label": aria_label,
        "title": title,
        "title_prefix": title_prefix,
    }
