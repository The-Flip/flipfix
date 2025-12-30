"""API endpoint to upload media.

Used by the Discord Bot to upload photos and videos from Discord when creating Flipfix records from Discord posts."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.http import Http404, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from the_flip.apps.core.media import ALLOWED_MEDIA_EXTENSIONS, is_video_file
from the_flip.apps.core.models import AbstractMedia, get_media_model

from .transcoding import _json_api_view, _validate_transcoding_auth

logger = logging.getLogger(__name__)


def _get_parent_record(media_model: type[AbstractMedia], parent_id: int) -> Any:
    """
    Look up the parent record for a media model.

    Uses the media model's parent_field_name to determine the parent model,
    then fetches the parent by ID.

    Raises:
        Http404: If parent record not found.
    """
    parent_field_name = media_model.parent_field_name
    parent_field = media_model._meta.get_field(parent_field_name)
    parent_model = parent_field.related_model
    if parent_model is None:
        raise ValueError(f"Field {parent_field_name} has no related model")

    try:
        return parent_model.objects.get(id=parent_id)  # type: ignore[union-attr]
    except ObjectDoesNotExist as e:
        model_name = getattr(parent_model, "__name__", "Record")
        raise Http404(f"{model_name} with id {parent_id} not found") from e


def _validate_media_file(uploaded_file) -> None:
    """
    Validate the uploaded media file.

    Accepts files with:
    - image/* or video/* content type, OR
    - A supported file extension (for when Discord omits MIME type)

    Raises:
        ValidationError: If file is missing or has invalid type.
    """
    if not uploaded_file:
        raise ValidationError("Missing file")

    content_type = (getattr(uploaded_file, "content_type", "") or "").lower()
    filename = getattr(uploaded_file, "name", "") or ""
    ext = Path(filename).suffix.lower()

    # Accept if content type is valid
    if content_type.startswith(("image/", "video/")):
        return

    # Accept if file extension is supported (fallback for missing MIME types)
    if ext in ALLOWED_MEDIA_EXTENSIONS:
        return

    raise ValidationError(f"Invalid file type: {content_type}")


@method_decorator(csrf_exempt, name="dispatch")
class ReceiveMediaView(View):
    """
    API endpoint to upload media.

    Used by the Discord Bot to upload photos and videos from Discord when creating Flipfix records from Discord posts.

    POST /api/media/<model_name>/<parent_id>/

    Expects multipart/form-data with:
    - file: media file (photo or video)
    - Authorization header: Bearer <token>

    The endpoint determines media type from the file's Content-Type header.
    Videos are stored as-is (no transcoding) since Discord already transcodes.
    Photos are processed (resize, thumbnail) by the model's save() method.
    """

    @_json_api_view
    def post(self, request, model_name: str, parent_id: int):
        _validate_transcoding_auth(request)

        uploaded_file = request.FILES.get("file")
        _validate_media_file(uploaded_file)

        try:
            media_model = get_media_model(model_name)
        except ValueError as e:
            raise ValidationError(str(e)) from e

        parent = _get_parent_record(media_model, parent_id)

        return self._create_media_record(media_model, parent, uploaded_file)

    def _create_media_record(self, media_model, parent, uploaded_file) -> JsonResponse:
        """Create a media record from the uploaded file."""
        filename = getattr(uploaded_file, "name", "")
        is_video = is_video_file(uploaded_file)

        # Build kwargs for creating the media record
        # Set transcode_status="" for both photos and videos from Discord:
        # - Photos don't need transcoding
        # - Videos from Discord are already browser-compatible
        parent_field_name = media_model.parent_field_name
        create_kwargs = {
            parent_field_name: parent,
            "media_type": AbstractMedia.MediaType.VIDEO
            if is_video
            else AbstractMedia.MediaType.PHOTO,
            "file": uploaded_file,
            "transcode_status": "",
        }

        media = media_model.objects.create(**create_kwargs)

        logger.info(
            "media_api_upload_success",
            extra={
                "model_name": media_model.__name__,
                "parent_id": parent.id,
                "media_id": media.id,
                "media_type": media.media_type,
                "original_filename": filename,
            },
        )

        return JsonResponse(
            {
                "success": True,
                "media_id": media.id,
                "media_type": media.media_type,
            }
        )
