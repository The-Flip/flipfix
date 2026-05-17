"""Custom middleware helpers."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from flipfix.apps.accounts.models import Maintainer
from flipfix.apps.accounts.permissions import can_access_maintainer_portal
from flipfix.apps.core.ip import get_real_ip
from flipfix.logging import bind_log_context, reset_log_context


class RequestContextMiddleware:
    """Attach a request ID and user/path metadata to log records."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = request.META.get("HTTP_X_REQUEST_ID") or uuid.uuid4().hex

        user_id = None
        username = None
        if hasattr(request, "user") and getattr(request, "user", None):
            if getattr(request.user, "is_authenticated", False):
                user_id = getattr(request.user, "id", None)
                username = getattr(request.user, "username", None)

        token = bind_log_context(
            request_id=request_id,
            path=request.path,
            method=request.method,
            user_id=user_id,
            username=username,
            remote_ip=get_real_ip(request),
        )
        request.request_id = request_id  # type: ignore[attr-defined]
        try:
            response = self.get_response(request)
        finally:
            reset_log_context(token)

        response.headers.setdefault("X-Request-ID", request_id)
        return response


class MaintainerAccessMiddleware:
    """Require maintainer portal permission unless login-not-required or maintainer-not-required.

    Sits after ``LoginRequiredMiddleware``. At this point the user is guaranteed
    to be authenticated (or the view is explicitly public/infrastructure).
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Permission check is in process_view() so we can inspect the view function's attributes.
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        # login_not_required() sets view_func.login_required = False.
        # Skip entirely for always_public, infrastructure, and public views.
        if not getattr(view_func, "login_required", True):
            return None
        # access="authenticated" sets view_func.maintainer_required = False
        if not getattr(view_func, "maintainer_required", True):
            return None
        if not can_access_maintainer_portal(request.user):
            raise PermissionDenied
        return None


class MaintainerActivityMiddleware:
    """Update ``Maintainer.last_active_at`` at most once per 24h per authenticated user.

    The once-per-day gate uses Django's default LocMemCache, which is per-process.
    With N gunicorn workers, worst case is N writes/user/day instead of 1; at
    ~10 maintainers and a handful of workers that's <100 writes/day total —
    well below any threshold worth introducing shared-cache infrastructure
    (Redis, DB cache) to fix. If a single fleet-wide write per day later
    becomes desirable, swap ``CACHES`` to a shared backend and no code in this
    class needs to change.
    """

    CACHE_KEY_TEMPLATE = "maintainer_last_active:{user_id}"
    CACHE_TTL_SECONDS = 60 * 60 * 24

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        self._touch(request)
        return response

    def _touch(self, request: HttpRequest) -> None:
        # AuthenticationMiddleware guarantees request.user exists as a User
        # or AnonymousUser; both expose is_authenticated.
        if not request.user.is_authenticated:
            return
        key = self.CACHE_KEY_TEMPLATE.format(user_id=request.user.id)
        # cache.add returns False if the key already exists — that's the
        # once-per-24h gate (per process; see class docstring).
        if not cache.add(key, True, self.CACHE_TTL_SECONDS):
            return
        # .filter().update() no-ops (rowcount=0) for authenticated users that
        # have no Maintainer row — including the 403'd non-maintainers that
        # still reach this middleware on the response path. We rely on this
        # no-op (not on middleware order) for correctness.
        #
        # Using .update() instead of .save() also skips signals and
        # TimeStampedMixin.updated_at (auto_now fires on save only), so
        # "last active" doesn't accidentally bump "profile last edited."
        Maintainer.objects.filter(user_id=request.user.id).update(last_active_at=timezone.now())
