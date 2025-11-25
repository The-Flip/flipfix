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
