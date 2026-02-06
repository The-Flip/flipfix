"""Markdown rendering pipeline.

Shared utility for converting markdown text to sanitized HTML. Used by
the ``render_markdown`` template filter and the wiki action rendering tag.
"""

import re

import markdown as md
import nh3
from linkify_it import LinkifyIt

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

# Regex for task list items: matches <li> followed by optional <p>, then [ ], [  ], [], [x], or [X]
# Group 1: optional whitespace+<p> (for blank-line-separated list items)
# Group 2: the check character to determine checked state (spaces or empty = unchecked)
_TASK_LIST_RE = re.compile(r"<li>(\s*<p>)?\s*\[( *|[xX])\]")


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


def _convert_task_list_items(html: str) -> str:
    """Convert task list markers in <li> tags to checkbox HTML.

    After markdown and nh3 processing, literal [ ] and [x] text inside <li> tags
    is converted to checkbox inputs. Each checkbox gets a sequential
    data-checkbox-index attribute for JavaScript targeting.

    This runs AFTER nh3 sanitization, so the injected <input> elements are
    trusted server code, not user-supplied HTML.

    Args:
        html: Sanitized HTML containing <li>[ ] or <li>[x] patterns

    Returns:
        HTML with task list markers replaced by checkbox inputs
    """
    counter = 0

    def _replace(match: re.Match) -> str:
        nonlocal counter
        idx = counter
        counter += 1
        p_tag = match.group(1) or ""  # Preserve <p> if present (blank-line-separated items)
        check_char = match.group(2)
        checked_attr = " checked" if check_char in ("x", "X") else ""
        return (
            f'<li class="task-list-item">{p_tag}'
            f'<input type="checkbox"{checked_attr} data-checkbox-index="{idx}" disabled>'
        )

    return _TASK_LIST_RE.sub(_replace, html)


def render_markdown_html(text: str) -> str:
    """Convert markdown text to sanitized HTML.

    Full pipeline: wiki links → markdown → linkify → nh3 → checkboxes.

    Args:
        text: Raw markdown text (may contain ``[[type:ref]]`` links).

    Returns:
        Sanitized HTML string. The caller is responsible for wrapping
        in ``mark_safe()`` if needed for template rendering.
    """
    if not text:
        return ""
    # Convert [[type:ref]] links to markdown links (before markdown processing)
    from the_flip.apps.core.markdown_links import render_all_links

    text = render_all_links(text)
    # Convert markdown to HTML
    html = md.markdown(text, extensions=["fenced_code", "nl2br", "smarty"])
    # Convert bare URLs to links
    html = _linkify_urls(html)
    # Sanitize to prevent XSS
    safe_html = nh3.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES)
    # Convert task list markers to checkboxes (after sanitization for security)
    return _convert_task_list_items(safe_html)
