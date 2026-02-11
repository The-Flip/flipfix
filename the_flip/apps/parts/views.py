"""Views for parts management."""

from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import format_html
from django.views.generic import FormView, TemplateView, UpdateView, View

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.core.attribution import (
    resolve_maintainer_for_create,
    resolve_maintainer_for_edit,
)
from the_flip.apps.core.datetime import apply_browser_timezone, validate_not_future
from the_flip.apps.core.forms import SearchForm
from the_flip.apps.core.markdown_links import (
    save_inline_markdown_field,
    sync_references,
)
from the_flip.apps.core.media import attach_media_files
from the_flip.apps.core.mixins import (
    CanAccessMaintainerPortalMixin,
    FormPrefillMixin,
    InfiniteScrollMixin,
    MediaUploadMixin,
    SharedAccountMixin,
)
from the_flip.apps.parts.forms import (
    PartRequestEditForm,
    PartRequestForm,
    PartRequestUpdateEditForm,
    PartRequestUpdateForm,
)
from the_flip.apps.parts.models import (
    PartRequest,
    PartRequestMedia,
    PartRequestUpdate,
    PartRequestUpdateMedia,
)


def _latest_update_prefetch():
    """Prefetch for ordering updates by most recent."""
    return Prefetch(
        "updates",
        queryset=PartRequestUpdate.objects.order_by("-occurred_at"),
        to_attr="prefetched_updates",
    )


class PartRequestListView(CanAccessMaintainerPortalMixin, TemplateView):
    """List of all part requests. Maintainer-only access."""

    template_name = "parts/part_request_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        search_query = self.request.GET.get("q", "").strip()
        parts = (
            PartRequest.objects.search(search_query)
            .select_related("requested_by__user", "machine", "machine__model")
            .prefetch_related("media", _latest_update_prefetch())
            .order_by("-occurred_at")
        )

        paginator = Paginator(parts, settings.LIST_PAGE_SIZE)
        page_obj = paginator.get_page(self.request.GET.get("page"))

        # Stats for sidebar
        stats = [
            {
                "value": PartRequest.objects.filter(status=PartRequest.Status.REQUESTED).count(),
                "label": "Requested",
            },
            {
                "value": PartRequest.objects.filter(status=PartRequest.Status.ORDERED).count(),
                "label": "Ordered",
            },
            {
                "value": PartRequest.objects.filter(status=PartRequest.Status.RECEIVED).count(),
                "label": "Received",
            },
        ]

        context.update(
            {
                "page_obj": page_obj,
                "part_requests": page_obj.object_list,
                "search_form": SearchForm(initial={"q": search_query}),
                "stats": stats,
            }
        )
        return context


class PartRequestListPartialView(CanAccessMaintainerPortalMixin, InfiniteScrollMixin, View):
    """AJAX endpoint for infinite scrolling in the part request list."""

    item_template = "parts/partials/part_list_entry.html"

    def get_queryset(self):
        search_query = self.request.GET.get("q", "").strip()
        return (
            PartRequest.objects.search(search_query)
            .select_related("requested_by__user", "machine", "machine__model")
            .prefetch_related("media", _latest_update_prefetch())
            .order_by("-occurred_at")
        )


