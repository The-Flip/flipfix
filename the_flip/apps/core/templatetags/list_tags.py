"""List/collection component tags: empty_state, child_list_search, stat_grid, timeline."""

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from the_flip.apps.core.templatetags.ui_tags import icon as icon_tag

register = template.Library()


CHILD_LIST_SEARCH_THRESHOLD = 5
"""Minimum number of child items before showing the search bar."""


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


@register.inclusion_tag("components/child_list_search.html")
def child_list_search(total_count: int, search_value: str = "", placeholder: str = "Search..."):
    """Conditionally render a search bar for child items on detail pages.

    The search bar is shown when there are enough items to warrant searching,
    or when a search query is already active (so the user can clear it).

    Usage:
        {% child_list_search total_count=log_count search_value=search_query placeholder="Search logs..." %}

    Args:
        total_count: Total number of child items (unfiltered)
        search_value: Current search query string
        placeholder: Placeholder text for the search input
    """
    return {
        "show": total_count > CHILD_LIST_SEARCH_THRESHOLD or bool(search_value),
        "value": search_value,
        "placeholder": placeholder,
    }


# ---- Timeline ---------------------------------------------------------------


@register.simple_block_tag
def timeline(content, id="", entry_types=None):
    """Wrap content in a timeline container with vertical line.

    Usage:
        {% timeline %}
          {% for entry in entries %}
            {% include "partials/entry.html" %}
          {% endfor %}
        {% endtimeline %}

        {% timeline id="log-list" entry_types=entry_types %}...{% endtimeline %}

    Args:
        id: Optional HTML id attribute
        entry_types: Tuple/list of entry types this timeline accepts for live injection.
                     When AJAX creates a new log entry, the response includes the entry type.
                     JS checks if that type is in this list before injecting.
                     If not specified or empty, defaults to ["log"] for backwards compatibility.
    """
    id_attr = f' id="{id}"' if id else ""
    # Default to log entries only for backwards compatibility
    if entry_types is None:
        entry_types = ("log",)
    types_str = ",".join(entry_types)
    entry_types_attr = f' data-entry-types="{types_str}"'
    return format_html(
        '<div class="timeline"{}{}>\n  <div class="timeline__line"></div>\n{}</div>',
        mark_safe(id_attr),  # noqa: S308 - id is from template, not user input
        mark_safe(entry_types_attr),  # noqa: S308 - data attr is from template, not user input
        content,
    )


@register.simple_block_tag
def timeline_entry(content, icon: str, variant="log"):
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
    icon_html = icon_tag(icon)
    return format_html(
        '<div class="timeline__entry">\n'
        '  <div class="timeline__entry-inner">\n'
        '    <div class="timeline__icon timeline__icon--{}">\n'
        "      {}\n"
        "    </div>\n"
        '    <div class="timeline__content">\n'
        "{}"
        "    </div>\n"
        "  </div>\n"
        "</div>",
        variant,
        icon_html,
        content,
    )
