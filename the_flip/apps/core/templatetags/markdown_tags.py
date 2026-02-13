"""Markdown pipeline: render_markdown, storage_to_authoring."""

from django import template

register = template.Library()


@register.filter
def storage_to_authoring(text):
    """Convert storage-format links to authoring format for editing.

    Storage format uses PKs (e.g., ``[[machine:id:42]]``).
    Authoring format uses slugs (e.g., ``[[machine:blackout]]``).
    ID-based types (e.g., ``[[log:7]]``) pass through unchanged.

    Usage in templates::

        <textarea>{{ content|storage_to_authoring }}</textarea>
    """
    if not text:
        return text
    from the_flip.apps.core.markdown_links import convert_storage_to_authoring

    return convert_storage_to_authoring(text)


@register.filter
def render_markdown(text):
    """Convert markdown text to sanitized HTML."""
    from the_flip.apps.core.markdown import render_markdown_html

    return render_markdown_html(text)
