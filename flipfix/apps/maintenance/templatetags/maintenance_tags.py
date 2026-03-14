"""Maintenance domain display: problem/log pills, status/priority filters, meta formatters."""

from decimal import Decimal

from django import template
from django.urls import reverse
from django.utils.html import format_html

from flipfix.apps.core.mixins import can_access_maintainer_portal
from flipfix.apps.core.templatetags.ui_tags import _settable_pill_context, smart_date

register = template.Library()


def _format_hours(value: Decimal | None) -> str:
    """Format a Decimal hours value to at most 2 decimal places, stripping trailing zeros."""
    if not value:
        return "0"
    # Quantize to 2 decimal places, then normalize to strip trailing zeros
    return f"{float(value):.2f}".rstrip("0").rstrip(".")


# ---- Problem report priority mappings ---------------------------------------

_PRIORITY_CSS_CLASSES = {
    "untriaged": "pill--priority-untriaged",
    "unplayable": "pill--priority-unplayable",
    "major": "pill--priority-major",
}

_PRIORITY_ICONS = {
    "untriaged": "triangle-exclamation",
    "unplayable": "circle-xmark",
    "major": "arrow-up",
    "minor": "arrow-down",
    "task": "list-check",
}


@register.filter
def problem_priority_css_class(priority):
    """Return pill CSS class for ProblemReport.priority.

    Usage:
        {{ report.priority|problem_priority_css_class }}
    """
    return _PRIORITY_CSS_CLASSES.get(priority, "pill--neutral")


@register.filter
def problem_priority_icon(priority):
    """Return Font Awesome icon name for ProblemReport.priority.

    Usage:
        {{ report.priority|problem_priority_icon }}
    """
    return _PRIORITY_ICONS.get(priority, "minus")


# ---- Problem report status mappings -----------------------------------------

_STATUS_CSS_CLASSES = {
    "open": "pill--status-broken",
    "closed": "pill--status-good",
}

_STATUS_ICONS = {
    "open": "circle-exclamation",
    "closed": "check",
}


@register.filter
def problem_status_css_class(status):
    """Return pill CSS class for ProblemReport.status.

    Usage:
        {{ report.status|problem_status_css_class }}
    """
    return _STATUS_CSS_CLASSES.get(status, "pill--status-broken")


@register.filter
def problem_status_icon(status):
    """Return Font Awesome icon name for ProblemReport.status.

    Usage:
        {{ report.status|problem_status_icon }}
    """
    return _STATUS_ICONS.get(status, "circle-exclamation")


# ---- Inclusion tags for read-only pills ------------------------------------


@register.inclusion_tag("components/problem_report_status_pill.html")
def problem_report_status_pill(report):
    """Render a status pill (Open/Closed) for a problem report.

    Usage:
        {% problem_report_status_pill report %}
    """
    return {"report": report}


@register.inclusion_tag("components/problem_report_type_pill.html")
def problem_report_type_pill(report):
    """Render a problem type pill for a problem report (hidden if type is Other).

    Usage:
        {% problem_report_type_pill report %}
    """
    return {"report": report}


@register.inclusion_tag("components/problem_report_priority_pill.html")
def problem_report_priority_pill(report):
    """Render a priority pill for a problem report.

    Usage:
        {% problem_report_priority_pill report %}
    """
    return {"report": report}


# ---- Meta / summary filters ------------------------------------------------


@register.filter
def problem_report_summary(report):
    """Build a concise problem report summary.

    - If type is "Other" and description exists: just the description.
    - If type is "Other" and no description: "No description provided".
    - If type is not "Other" and description exists: "<Type>: <description>".
    - If type is not "Other" and no description: "<Type>".
    """
    if not report:
        return ""

    description = (getattr(report, "description", "") or "").strip()
    problem_type_class = getattr(report, "ProblemType", None)
    is_other = (
        problem_type_class and getattr(report, "problem_type", None) == problem_type_class.OTHER
    )
    type_display = getattr(report, "get_problem_type_display", lambda: "")()

    if is_other:
        return description or "No description provided."

    if description:
        return f"{type_display}: {description}"
    return type_display


