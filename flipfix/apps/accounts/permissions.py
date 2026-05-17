"""Capability predicates for the accounts domain.

These helpers wrap permission checks and directory-membership queries
whose business meaning lives in this app. They are imported by
middleware, routing, nav rendering, and any view or template that needs
to gate behavior on a maintainer capability.

They live here (not in ``core/mixins.py``) so that ``core`` stays free
of dependencies on sibling apps' models and codenames. ``core`` houses
genuinely shared utilities; capability checks are accounts-domain logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .models import Maintainer

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


def can_access_maintainer_portal(user: AbstractUser | Any) -> bool:
    """Check if user can access the maintainer portal.

    Used by ``MaintainerAccessMiddleware`` and inline permission checks.
    Superusers automatically pass via ``has_perm()``.
    """
    return user.has_perm("accounts.can_access_maintainer_portal")


def can_manage_catalog(user: AbstractUser | Any) -> bool:
    """Check if user is a working catalog manager.

    Requires both maintainer portal access and the catalog management
    permission. Superusers pass via ``has_perm()`` auto-pass.
    """
    return can_access_maintainer_portal(user) and user.has_perm("accounts.can_manage_catalog")


def can_view_user_profiles(user: AbstractUser | Any) -> bool:
    """Check if user can view the user directory and profile pages.

    Requires maintainer portal access and the directory-viewing permission.
    Superusers pass via ``has_perm()`` auto-pass.
    """
    return can_access_maintainer_portal(user) and user.has_perm("accounts.can_view_user_profiles")


def is_in_user_directory(user: AbstractUser | Any) -> bool:
    """Whether ``user`` appears in the public user directory.

    Derived from ``Maintainer.objects.in_user_directory()`` so the
    visibility rule has a single source of truth.
    """
    if not user.is_authenticated:
        return False
    return Maintainer.objects.in_user_directory().filter(user=user).exists()
