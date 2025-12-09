"""Reusable view mixins for the core app."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import JsonResponse

from the_flip.apps.core.tasks import enqueue_transcode

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from django.db import models
    from django.http import HttpRequest


def can_access_maintainer_portal(user: AbstractUser | Any) -> bool:
    """
    Check if user can access the maintainer portal.

    Used by CanAccessMaintainerPortalMixin and inline permission checks.
    Currently checks is_staff or is_superuser.
    Will switch to permission-based in Phase 2.
    """
    return user.is_staff or user.is_superuser


class CanAccessMaintainerPortalMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Mixin requiring maintainer portal access.

    Behavior:
    - Unauthenticated users -> redirect to login
    - Authenticated but unauthorized -> 403
    """

    request: HttpRequest  # Provided by View

    def test_func(self) -> bool:
        return can_access_maintainer_portal(self.request.user)


class CanManageTerminalsMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Mixin requiring terminal management access.

    Currently checks is_superuser.
    """

    request: HttpRequest  # Provided by View

    def test_func(self) -> bool:
        return self.request.user.is_superuser


class MediaUploadMixin:
    """
    Mixin for views that handle media upload and delete actions.

    Provides handle_upload_media() and handle_delete_media() methods
    that can be called from a view's post() method.

    Subclasses must implement:
        - get_media_model(): Return the media model class (e.g., LogEntryMedia)
        - get_media_parent(): Return the parent object for new media
    """

    def get_media_model(self) -> Any:
        """Return the media model class to use for uploads."""
        raise NotImplementedError("Subclasses must implement get_media_model()")

    def get_media_parent(self) -> models.Model:
        """Return the parent object to attach media to."""
        raise NotImplementedError("Subclasses must implement get_media_parent()")

    def handle_upload_media(self, request: HttpRequest) -> JsonResponse:
        """
        Handle media file upload from AJAX request.

        Expects:
            - request.FILES["file"]: The uploaded file

        Returns:
            JsonResponse with media details or error
        """
        if "file" not in request.FILES:
            return JsonResponse({"success": False, "error": "No file provided"}, status=400)

        upload = request.FILES["file"]
        content_type = (getattr(upload, "content_type", "") or "").lower()
        ext = Path(getattr(upload, "name", "")).suffix.lower()
        is_video = content_type.startswith("video/") or ext in {
            ".mp4",
            ".mov",
            ".m4v",
            ".hevc",
        }

        media_model = self.get_media_model()
        parent = self.get_media_parent()

        # Get the FK field name from the model's parent_field_name class attribute
        parent_field_name = media_model.parent_field_name

        create_kwargs: dict[str, Any] = {
            parent_field_name: parent,
            "media_type": media_model.TYPE_VIDEO if is_video else media_model.TYPE_PHOTO,
            "file": upload,
            "transcode_status": media_model.STATUS_PENDING if is_video else "",
        }

        media = media_model.objects.create(**create_kwargs)

        if is_video:
            enqueue_transcode(media.id, model_name=media_model.__name__)

        return JsonResponse(
            {
                "success": True,
                "media_id": media.id,
                "media_url": media.file.url,
                "thumbnail_url": media.thumbnail_file.url
                if media.thumbnail_file
                else media.file.url,
                "media_type": media.media_type,
                "transcode_status": media.transcode_status,
                "poster_url": media.poster_file.url if media.poster_file else None,
            }
        )

    def handle_delete_media(self, request: HttpRequest) -> JsonResponse:
        """
        Handle media deletion from AJAX request.

        Expects:
            - request.POST["media_id"]: ID of media to delete

        Returns:
            JsonResponse with success status or error
        """
        media_id = request.POST.get("media_id")
        if not media_id:
            return JsonResponse({"success": False, "error": "No media_id provided"}, status=400)

        media_model = self.get_media_model()
        parent = self.get_media_parent()
        parent_field_name = media_model.parent_field_name

        try:
            filter_kwargs = {"id": media_id, parent_field_name: parent}
            media = media_model.objects.get(**filter_kwargs)

            # Delete associated files
            if media.transcoded_file:
                media.transcoded_file.delete(save=False)
            if media.poster_file:
                media.poster_file.delete(save=False)
            if media.thumbnail_file:
                media.thumbnail_file.delete(save=False)
            media.file.delete()
            media.delete()

            return JsonResponse({"success": True})

        except media_model.DoesNotExist:
            return JsonResponse({"success": False, "error": "Media not found"}, status=404)