@register.simple_tag(takes_context=True)
def problem_report_meta(context, report):
    """Render reporter name (if present) followed by timestamp (emphasized).

    Example: "Alice \u00b7 <strong><time ...>...</time></strong>"
    If no reporter, or if the user is unauthenticated, only render the timestamp.
    """
    if not report:
        return ""

    ts = smart_date(getattr(report, "occurred_at", None))

    if not context["user"].is_authenticated:
        return format_html("<strong>{}</strong>", ts)

    name = (getattr(report, "reporter_display", "") or "").strip()

    if name:
        return format_html("{} \u00b7 <strong>{}</strong>", name, ts)
    return format_html("<strong>{}</strong>", ts)


@register.simple_tag(takes_context=True)
def log_entry_meta(context, entry):
    """Render maintainer name(s) (if present) followed by timestamp (emphasized).

    Example: "Alice \u00b7 <strong><time ...>...</time></strong>"
    If no maintainer name, or if the user is unauthenticated, only render the timestamp.
    """
    if not entry:
        return ""

    ts = smart_date(getattr(entry, "occurred_at", None))

    time_spent = getattr(entry, "time_spent", None)
    hours = format_html("{}h", _format_hours(time_spent)) if time_spent else ""

    if not context["user"].is_authenticated:
        if hours:
            return format_html("{} \u00b7 <strong>{}</strong>", hours, ts)
        return format_html("<strong>{}</strong>", ts)

    names = ""
    maintainers = list(entry.maintainers.all()) if hasattr(entry, "maintainers") else []
    if maintainers:
        names = ", ".join(str(m) for m in maintainers)
    elif getattr(entry, "maintainer_names", ""):
        names = entry.maintainer_names

    names = (names or "").strip()
    if names and hours:
        return format_html("{} \u00b7 {} \u00b7 <strong>{}</strong>", names, hours, ts)
    if names:
        return format_html("{} \u00b7 <strong>{}</strong>", names, ts)
    if hours:
        return format_html("{} \u00b7 <strong>{}</strong>", hours, ts)
    return format_html("<strong>{}</strong>", ts)


# ---- Settable pills ---------------------------------------------------------


@register.inclusion_tag("components/settable_pill.html", takes_context=True)
def settable_problem_status_pill(context, report):
    """Render a settable status dropdown pill for a problem report.

    Usage:
        {% settable_problem_status_pill report %}
    """
    ctx = _settable_pill_context(
        field="status",
        action="update_status",
        current_value=report.status,
        display_value=report.get_status_display(),
        pill_class=problem_status_css_class(report.status),
        icon_name=problem_status_icon(report.status),
        items=[
            {
                "value": v,
                "label": label,
                "pill_class": problem_status_css_class(v),
                "icon": problem_status_icon(v),
            }
            for v, label in type(report).Status.choices
        ],
    )
    ctx["user"] = context["user"]
    return ctx


@register.inclusion_tag("components/settable_pill.html", takes_context=True)
def settable_problem_priority_pill(context, report):
    """Render a settable priority dropdown pill for a problem report.

    Excludes UNTRIAGED from the choices -- maintainers cannot set it.

    Usage:
        {% settable_problem_priority_pill report %}
    """
    ctx = _settable_pill_context(
        field="priority",
        action="update_priority",
        current_value=report.priority,
        display_value=report.get_priority_display(),
        pill_class=problem_priority_css_class(report.priority),
        icon_name=problem_priority_icon(report.priority),
        items=[
            {
                "value": v,
                "label": label,
                "pill_class": problem_priority_css_class(v),
                "icon": problem_priority_icon(v),
            }
            for v, label in type(report).Priority.maintainer_settable()
        ],
    )
    ctx["user"] = context["user"]
    return ctx


# ---- Report problem button --------------------------------------------------


@register.inclusion_tag("components/report_problem_button.html", takes_context=True)
def report_problem_button(context, machine, btn_class="btn btn--report", label="Report Problem"):
    """Render a Report Problem button with guest-aware URL.

    Guests get the public QR-style form; maintainers get the full form.

    Usage::

        {% report_problem_button machine %}
        {% report_problem_button machine btn_class="btn btn--report btn--full" %}
        {% report_problem_button machine label="Report" %}
    """
    if can_access_maintainer_portal(context["user"]):
        url = reverse("problem-report-create-machine", kwargs={"slug": machine.slug})
    else:
        url = reverse("public-problem-report-create", kwargs={"slug": machine.slug})
    return {"url": url, "btn_class": btn_class, "label": label}
