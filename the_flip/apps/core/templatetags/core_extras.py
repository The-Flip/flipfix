import markdown
import nh3
from django import template
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from linkify_it import LinkifyIt

register = template.Library()

# Linkifier instance for URL detection (handles URLs, emails, www links)
_linkify = LinkifyIt()

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
    "img",
    "hr",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "figure",
    "figcaption",
}

# Allowed attributes per tag
ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title"},
    "code": {"class"},
    "pre": {"class"},
    "th": {"align"},
    "td": {"align"},
}


def _linkify_urls(html: str) -> str:
    """Convert bare URLs to anchor tags using linkify-it-py.

    Handles URLs, www links, and email addresses. Properly handles edge cases
    like parentheses in URLs (e.g., Wikipedia links) and avoids double-linking
    URLs already in anchor tags.
    """
    matches = _linkify.match(html)
    if not matches:
        return html

    # Process matches in reverse order to preserve string indices
    result = html
    for match in reversed(matches):
        start = match.index
        end = match.last_index

        # Skip if this URL is already inside an href attribute
        prefix = html[:start]
        if prefix.endswith('href="') or prefix.endswith("href='"):
            continue

        # Replace with anchor tag
        anchor = f'<a href="{match.url}">{match.text}</a>'
        result = result[:start] + anchor + result[end:]

    return result


@register.filter
def render_markdown(text):
    """Convert markdown text to sanitized HTML."""
    if not text:
        return ""
    # Convert markdown to HTML
    html = markdown.markdown(text, extensions=["fenced_code", "nl2br"])
    # Convert bare URLs to links
    html = _linkify_urls(html)
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
    Example: "Alice · <strong><time ...>…</time></strong>"
    If no reporter, only render the timestamp emphasized.
    """
    if not report:
        return ""

    ts = smart_date(getattr(report, "created_at", None))
    name = (getattr(report, "reporter_display", "") or "").strip()

    if name:
        return format_html("{} · <strong>{}</strong>", name, ts)
    return format_html("<strong>{}</strong>", ts)


@register.filter
def log_entry_meta(entry):
    """
    Render maintainer name(s) (if present) followed by timestamp (emphasized).
    Example: "Alice · <strong><time ...>…</time></strong>"
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
        return format_html("{} · <strong>{}</strong>", names, ts)
    return format_html("<strong>{}</strong>", ts)


# -----------------------------------------------------------------------------
# UI Component template tags
# -----------------------------------------------------------------------------


@register.inclusion_tag("components/button.html")
def button(
    url: str,
    label: str,
    icon: str = "",
    variant: str = "secondary",
    full_width: bool = False,
    icon_only: bool = False,
):
    """Render a button/link component.

    Usage:
        {% button url="/logs/new/" label="New Log" icon="plus" variant="log" %}
        {% button url="/edit/" label="Edit" icon="pencil" icon_only=True %}

    Args:
        url: Link href
        icon: FontAwesome icon name (without fa- prefix)
        label: Button text (becomes aria-label if icon_only)
        variant: 'primary', 'secondary', 'report', 'log'
        full_width: Add btn--full class
        icon_only: Render icon-only button with aria-label
    """
    return {
        "url": url,
        "label": label,
        "icon": icon,
        "variant": variant,
        "full_width": full_width,
        "icon_only": icon_only,
    }


@register.inclusion_tag("components/stat_grid.html")
def stat_grid(stats: list):
    """Render a grid of statistics.

    Usage:
        {% stat_grid stats=stats_list %}

    Args:
        stats: List of dicts with 'value', 'label', and optional 'variant' keys
               variant can be 'problem', 'log', or None for default styling
    """
    return {"stats": stats}


@register.inclusion_tag("components/empty_state.html")
def empty_state(empty_message: str, search_message: str, is_search: bool = False):
    """Render an empty state message, with search-aware variant.

    Usage:
        {% empty_state empty_message="No log entries yet." search_message="No log entries match your search." is_search=search_form.q.value %}

    Args:
        empty_message: Message shown when there are no items
        search_message: Message shown when search returns no results
        is_search: Whether a search is active (typically search_form.q.value)
    """
    return {
        "empty_message": empty_message,
        "search_message": search_message,
        "is_search": bool(is_search),
    }


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


# -----------------------------------------------------------------------------
# Sidebar template tags
# -----------------------------------------------------------------------------


@register.simple_block_tag
def sidebar(content):
    """Wrap content in a sticky sidebar card.

    Usage:
        {% sidebar %}
          {% sidebar_section title="Stats" %}...{% endsidebar_section %}
          {% sidebar_section title="Actions" %}...{% endsidebar_section %}
        {% endsidebar %}
    """
    return format_html(
        '<div class="card card--padded sidebar--sticky">\n{}</div>',
        content,
    )


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


# -----------------------------------------------------------------------------
# Timeline template tags
# -----------------------------------------------------------------------------


@register.simple_block_tag
def timeline(content, id="", inject_log_entries=True):
    """Wrap content in a timeline container with vertical line.

    Usage:
        {% timeline %}
          {% for entry in entries %}
            {% include "partials/entry.html" %}
          {% endfor %}
        {% endtimeline %}

        {% timeline id="log-list" inject_log_entries=False %}...{% endtimeline %}

    Args:
        id: Optional HTML id attribute
        inject_log_entries: If True (default), AJAX status/location changes will
                            inject new log entries into this timeline. Set to False
                            for timelines that shouldn't receive log entries (e.g.,
                            problem reports list).
    """
    id_attr = f' id="{id}"' if id else ""
    inject_attr = ' data-inject-log-entries="true"' if inject_log_entries else ""
    return format_html(
        '<div class="timeline"{}{}>\n' '  <div class="timeline__line"></div>\n' "{}" "</div>",
        mark_safe(id_attr),  # noqa: S308 - id is from template, not user input
        mark_safe(inject_attr),  # noqa: S308 - data attr is from template, not user input
        content,
    )


@register.simple_block_tag
def timeline_entry(content, icon, variant="log"):
    """Wrap content in a timeline entry with icon.

    Usage:
        {% timeline_entry icon="comment" variant="log" %}
          <article class="card card--log timeline__card">
            ...card content...
          </article>
        {% endtimeline_entry %}

    Args:
        content: The card content (captured between tags)
        icon: FontAwesome icon name (e.g., "comment", "screwdriver-wrench", "bug")
        variant: "log" or "problem" for color styling
    """
    return format_html(
        '<div class="timeline__entry">\n'
        '  <div class="timeline__entry-inner">\n'
        '    <div class="timeline__icon timeline__icon--{}">\n'
        '      <i class="fa-solid fa-{}"></i>\n'
        "    </div>\n"
        '    <div class="timeline__content">\n'
        "{}"
        "    </div>\n"
        "  </div>\n"
        "</div>",
        variant,
        icon,
        content,
    )
