"""Views for part request update CRUD."""

from __future__ import annotations

from functools import partial

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import format_html
from django.views.generic import FormView, UpdateView, View

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.core.attribution import (
    resolve_maintainer_for_create,
    resolve_maintainer_for_edit,
)
from the_flip.apps.core.datetime import apply_browser_timezone, validate_not_future
from the_flip.apps.core.markdown_links import (
    save_inline_markdown_field,
    sync_references,
)
from the_flip.apps.core.media import is_video_file
from the_flip.apps.core.mixins import (
    CanAccessMaintainerPortalMixin,
    MediaUploadMixin,
)
from the_flip.apps.core.tasks import enqueue_transcode
from the_flip.apps.parts.forms import (
    PartRequestUpdateEditForm,
    PartRequestUpdateForm,
)
from the_flip.apps.parts.models import (
    PartRequest,
    PartRequestUpdate,
    PartRequestUpdateMedia,
)


class PartRequestUpdateCreateView(CanAccessMaintainerPortalMixin, FormView):
    """Add an update/comment to a part request."""

    template_name = "parts/part_update_new.html"
    form_class = PartRequestUpdateForm

    def dispatch(self, request, *args, **kwargs):
        self.part_request = get_object_or_404(
            PartRequest.objects.select_related("requested_by__user", "machine", "machine__model"),
            pk=kwargs["pk"],
        )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["part_request"] = self.part_request

        # Check if current user is on a shared/terminal account
        is_shared_account = False
        if hasattr(self.request.user, "maintainer"):
            is_shared_account = self.request.user.maintainer.is_shared_account
        context["is_shared_account"] = is_shared_account
        return context

    def get_initial(self):
        initial = super().get_initial()

        # Pre-fill poster_name with current user's display name (for non-shared accounts)
        if hasattr(self.request.user, "maintainer"):
            if not self.request.user.maintainer.is_shared_account:
                initial["poster_name"] = str(self.request.user.maintainer)
        return initial

    @transaction.atomic
    def form_valid(self, form):
        # Resolve poster attribution
        current_maintainer = get_object_or_404(Maintainer, user=self.request.user)
        attribution = resolve_maintainer_for_create(
            self.request,
            current_maintainer,
            form,
            username_field="poster_name_username",
            text_field="poster_name",
        )
        if not attribution:
            return self.form_invalid(form)

        update = form.save(commit=False)
        update.part_request = self.part_request
        update.posted_by = attribution.maintainer
        update.posted_by_name = attribution.freetext_name
        occurred_at = apply_browser_timezone(form.cleaned_data.get("occurred_at"), self.request)

        # Validate after timezone conversion (form validation runs before conversion)
        if not validate_not_future(occurred_at, form):
            return self.form_invalid(form)

        update.occurred_at = occurred_at
        update.save()
        sync_references(update, update.text)

        # Handle media uploads
        media_files = form.cleaned_data.get("media_file", [])
        if media_files:
            for media_file in media_files:
                is_video = is_video_file(media_file)

                media = PartRequestUpdateMedia.objects.create(
                    update=update,
                    media_type=PartRequestUpdateMedia.MediaType.VIDEO
                    if is_video
                    else PartRequestUpdateMedia.MediaType.PHOTO,
                    file=media_file,
                    transcode_status=PartRequestUpdateMedia.TranscodeStatus.PENDING
                    if is_video
                    else "",
                )

                if is_video:
                    transaction.on_commit(
                        partial(
                            enqueue_transcode,
                            media_id=media.id,
                            model_name="PartRequestUpdateMedia",
                        )
                    )

        if update.new_status:
            messages.success(
                self.request,
                format_html(
                    'Part request <a href="{}">#{}</a> updated to {}.',
                    reverse("part-request-detail", kwargs={"pk": self.part_request.pk}),
                    self.part_request.pk,
                    update.get_new_status_display(),
                ),
            )
        else:
            messages.success(
                self.request,
                format_html(
                    'Comment added to part request <a href="{}">#{}</a>.',
                    reverse("part-request-detail", kwargs={"pk": self.part_request.pk}),
                    self.part_request.pk,
                ),
            )

        return redirect("part-request-detail", pk=self.part_request.pk)

    def form_invalid(self, form):
        # Re-render form with errors (default FormView behavior)
        return super().form_invalid(form)


