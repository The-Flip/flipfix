"""Project-level routing utilities.

Provides a custom ``path()`` that supports ``access=`` annotations for the
public access system.

Usage in ``urls.py``::

    from flipfix.apps.core.routing import path

    urlpatterns = [
        # Default: logged-in maintainer
        path("parts/", PartRequestListView.as_view(), name="part-request-list"),

        # Public when toggle is on (guest-aware, read-only, cached)
        path("machines/", MachineListView.as_view(), name="machine-list", access="public"),

        # Always open — infrastructure (login page, healthz, QR form, API endpoints)
        path("healthz", healthz, name="healthz", access="always_public"),

        # Logged-in, any role — profile, password change
        path("profile/", ProfileUpdateView.as_view(), name="profile", access="authenticated"),

        # Superuser only
        path("terminals/", TerminalListView.as_view(), name="terminal-list", access="superuser"),
    ]
"""

from __future__ import annotations

from functools import wraps
from typing import Literal

from constance import config
from django.conf import settings
from django.contrib.auth.decorators import login_not_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseNotAllowed
from django.urls import path as django_path
from django.utils.cache import patch_cache_control

from flipfix.apps.accounts.permissions import can_access_maintainer_portal

_public_url_names: set[str] = set()

PUBLIC_CACHE_MAX_AGE = 300  # 5 minutes

_AccessLevel = Literal["always_public", "authenticated", "public", "superuser"]

_VALID_ACCESS_LEVELS = {"always_public", "authenticated", "public", "superuser"}


def path(
    route_path,
    view,
    *,
    access: _AccessLevel | None = None,
    **kwargs,
):
    """Project-level path() — delegates to Django's path() with extra routing options.

    Args:
        access: Access level override.

            - ``"always_public"`` — no auth required, regardless of toggle.
              For infrastructure views (login, healthz, QR form, Bearer-auth APIs).
            - ``"authenticated"`` — any logged-in user, skips maintainer permission
              check. For profile, password change, logout.
            - ``"public"`` — open to unauthenticated visitors when
              ``PUBLIC_ACCESS_ENABLED`` is on; redirects to login when off.
            - ``"superuser"`` — superuser only.
            - ``None`` (default) — logged-in maintainer.
    """
    if access is not None and access not in _VALID_ACCESS_LEVELS:
        msg = f"Invalid access level {access!r}. Must be one of {_VALID_ACCESS_LEVELS}"
        raise ValueError(msg)
    if access == "always_public":
        view = login_not_required(view)
    elif access == "authenticated":
        view = _mark_no_maintainer_required(view)
    elif access == "public":
        name = kwargs.get("name", "")
        if name:
            _public_url_names.add(name)
        view = _wrap_for_public_access(view)
        view = login_not_required(view)  # bypass middleware; wrapper handles redirect
    elif access == "superuser":
        view = _wrap_require_superuser(view)
    return django_path(route_path, view, **kwargs)


def _mark_no_maintainer_required(view_func):
    """Mark a view so MaintainerAccessMiddleware skips the permission check."""
    view_func.maintainer_required = False
    return view_func


def _wrap_for_public_access(view_func):
    """Wrap a view to enable public access for unauthenticated visitors."""

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            if not config.PUBLIC_ACCESS_ENABLED:
                from django.contrib.auth.views import redirect_to_login

                return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
            # Anonymous visitors are read-only
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                return HttpResponseNotAllowed(["GET", "HEAD", "OPTIONS"])
        elif not can_access_maintainer_portal(request.user):
            # Authenticated non-maintainers are also read-only
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                raise PermissionDenied
        response = view_func(request, *args, **kwargs)
        if not request.user.is_authenticated:
            patch_cache_control(response, public=True, max_age=PUBLIC_CACHE_MAX_AGE)
        return response

    wrapped.public_access_view = True
    return wrapped


def _wrap_require_superuser(view_func):
    """Wrap a view to require superuser access."""

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapped


def get_public_url_names() -> frozenset[str]:
    """Return the set of URL names marked access="public". Used by nav tags."""
    return frozenset(_public_url_names)


def _reset_public_url_names() -> None:
    """Test utility — clear the public URL name registry."""
    _public_url_names.clear()
