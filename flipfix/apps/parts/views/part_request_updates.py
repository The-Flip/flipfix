"""Views for part request update CRUD."""

from __future__ import annotations

from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.html import format_html
from django.views.generic import DetailView, FormView, UpdateView

from flipfix.apps.accounts.models import Maintainer
from flipfix.apps.core.attribution import (
    resolve_maintainer_for_create,
    resolve_maintainer_for_edit,
)
from flipfix.apps.core.datetime import apply_and_validate_timezone
from flipfix.apps.core.markdown_links import sync_references
from flipfix.apps.core.media_upload import attach_media_files
from flipfix.apps.core.mixins import (
    CanAccessMaintainerPortalMixin,
    InlineTextEditMixin,
    MediaUploadMixin,
    SharedAccountMixin,
)
from flipfix.apps.parts.forms import (
    PartRequestUpdateEditForm,
    PartRequestUpdateForm,
)
from flipfix.apps.parts.models import (
    PartRequest,
    PartRequestUpdate,
    PartRequestUpdateMedia,
)


class PartRequestUpdateCreateView(SharedAccountMixin, CanAccessMaintainerPortalMixin, FormView):
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
        return context

    def get_initial(self):
        initial = super().get_initial()

        # Pre-fill poster_name with current user's display name (for non-shared accounts)
        if not self.is_shared_account and hasattr(self.request.user, "maintainer"):
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
        occurred_at, is_valid = apply_and_validate_timezone(form, self.request)
        if not is_valid:
            return self.form_invalid(form)

        update.occurred_at = occurred_at
        update.save()
        sync_references(update, update.text)

        # Handle media uploads
        media_files = form.cleaned_data.get("media_file", [])
        if media_files:
            attach_media_files(
                media_files=media_files,
                parent=update,
                media_model=PartRequestUpdateMedia,
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


class PartRequestUpdateDetailView(
    InlineTextEditMixin, CanAccessMaintainerPortalMixin, MediaUploadMixin, DetailView
):
    """Detail view for a part request update. Maintainer-only access."""

    model = PartRequestUpdate
    template_name = "parts/part_update_detail.html"
    context_object_name = "update"

    def get_queryset(self):
        return PartRequestUpdate.objects.select_related(
            "part_request__requested_by__user",
            "part_request__machine",
            "part_request__machine__model",
            "posted_by__user",
        ).prefetch_related("media")

    def get_media_model(self):
        return PartRequestUpdateMedia

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["part_request"] = self.object.part_request
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        action = request.POST.get("action")

        action_handlers = {
            "update_text": self.handle_update_text,
            "upload_media": self.handle_upload_media,
            "delete_media": self.handle_delete_media,
        }

        if action in action_handlers:
            return action_handlers[action](request)

        return JsonResponse({"success": False, "error": f"Unknown action: {action}"}, status=400)


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

        occurred_at, is_valid = apply_and_validate_timezone(form, self.request)
        if not is_valid:
            return self.form_invalid(form)

        update.occurred_at = occurred_at
        update.save()

        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("part-request-update-detail", kwargs={"pk": self.object.pk})
