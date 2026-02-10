"""Reusable view mixins for the core app."""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.db import transaction
from django.http import JsonResponse
from django.template.loader import render_to_string

from the_flip.apps.core.tasks import enqueue_transcode

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from django.db import models
    from django.db.models import QuerySet
    from django.http import HttpRequest


def can_access_maintainer_portal(user: AbstractUser | Any) -> bool:
    """
    Check if user can access the maintainer portal.

    Used by CanAccessMaintainerPortalMixin and inline permission checks.
    Uses permission-based check. Superusers automatically pass via has_perm().
    """
    return user.has_perm("accounts.can_access_maintainer_portal")


class FormPrefillMixin:
    """Pre-fill a form field from session data.

    Any feature can seed a form by storing in ``request.session["form_prefill"]``::

        {"field": "description", "content": "..."}

    An optional ``extra_initial`` dict can supply additional initial values::

        {"field": "description", "content": "...", "extra_initial": {"priority": "task"}}

    An optional ``template_content_url`` identifies the wiki template that
    produced the prefill, so the template selector dropdown can pre-select it::

        {"field": "description", "content": "...", "template_content_url": "/api/wiki/..."}

    The mixin pops the data on GET so the session is cleaned up automatically.

    Views can extend ``get_initial()`` to pop additional session keys
    (e.g. ``WikiPageCreateView`` adds ``form_prefill_tags`` and ``form_prefill_title``).
    """

    _prefill_template_url: str = ""

    def get_initial(self):
        initial = super().get_initial()
        prefill = self.request.session.pop("form_prefill", None)
        if prefill:
            initial[prefill["field"]] = prefill["content"]
            if prefill.get("extra_initial"):
                initial.update(prefill["extra_initial"])
            self._prefill_template_url = prefill.get("template_content_url", "")
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self._prefill_template_url:
            context["prefill_template_url"] = self._prefill_template_url
        return context


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
            - request.FILES["media_file"]: The uploaded file

        Returns:
            JsonResponse with media details or error
        """
        if "media_file" not in request.FILES:
            return JsonResponse({"success": False, "error": "No file provided"}, status=400)

        upload = request.FILES["media_file"]
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
            "media_type": media_model.MediaType.VIDEO if is_video else media_model.MediaType.PHOTO,
            "file": upload,
            "transcode_status": media_model.TranscodeStatus.PENDING if is_video else "",
        }

        media = media_model.objects.create(**create_kwargs)

        if is_video:
            transaction.on_commit(
                partial(enqueue_transcode, media_id=media.id, model_name=media_model.__name__)
            )

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


class InfiniteScrollMixin:
    """
    Mixin for views that return paginated JSON for infinite scroll.

    Provides a standard get() implementation that:
    1. Calls get_queryset() to get items
    2. Paginates using page_size and page_param
    3. Renders each item using item_template
    4. Returns JSON with items HTML, has_next, and next_page

    Subclasses must set:
        - item_template: Template path for rendering each item

    Subclasses must implement:
        - get_queryset(): Return the queryset to paginate

    Subclasses may override:
        - get_item_context(item): Return context dict for each item (default: {"entry": item})
        - page_size: Items per page (default: settings.LIST_PAGE_SIZE)
        - page_param: Query param for page number (default: "page")
    """

    item_template: str
    page_size: int = settings.LIST_PAGE_SIZE
    page_param: str = "page"
    request: HttpRequest  # Provided by View

    def get_queryset(self) -> QuerySet:
        """Return the queryset to paginate."""
        raise NotImplementedError("Subclasses must implement get_queryset()")

    def get_item_context(self, item: Any) -> dict[str, Any]:
        """Return template context for a single item."""
        return {"entry": item}

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
        """Handle GET request, returning paginated JSON."""
        queryset = self.get_queryset()
        paginator = Paginator(queryset, self.page_size)
        page_obj = paginator.get_page(request.GET.get(self.page_param))

        items_html = "".join(
            render_to_string(self.item_template, self.get_item_context(item), request=request)
            for item in page_obj.object_list
        )

        return JsonResponse(
            {
                "items": items_html,
                "has_next": page_obj.has_next(),
                "next_page": page_obj.next_page_number() if page_obj.has_next() else None,
            }
        )
