"""Project-level views."""
from __future__ import annotations

import mimetypes
from pathlib import Path

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.http import FileResponse, Http404, JsonResponse
from django.utils._os import safe_join


def health_check(request):
    """Lightweight health endpoint for platform probes."""
    return JsonResponse({"status": "ok"})


def serve_media(request, path: str):
    """Serve user-uploaded media files from MEDIA_ROOT."""
    if not getattr(settings, "MEDIA_ROOT", None):
        raise Http404("Media storage is not configured.")

    try:
        full_path = Path(safe_join(str(settings.MEDIA_ROOT), path))
    except (ValueError, SuspiciousFileOperation) as exc:
        raise Http404("Invalid media path.") from exc

    if not full_path.is_file():
        raise Http404("Media not found.")

    content_type, _ = mimetypes.guess_type(str(full_path))
    response = FileResponse(full_path.open("rb"), content_type=content_type)
    response["Content-Length"] = full_path.stat().st_size
    return response
