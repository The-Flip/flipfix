"""Accounts domain: display_name_with_username, can_manage_catalog."""

from django import template

from flipfix.apps.core.mixins import can_manage_catalog as _can_manage_catalog

register = template.Library()


@register.filter(name="can_manage_catalog")
def can_manage_catalog(user) -> bool:
    """Return whether ``user`` is a working catalog manager.

    Thin wrapper over ``flipfix.apps.core.mixins.can_manage_catalog`` so
    templates can write::

        {% load accounts_tags %}
        {% if user|can_manage_catalog %}...{% endif %}

    Single source of truth: the predicate logic (portal access AND the
    catalog-management permission) lives in ``mixins.py``.
    """
    return _can_manage_catalog(user)


@register.filter
def display_name_with_username(user):
    """Return user's display name with username suffix.

    Returns "First Last (username)" if first or last name is set,
    otherwise just "username".

    Usage:
        {{ user|display_name_with_username }}
        {{ terminal.user|display_name_with_username }}
    """
    if not user:
        return ""
    first = getattr(user, "first_name", "") or ""
    last = getattr(user, "last_name", "") or ""
    username = getattr(user, "username", "") or ""
    if first or last:
        full_name = f"{first} {last}".strip()
        return f"{full_name} ({username})"
    return username
