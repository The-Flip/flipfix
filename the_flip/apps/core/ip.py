"""Client IP address utilities."""

from __future__ import annotations

from django.http import HttpRequest
from ipware import get_client_ip


def get_real_ip(request: HttpRequest) -> str | None:
    """
    Extract the real client IP address from a request.

    Uses django-ipware to correctly handle proxied requests (e.g., behind
    Railway, Cloudflare, or other reverse proxies) by parsing X-Forwarded-For
    and related headers.

    Returns None if the IP cannot be determined.
    """
    ip, _ = get_client_ip(request)
    return ip