class PartRequestCreateView(
    FormPrefillMixin, SharedAccountMixin, CanAccessMaintainerPortalMixin, FormView
):
    """Create a new part request."""

    template_name = "parts/part_request_new.html"
    form_class = PartRequestForm

    def dispatch(self, request, *args, **kwargs):
        self.machine = None
        if "slug" in kwargs:
            self.machine = get_object_or_404(MachineInstance, slug=kwargs["slug"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["machine"] = self.machine
        context["is_edit"] = False
        selected_slug = (
            self.request.POST.get("machine_slug") if self.request.method == "POST" else ""
        )
        if selected_slug and not self.machine:
            context["selected_machine"] = MachineInstance.objects.filter(slug=selected_slug).first()
        elif self.machine:
            context["selected_machine"] = self.machine
        return context

    def get_initial(self):
        initial = super().get_initial()
        if self.machine:
            initial["machine_slug"] = self.machine.slug

        # Pre-fill requester_name with current user's display name (for non-shared accounts)
        if not self.is_shared_account and hasattr(self.request.user, "maintainer"):
            initial["requester_name"] = str(self.request.user.maintainer)
        return initial

    @transaction.atomic
    def form_valid(self, form):
        machine = self.machine
        if not machine:
            slug = (form.cleaned_data.get("machine_slug") or "").strip()
            if slug:
                machine = MachineInstance.objects.filter(slug=slug).first()

        # Resolve requester attribution
        current_maintainer = get_object_or_404(Maintainer, user=self.request.user)
        attribution = resolve_maintainer_for_create(
            self.request,
            current_maintainer,
            form,
            username_field="requester_name_username",
            text_field="requester_name",
        )
        if not attribution:
            return self.form_invalid(form)

        part_request = form.save(commit=False)
        part_request.requested_by = attribution.maintainer
        part_request.requested_by_name = attribution.freetext_name
        part_request.machine = machine
        occurred_at = apply_browser_timezone(form.cleaned_data.get("occurred_at"), self.request)

        # Validate after timezone conversion (form validation runs before conversion)
        if not validate_not_future(occurred_at, form):
            return self.form_invalid(form)

        part_request.occurred_at = occurred_at
        part_request.save()
        sync_references(part_request, part_request.text)

        # Handle media uploads
        media_files = form.cleaned_data.get("media_file", [])
        if media_files:
            attach_media_files(
                media_files=media_files, parent=part_request, media_model=PartRequestMedia
            )

        messages.success(
            self.request,
            format_html(
                'Part request <a href="{}">#{}</a> created.',
                reverse("part-request-detail", kwargs={"pk": part_request.pk}),
                part_request.pk,
            ),
        )
        return redirect("part-request-detail", pk=part_request.pk)


class PartRequestDetailView(CanAccessMaintainerPortalMixin, MediaUploadMixin, View):
    """Detail view for a part request. Maintainer-only access."""

    template_name = "parts/part_request_detail.html"

    def get_media_model(self):
        return PartRequestMedia

    def get_media_parent(self):
        return self.part_request

    def get(self, request, *args, **kwargs):
        self.part_request = get_object_or_404(
            PartRequest.objects.select_related(
                "requested_by__user", "machine", "machine__model"
            ).prefetch_related("media"),
            pk=kwargs["pk"],
        )
        return self.render_response(request, self.part_request)

    def post(self, request, *args, **kwargs):
        self.part_request = get_object_or_404(
            PartRequest.objects.select_related(
                "requested_by__user", "machine", "machine__model"
            ).prefetch_related("media"),
            pk=kwargs["pk"],
        )
        action = request.POST.get("action")

        # Handle AJAX text update
        if action == "update_text":
            text = request.POST.get("text", "")
            try:
                save_inline_markdown_field(self.part_request, "text", text)
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

    def render_response(self, request, part_request):
        from django.shortcuts import render

        # Get updates for this part request with pagination
        search_query = request.GET.get("q", "").strip()
        updates = (
            PartRequestUpdate.objects.filter(part_request=part_request)
            .search_for_part_request(search_query)
            .select_related("posted_by__user")
            .prefetch_related("media")
            .order_by("-occurred_at")
        )

        paginator = Paginator(updates, settings.LIST_PAGE_SIZE)
        page_obj = paginator.get_page(request.GET.get("page"))

        context = {
            "part_request": part_request,
            "machine": part_request.machine,
            "page_obj": page_obj,
            "updates": page_obj.object_list,
            "update_count": paginator.count,
            "search_query": search_query,
        }
        return render(request, self.template_name, context)


class PartRequestEditView(CanAccessMaintainerPortalMixin, UpdateView):
    """Edit a part request's metadata (requester, timestamp)."""

    model = PartRequest
    form_class = PartRequestEditForm
    template_name = "parts/part_request_edit.html"

    def get_queryset(self):
        return PartRequest.objects.select_related(
            "requested_by__user",
            "machine",
            "machine__model",
        )

    def get_initial(self):
        initial = super().get_initial()
        # Pre-fill requester_name with current requester's display name
        if self.object.requested_by:
            initial["requester_name"] = str(self.object.requested_by)
        elif self.object.requested_by_name:
            initial["requester_name"] = self.object.requested_by_name
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["part_request"] = self.object
        return context

    def form_valid(self, form):
        # Resolve requester attribution
        attribution = resolve_maintainer_for_edit(
            self.request,
            form,
            username_field="requester_name_username",
            text_field="requester_name",
            error_message="Please enter a requester name.",
        )
        if not attribution:
            return self.form_invalid(form)

        part_request = form.save(commit=False)
        part_request.requested_by = attribution.maintainer
        part_request.requested_by_name = attribution.freetext_name

        # Apply browser timezone to occurred_at
        occurred_at = apply_browser_timezone(form.cleaned_data.get("occurred_at"), self.request)

        # Validate after timezone conversion (form validation runs before conversion)
        if not validate_not_future(occurred_at, form):
            return self.form_invalid(form)

        part_request.occurred_at = occurred_at
        part_request.save()

        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("part-request-detail", kwargs={"pk": self.object.pk})


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
            attach_media_files(
                media_files=media_files, parent=update, media_model=PartRequestUpdateMedia
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


class PartRequestUpdatesPartialView(CanAccessMaintainerPortalMixin, InfiniteScrollMixin, View):
    """AJAX endpoint for infinite scrolling updates on a part request detail page."""

    item_template = "parts/partials/part_update_entry.html"

    def get_queryset(self):
        part_request = get_object_or_404(PartRequest, pk=self.kwargs["pk"])
        search_query = self.request.GET.get("q", "").strip()
        return (
            PartRequestUpdate.objects.filter(part_request=part_request)
            .search_for_part_request(search_query)
            .select_related("posted_by__user")
            .prefetch_related("media")
            .order_by("-occurred_at")
        )

    def get_item_context(self, item):
        return {"update": item}


class PartRequestStatusUpdateView(CanAccessMaintainerPortalMixin, View):
    """AJAX-only endpoint to update part request status."""

    def post(self, request, *args, **kwargs):
        self.part_request = get_object_or_404(PartRequest, pk=kwargs["pk"])
        action = request.POST.get("action")

        action_handlers = {
            "update_status": self._handle_update_status,
        }

        if action in action_handlers:
            return action_handlers[action](request)

        return JsonResponse({"success": False, "error": f"Unknown action: {action}"}, status=400)

    # -- Action handlers -------------------------------------------------------

    def _handle_update_status(self, request):
        """AJAX: change status, creating an audit trail record."""
        new_status = request.POST.get("status")
        if new_status not in PartRequest.Status.values:
            return JsonResponse({"success": False, "error": "Invalid status"}, status=400)

        if self.part_request.status == new_status:
            return JsonResponse({"success": True, "status": "noop"})

        # Get old status display before change
        old_display = self.part_request.get_status_display()
        new_display = PartRequest.Status(new_status).label

        # Get the maintainer for the current user
        maintainer = get_object_or_404(Maintainer, user=request.user)

        # Create an update that will cascade the status change
        update = PartRequestUpdate.objects.create(
            part_request=self.part_request,
            posted_by=maintainer,
            text=f"Status changed: {old_display} → {new_display}",
            new_status=new_status,
        )

        # Render the new update entry for injection into the page
        update_html = render_to_string(
            "parts/partials/part_update_entry.html",
            {"update": update},
        )

        return JsonResponse(
            {
                "success": True,
                "status": "success",
                "new_status": new_status,
                "new_status_display": new_display,
                "update_html": update_html,
            }
        )


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
        from django.shortcuts import render

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
