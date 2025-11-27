import markdown
import nh3
from django import template
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

# Allowed HTML tags for markdown rendering
ALLOWED_TAGS = {
    "p",
    "br",
    "strong",
    "em",
    "ul",
    "ol",
    "li",
    "code",
    "pre",
    "blockquote",
    "a",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
}

# Allowed attributes per tag
ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
}


@register.filter
def render_markdown(text):
    """Convert markdown text to sanitized HTML."""
    if not text:
        return ""
    # Convert markdown to HTML
    html = markdown.markdown(text, extensions=["fenced_code", "nl2br"])
    # Sanitize to prevent XSS
    safe_html = nh3.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES)
    return mark_safe(safe_html)  # noqa: S308 - HTML sanitized by nh3


@register.filter
def smart_date(value):
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
def getfield(form, field_name):
    """Get a field from a form by name."""
    return form[field_name]


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


@register.filter
def problem_report_summary(report):
    """
    Build a concise problem report summary:
    - If type is "Other" and description exists: just the description.
    - If type is "Other" and no description: "No description provided".
    - If type is not "Other" and description exists: "<Type>: <description>".
    - If type is not "Other" and no description: "<Type>".
    """
    if not report:
        return ""

    description = (getattr(report, "description", "") or "").strip()
    is_other = getattr(report, "problem_type", None) == getattr(report, "PROBLEM_OTHER", None)
    type_display = getattr(report, "get_problem_type_display", lambda: "")()

    if is_other:
        return description or "No description provided."

    if description:
        return f"{type_display}: {description}"
    return type_display


@register.filter
def problem_report_meta(report):
    """
    Render reporter name (if present) followed by timestamp (emphasized).
    Example: "Alice on <strong><time ...>…</time></strong>"
    If no reporter, only render the timestamp emphasized.
    """
    if not report:
        return ""

    ts = smart_date(getattr(report, "created_at", None))
    name = (getattr(report, "reporter_display", "") or "").strip()

    if name:
        return format_html("{} on <strong>{}</strong>", name, ts)
    return format_html("<strong>{}</strong>", ts)


@register.filter
def log_entry_meta(entry):
    """
    Render maintainer name(s) (if present) followed by timestamp (emphasized).
    Example: "Alice on <strong><time ...>…</time></strong>"
    If no maintainer name, only render the timestamp emphasized.
    """
    if not entry:
        return ""

    ts = smart_date(getattr(entry, "work_date", None))
    names = ""
    try:
        if hasattr(entry, "maintainers") and entry.maintainers.exists():
            names = ", ".join(str(m) for m in entry.maintainers.all())
        elif getattr(entry, "maintainer_names", ""):
            names = entry.maintainer_names
    except Exception:
        names = getattr(entry, "maintainer_names", "") or ""

    names = (names or "").strip()
    if names:
        return format_html("{} on <strong>{}</strong>", names, ts)
    return format_html("<strong>{}</strong>", ts)
