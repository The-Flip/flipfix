"""Custom middleware helpers."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from the_flip.apps.core.ip import get_real_ip
from the_flip.logging import bind_log_context, reset_log_context


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
