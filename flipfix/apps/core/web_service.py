"""Calls from the worker service to the web service's internal API.

In production the web and worker are separate services, and only the web
service has the media disk mounted. Anything that touches uploaded files
(transcoding transfers, deleting media) therefore has to happen on the web
service; the worker asks for it over HTTP, authenticated with the shared
``TRANSCODING_UPLOAD_TOKEN`` (checked by ``api_auth.validate_worker_token``).
"""

from __future__ import annotations

from urllib.parse import urlsplit

import requests
from django.conf import settings

ERROR_EXCERPT_CHARS = 200
"""How much of a non-JSON error body to quote in the raised error."""


def require_web_service_config(web_service_url: str | None, token: str | None) -> tuple[str, str]:
    """Return ``(web_service_url, token)`` after validating them.

    Raises ValueError naming whatever is missing, or if the URL would send the
    token in cleartext: plain ``http`` is only allowed to this machine (local
    development); everything else must be ``https``.
    """
    if web_service_url and token:
        _require_secure_transport(web_service_url)
        return web_service_url, token
    missing = [
        name
        for name, value in (
            ("DJANGO_WEB_SERVICE_URL", web_service_url),
            ("TRANSCODING_UPLOAD_TOKEN", token),
        )
        if not value
    ]
    raise ValueError(f"Required environment variables not configured: {', '.join(missing)}")


_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _require_secure_transport(web_service_url: str) -> None:
    """Reject URLs that would carry the worker token unencrypted off this machine."""
    parts = urlsplit(web_service_url)
    if parts.scheme == "https" or (parts.scheme == "http" and parts.hostname in _LOOPBACK_HOSTS):
        return
    raise ValueError(
        "DJANGO_WEB_SERVICE_URL must use https (plain http is only allowed to localhost)"
    )


def post_to_web_service(path: str, *, timeout: int = 300) -> dict:
    """POST to an internal web-service endpoint and return its JSON body.

    Args:
        path: URL path on the web service, e.g. ``reverse("api-wiki-media-sweep")``.
        timeout: Seconds to wait for the response.

    Raises:
        ValueError: If the web service URL or token isn't configured.
        RuntimeError: If the web service responds with an error.
        requests.RequestException: If the request itself fails.
    """
    base_url, token = require_web_service_config(
        settings.DJANGO_WEB_SERVICE_URL, settings.TRANSCODING_UPLOAD_TOKEN
    )
    response = requests.post(
        f"{base_url.rstrip('/')}{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
        # The request carries the worker token; never follow a redirect with it
        # (requests keeps Authorization on some same-host redirects). A 3xx is
        # reported as a failure below.
        allow_redirects=False,
    )
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code != 200 or not body.get("success"):
        detail = body.get("error") or response.text[:ERROR_EXCERPT_CHARS].strip()
        raise RuntimeError(
            f"Web service call to {path} failed: HTTP {response.status_code}: {detail}"
        )
    return body
