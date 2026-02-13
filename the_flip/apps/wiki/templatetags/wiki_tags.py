"""Wiki-specific template tags."""

from django import template
from django.utils.safestring import mark_safe

from the_flip.apps.core.markdown import render_markdown_html
from the_flip.apps.wiki.actions import inject_buttons, prepare_for_rendering

register = template.Library()


@register.simple_tag
def render_wiki_content(page):
    """Render wiki page content with action buttons.

    Processes action block markers before the markdown pipeline, then
    injects button HTML after sanitization.

    If any markers are malformed the page falls back to plain markdown
    rendering with no partial marker artefacts.

    Usage::

        {% load wiki_tags %}
        {% render_wiki_content page %}
    """
    content = page.content or ""
    if not content:
        return ""

    processed, token_map = prepare_for_rendering(content)
    html = render_markdown_html(processed)

    if token_map:
        html = inject_buttons(html, token_map, page.pk)
        return mark_safe(html)  # noqa: S308 — nh3-sanitized HTML + format_html-escaped buttons

    return html
