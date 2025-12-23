"""Video transcoding worker API endpoints."""

from __future__ import annotations

import logging
from functools import partial, wraps

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import FileResponse, Http404, JsonResponse
from django.utils.crypto import constant_time_compare
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from the_flip.apps.core.models import AbstractMedia, get_media_model

logger = logging.getLogger(__name__)


class _AuthenticationError(Exception):
    """Raised when API authentication fails."""

    def __init__(self, message: str, status: int = 401):
        self.message = message
        self.status = status
        super().__init__(message)


def _json_api_view(view_method):
    """
    Decorator that converts exceptions to JSON error responses.

    Handles:
    - _AuthenticationError → 401/403 with error message
    - ValidationError → 400 with error message
    - Http404 → 404 with error message
    - OSError → 500 with "File storage error" message (logged)
    - Other exceptions → 500 with generic message (logged)
    """

    @wraps(view_method)
    def wrapper(self, request, *args, **kwargs):
        try:
            return view_method(self, request, *args, **kwargs)
        except _AuthenticationError as e:
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


def _validate_transcoding_auth(request) -> None:
    """
    Validate Bearer token authentication for transcoding API endpoints.

    Raises:
        _AuthenticationError: If authentication fails.
    """
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if not auth_header.startswith("Bearer "):
        raise _AuthenticationError("Missing or invalid Authorization header", status=401)

    token = auth_header[7:]
    if not settings.TRANSCODING_UPLOAD_TOKEN:
        raise _AuthenticationError("Server not configured for transcoding", status=500)

    if not constant_time_compare(token, settings.TRANSCODING_UPLOAD_TOKEN):
        raise _AuthenticationError("Invalid authentication token", status=403)


def _get_media_record(model_name: str, media_id: int) -> tuple[type, AbstractMedia]:
    """
    Look up a media record by model name and ID.

    Raises:
        ValidationError: If model_name is invalid.
        Http404: If media record not found.
    """
    try:
        media_model = get_media_model(model_name)
    except ValueError as e:
        raise ValidationError(str(e)) from e

    try:
        media = media_model.objects.get(id=media_id)
    except media_model.DoesNotExist as e:
        raise Http404(f"{model_name} with id {media_id} not found") from e

    return media_model, media


def _validate_upload_files(video_file, poster_file) -> None:
    """
    Validate uploaded video and poster files.

    Raises:
        ValidationError: If files are missing or have invalid types.
    """
    if not video_file:
        raise ValidationError("Missing video_file")

    video_content_type = (getattr(video_file, "content_type", "") or "").lower()
    if not video_content_type.startswith("video/"):
        raise ValidationError(f"Invalid video file type: {video_content_type}")

    if poster_file:
        poster_content_type = (getattr(poster_file, "content_type", "") or "").lower()
        if not poster_content_type.startswith("image/"):
            raise ValidationError(f"Invalid poster file type: {poster_content_type}")


@method_decorator(csrf_exempt, name="dispatch")
class ReceiveTranscodedMediaView(View):
    """
    API endpoint for worker service to upload transcoded video files.

    POST /api/transcoding/upload/<model_name>/<media_id>/

    Expects multipart/form-data with:
    - video_file: transcoded video file
    - poster_file: generated poster image
    - Authorization header: Bearer <token>
    """

    @_json_api_view
    def post(self, request, model_name: str, media_id: int):
        _validate_transcoding_auth(request)

        video_file = request.FILES.get("video_file")
        poster_file = request.FILES.get("poster_file")
        _validate_upload_files(video_file, poster_file)

        media_model, media = _get_media_record(model_name, media_id)

        return self._save_transcoded_files(media, media_model, video_file, poster_file)

    def _save_transcoded_files(self, media, media_model, video_file, poster_file) -> JsonResponse:
        """Save transcoded video and poster files to the media record."""
        original_file_name = media.file.name if media.file else None

        with transaction.atomic():
            if media.file:
                media.file = None

            media.transcoded_file = video_file
            if poster_file:
                media.poster_file = poster_file
            media.transcode_status = media_model.TranscodeStatus.READY
            media.save()

        # Delete original file only after transaction commits successfully
        if original_file_name:
            storage = media.transcoded_file.storage
            transaction.on_commit(partial(storage.delete, name=original_file_name))

        return JsonResponse(
            {
                "success": True,
                "message": "Transcoded media uploaded successfully",
                "media_id": media.id,
                "transcoded_url": media.transcoded_file.url,
                "poster_url": media.poster_file.url if media.poster_file else None,
            }
        )


@method_decorator(csrf_exempt, name="dispatch")
class ServeSourceMediaView(View):
    """
    API endpoint for worker service to download source video files.

    GET /api/transcoding/download/<model_name>/<media_id>/
    Authorization: Bearer <token>

    Returns the source file as a streaming response.
    """

    @_json_api_view
    def get(self, request, model_name: str, media_id: int):
        _validate_transcoding_auth(request)
        _media_model, media = _get_media_record(model_name, media_id)

        if not media.file:
            raise Http404("Media has no source file")

        return FileResponse(
            media.file.open("rb"),
            as_attachment=True,
            filename=media.file.name.split("/")[-1],
        )
