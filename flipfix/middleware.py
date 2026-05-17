"""Custom middleware helpers."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse

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
