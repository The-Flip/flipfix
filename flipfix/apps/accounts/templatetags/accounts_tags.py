"""Accounts domain: display_name_with_username, can_manage_catalog."""

from django import template

from flipfix.apps.accounts.permissions import (
    can_manage_catalog as _can_manage_catalog,
)
from flipfix.apps.accounts.permissions import (
    can_view_user_profiles as _can_view_user_profiles,
)
from flipfix.apps.accounts.permissions import (
    is_in_user_directory as _is_in_user_directory,
)

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


@register.filter(name="can_view_user_profiles")
def can_view_user_profiles(user) -> bool:
    """Return whether ``user`` can view the user directory and profile pages."""
    return _can_view_user_profiles(user)


@register.filter(name="is_in_user_directory")
def is_in_user_directory(user) -> bool:
    """Return whether ``user`` appears in the public user directory.

    Used by ``/profile`` to decide whether to show the photo management section.
    """
    return _is_in_user_directory(user)


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