class PartRequestUpdateDetailView(CanAccessMaintainerPortalMixin, MediaUploadMixin, View):
    """Detail view for a part request update. Maintainer-only access."""

    template_name = "parts/part_update_detail.html"

    def get_media_model(self):
        return PartRequestUpdateMedia

    def get_media_parent(self):
        return self.update

    def get(self, request, *args, **kwargs):
        self.update = get_object_or_404(
            PartRequestUpdate.objects.select_related(
                "part_request__requested_by__user",
                "part_request__machine",
                "part_request__machine__model",
                "posted_by__user",
            ).prefetch_related("media"),
            pk=kwargs["pk"],
        )
        return self.render_response(request, self.update)

    def post(self, request, *args, **kwargs):
        self.update = get_object_or_404(
            PartRequestUpdate.objects.select_related(
                "part_request__requested_by__user",
                "part_request__machine",
                "part_request__machine__model",
                "posted_by__user",
            ).prefetch_related("media"),
            pk=kwargs["pk"],
        )
        action = request.POST.get("action")

        # Handle AJAX text update
        if action == "update_text":
            text = request.POST.get("text", "")
            try:
                save_inline_markdown_field(self.update, "text", text)
            except ValidationError as e:
                return JsonResponse({"success": False, "errors": e.messages}, status=400)
            return JsonResponse({"success": True})

        # Handle AJAX media upload
        if action == "upload_media":
            return self.handle_upload_media(request)

        # Handle AJAX media delete
        if action == "delete_media":
            return self.handle_delete_media(request)

        return JsonResponse({"success": False, "error": "Invalid action"}, status=400)

    def render_response(self, request, update):
        context = {
            "update": update,
            "part_request": update.part_request,
        }
        return render(request, self.template_name, context)


class PartRequestUpdateEditView(CanAccessMaintainerPortalMixin, UpdateView):
    """Edit a part request update's metadata (poster, timestamp)."""

    model = PartRequestUpdate
    form_class = PartRequestUpdateEditForm
    template_name = "parts/part_update_edit.html"

    def get_queryset(self):
        return PartRequestUpdate.objects.select_related(
            "part_request__requested_by__user",
            "part_request__machine",
            "part_request__machine__model",
            "posted_by__user",
        )

    def get_initial(self):
        initial = super().get_initial()
        # Pre-fill poster_name with current poster's display name
        if self.object.posted_by:
            initial["poster_name"] = str(self.object.posted_by)
        elif self.object.posted_by_name:
            initial["poster_name"] = self.object.posted_by_name
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["update"] = self.object
        context["part_request"] = self.object.part_request
        return context

    def form_valid(self, form):
        # Resolve poster attribution
        attribution = resolve_maintainer_for_edit(
            self.request,
            form,
            username_field="poster_name_username",
            text_field="poster_name",
            error_message="Please enter a poster name.",
        )
        if not attribution:
            return self.form_invalid(form)

        update = form.save(commit=False)
        update.posted_by = attribution.maintainer
        update.posted_by_name = attribution.freetext_name

        # Apply browser timezone to occurred_at
        occurred_at = apply_browser_timezone(form.cleaned_data.get("occurred_at"), self.request)

        # Validate after timezone conversion (form validation runs before conversion)
        if not validate_not_future(occurred_at, form):
            return self.form_invalid(form)

        update.occurred_at = occurred_at
        update.save()

        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("part-request-update-detail", kwargs={"pk": self.object.pk})
