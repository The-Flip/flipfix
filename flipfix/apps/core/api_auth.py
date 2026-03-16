"""Shared API authentication utilities.

Provides a decorator and helpers for Bearer-token-authenticated JSON API
endpoints.  Used by the transcoding API, media upload API, and the
read-only machine list API.
"""

from __future__ import annotations

import logging
from functools import wraps

from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.utils.crypto import constant_time_compare

logger = logging.getLogger(__name__)


class ApiAuthError(Exception):
    """Raised when API authentication or authorization fails."""

    def __init__(self, message: str, status: int = 401):
        self.message = message
        self.status = status
        super().__init__(message)


def json_api_view(view_method):
    """Decorator that converts exceptions to JSON error responses.

    Handles:
    - ApiAuthError -> 401/403 with error message
    - ValidationError -> 400 with error message
    - Http404 -> 404 with error message
    - OSError -> 500 with "File storage error" message (logged)
    - Other exceptions -> 500 with generic message (logged)
    """

    @wraps(view_method)
    def wrapper(self, request, *args, **kwargs):
        try:
            return view_method(self, request, *args, **kwargs)
        except ApiAuthError as e:
            return JsonResponse({"success": False, "error": e.message}, status=e.status)
        except ValidationError as e:
            return JsonResponse({"success": False, "error": "; ".join(e.messages)}, status=400)
        except Http404 as e:
            return JsonResponse({"success": False, "error": str(e) or "Not found"}, status=404)
        except OSError:
            logger.exception("File storage error in %s", view_method.__name__)
            return JsonResponse({"success": False, "error": "File storage error"}, status=500)
        except Exception:
            logger.exception("Unexpected error in %s", view_method.__name__)
            return JsonResponse({"success": False, "error": "Internal server error"}, status=500)

    return wrapper


def _parse_bearer_token(request) -> str:
    """Extract Bearer token from the Authorization header.

    Raises ApiAuthError if the header is missing or malformed.
    """
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if not auth_header.startswith("Bearer "):
        raise ApiAuthError("Missing or invalid Authorization header", status=401)
    return auth_header[7:]


def validate_api_key(request):
    """Validate Bearer token against the ApiKey table.

    Returns the matched ``ApiKey`` instance.
    Raises ``ApiAuthError`` on failure.
    """
    from flipfix.apps.core.models import ApiKey

    token = _parse_bearer_token(request)

    for api_key in ApiKey.objects.all():
        if constant_time_compare(token, api_key.key):
            return api_key

    raise ApiAuthError("Invalid API key", status=403)
