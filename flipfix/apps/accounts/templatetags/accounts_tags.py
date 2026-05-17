"""Accounts template filters.

Thin wrappers exposing :mod:`flipfix.apps.accounts.display` and
:mod:`flipfix.apps.accounts.permissions` helpers to templates. Keeping the
filter definitions consistent (decorator-bound, single-line bodies) makes
it easy to scan this module for the full list of accounts filters.
"""

from django import template

from flipfix.apps.accounts.display import (
    display_name_with_username as _display_name_with_username,
)
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


@register.filter(name="display_name_with_username")
def display_name_with_username(user) -> str:
    """Return ``"First Last (username)"`` or just ``username``.

    Single source of truth: :func:`flipfix.apps.accounts.display.display_name_with_username`.
    """
    return _display_name_with_username(user)


@register.filter(name="can_manage_catalog")
def can_manage_catalog(user) -> bool:
    """Return whether ``user`` is a working catalog manager.

    Thin wrapper over ``flipfix.apps.accounts.permissions.can_manage_catalog``
    so templates can write::

        {% load accounts_tags %}
        {% if user|can_manage_catalog %}...{% endif %}

    Single source of truth: the predicate logic (portal access AND the
    catalog-management permission) lives in
    ``flipfix.apps.accounts.permissions``.
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
