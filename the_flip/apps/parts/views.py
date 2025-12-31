"""Views for parts management."""

from __future__ import annotations

from functools import partial

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import format_html
from django.views.generic import FormView, TemplateView, UpdateView, View

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.core.datetime import apply_browser_timezone
from the_flip.apps.core.media import is_video_file
from the_flip.apps.core.mixins import (
    CanAccessMaintainerPortalMixin,
    InfiniteScrollMixin,
    MediaUploadMixin,
)
from the_flip.apps.core.tasks import enqueue_transcode
from the_flip.apps.maintenance.forms import SearchForm
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


def get_part_request_queryset(search_query: str = ""):
    """Build the queryset for part request lists.

    Used by both the main list view and the infinite scroll partial view
    to ensure consistent filtering, prefetching, and ordering.
    """
    latest_update_prefetch = Prefetch(
        "updates",
        queryset=PartRequestUpdate.objects.order_by("-occurred_at"),
        to_attr="prefetched_updates",
    )
    queryset = (
        PartRequest.objects.all()
        .select_related("requested_by__user", "machine", "machine__model")
        .prefetch_related("media", latest_update_prefetch)
        .order_by("-occurred_at")
    )

    if search_query:
        queryset = queryset.filter(
            Q(text__icontains=search_query)
            | Q(status__icontains=search_query)
            | Q(machine__model__name__icontains=search_query)
            | Q(machine__name__icontains=search_query)
            | Q(requested_by__user__first_name__icontains=search_query)
            | Q(requested_by__user__last_name__icontains=search_query)
            | Q(requested_by_name__icontains=search_query)
            | Q(updates__text__icontains=search_query)
            | Q(updates__posted_by_name__icontains=search_query)
        ).distinct()

    return queryset


class PartRequestListView(CanAccessMaintainerPortalMixin, TemplateView):
    """List of all part requests. Maintainer-only access."""

    template_name = "parts/part_request_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        search_query = self.request.GET.get("q", "").strip()
        parts = get_part_request_queryset(search_query)

        paginator = Paginator(parts, 10)
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
        return get_part_request_queryset(search_query)


class PartRequestCreateView(CanAccessMaintainerPortalMixin, FormView):
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

        # Check if current user is on a shared/terminal account
        is_shared_account = False
        if hasattr(self.request.user, "maintainer"):
            is_shared_account = self.request.user.maintainer.is_shared_account
        context["is_shared_account"] = is_shared_account
        return context

    def get_initial(self):
        initial = super().get_initial()
        if self.machine:
            initial["machine_slug"] = self.machine.slug

        # Pre-fill requester_name with current user's display name (for non-shared accounts)
        if hasattr(self.request.user, "maintainer"):
            if not self.request.user.maintainer.is_shared_account:
                initial["requester_name"] = str(self.request.user.maintainer)
        return initial

    @transaction.atomic
    def form_valid(self, form):
        machine = self.machine
        if not machine:
            slug = (form.cleaned_data.get("machine_slug") or "").strip()
            if slug:
                machine = MachineInstance.objects.filter(slug=slug).first()

        # Determine the requester from hidden username field or text input
        current_maintainer = get_object_or_404(Maintainer, user=self.request.user)
        requester_username = self.request.POST.get("requester_name_username", "").strip()
        requester_name_text = form.cleaned_data.get("requester_name", "").strip()

        maintainer = None
        requester_name = ""

        if current_maintainer.is_shared_account:
            # For shared accounts: try username lookup first, then fall back to text
            if requester_username:
                maintainer = Maintainer.objects.filter(
                    user__username__iexact=requester_username,
                    is_shared_account=False,
                ).first()
            if not maintainer and requester_name_text:
                # No valid username selected, but text was entered - use text field
                requester_name = requester_name_text
            if not maintainer and not requester_name:
                form.add_error("requester_name", "Please enter your name.")
                return self.form_invalid(form)
        else:
            # For non-shared accounts, use selected user or fall back to current user
            maintainer = current_maintainer
            if requester_username:
                matched = Maintainer.objects.filter(
                    user__username__iexact=requester_username,
                    is_shared_account=False,
                ).first()
                if matched:
                    maintainer = matched

        part_request = form.save(commit=False)
        part_request.requested_by = maintainer
        part_request.requested_by_name = requester_name
        part_request.machine = machine
        part_request.occurred_at = apply_browser_timezone(
            form.cleaned_data.get("occurred_at"), self.request
        )
        part_request.save()

        # Handle media uploads
        media_files = form.cleaned_data.get("media_file", [])
        if media_files:
            for media_file in media_files:
                is_video = is_video_file(media_file)

                media = PartRequestMedia.objects.create(
                    part_request=part_request,
                    media_type=PartRequestMedia.MediaType.VIDEO
                    if is_video
                    else PartRequestMedia.MediaType.PHOTO,
                    file=media_file,
                    transcode_status=PartRequestMedia.TranscodeStatus.PENDING if is_video else "",
                )

                if is_video:
                    transaction.on_commit(
                        partial(
                            enqueue_transcode,
                            media_id=media.id,
                            model_name="PartRequestMedia",
                        )
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
            self.part_request.text = request.POST.get("text", "")
            self.part_request.save(update_fields=["text", "updated_at"])
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
        updates = (
            PartRequestUpdate.objects.filter(part_request=part_request)
            .select_related("posted_by__user")
            .prefetch_related("media")
            .order_by("-occurred_at")
        )

        search_query = request.GET.get("q", "").strip()
        if search_query:
            updates = updates.filter(
                Q(text__icontains=search_query) | Q(posted_by_name__icontains=search_query)
            ).distinct()

        paginator = Paginator(updates, 10)
        page_obj = paginator.get_page(request.GET.get("page"))

        context = {
            "part_request": part_request,
            "machine": part_request.machine,
            "page_obj": page_obj,
            "updates": page_obj.object_list,
            "search_form": SearchForm(initial={"q": search_query}),
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
        # Handle requester attribution from hidden username field or text input
        requester_username = self.request.POST.get("requester_name_username", "").strip()
        requester_name_text = form.cleaned_data.get("requester_name", "").strip()

        maintainer = None
        requester_name = ""

        if requester_username:
            maintainer = Maintainer.objects.filter(
                user__username__iexact=requester_username,
                is_shared_account=False,
            ).first()

        if not maintainer and requester_name_text:
            # No valid username selected, but text was entered - use text field
            requester_name = requester_name_text

        part_request = form.save(commit=False)
        part_request.requested_by = maintainer
        part_request.requested_by_name = requester_name
        part_request.occurred_at = apply_browser_timezone(
            form.cleaned_data.get("occurred_at"), self.request
        )
        part_request.save()

        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("part-request-detail", kwargs={"pk": self.object.pk})


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

        # Pre-fill requester_name with current user's display name (for non-shared accounts)
        if hasattr(self.request.user, "maintainer"):
            if not self.request.user.maintainer.is_shared_account:
                initial["requester_name"] = str(self.request.user.maintainer)
        return initial

    @transaction.atomic
    def form_valid(self, form):
        # Determine the poster from hidden username field or text input
        current_maintainer = get_object_or_404(Maintainer, user=self.request.user)
        requester_username = self.request.POST.get("requester_name_username", "").strip()
        requester_name_text = form.cleaned_data.get("requester_name", "").strip()

        maintainer = None
        poster_name = ""

        if current_maintainer.is_shared_account:
            # For shared accounts: try username lookup first, then fall back to text
            if requester_username:
                maintainer = Maintainer.objects.filter(
                    user__username__iexact=requester_username,
                    is_shared_account=False,
                ).first()
            if not maintainer and requester_name_text:
                # No valid username selected, but text was entered - use text field
                poster_name = requester_name_text
            if not maintainer and not poster_name:
                form.add_error("requester_name", "Please enter your name.")
                return self.form_invalid(form)
        else:
            # For non-shared accounts, use selected user or fall back to current user
            maintainer = current_maintainer
            if requester_username:
                matched = Maintainer.objects.filter(
                    user__username__iexact=requester_username,
                    is_shared_account=False,
                ).first()
                if matched:
                    maintainer = matched

        update = form.save(commit=False)
        update.part_request = self.part_request
        update.posted_by = maintainer
        update.posted_by_name = poster_name
        update.occurred_at = apply_browser_timezone(
            form.cleaned_data.get("occurred_at"), self.request
        )
        update.save()

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


class PartRequestUpdatesPartialView(CanAccessMaintainerPortalMixin, View):
    """AJAX endpoint for infinite scrolling updates on a part request detail page."""

    template_name = "parts/partials/part_update_entry.html"

    def get(self, request, *args, **kwargs):
        part_request = get_object_or_404(PartRequest, pk=kwargs["pk"])
        updates = (
            PartRequestUpdate.objects.filter(part_request=part_request)
            .select_related("posted_by__user")
            .prefetch_related("media")
            .order_by("-occurred_at")
        )

        search_query = request.GET.get("q", "").strip()
        if search_query:
            updates = updates.filter(
                Q(text__icontains=search_query) | Q(posted_by_name__icontains=search_query)
            ).distinct()

        paginator = Paginator(updates, 10)
        page_obj = paginator.get_page(request.GET.get("page"))
        items_html = "".join(
            render_to_string(self.template_name, {"update": update})
            for update in page_obj.object_list
        )
        return JsonResponse(
            {
                "items": items_html,
                "has_next": page_obj.has_next(),
                "next_page": page_obj.next_page_number() if page_obj.has_next() else None,
            }
        )


class PartRequestStatusUpdateView(CanAccessMaintainerPortalMixin, View):
    """AJAX-only endpoint to update part request status."""

    def post(self, request, *args, **kwargs):
        part_request = get_object_or_404(PartRequest, pk=kwargs["pk"])
        action = request.POST.get("action")

        if action == "update_status":
            new_status = request.POST.get("status")
            if new_status not in PartRequest.Status.values:
                return JsonResponse({"error": "Invalid status"}, status=400)

            if part_request.status == new_status:
                return JsonResponse({"status": "noop"})

            # Get old status display before change
            old_display = part_request.get_status_display()
            new_display = PartRequest.Status(new_status).label

            # Get the maintainer for the current user
            maintainer = get_object_or_404(Maintainer, user=request.user)

            # Create an update that will cascade the status change
            update = PartRequestUpdate.objects.create(
                part_request=part_request,
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
                    "status": "success",
                    "new_status": new_status,
                    "new_status_display": new_display,
                    "update_html": update_html,
                }
            )

        return JsonResponse({"error": "Unknown action"}, status=400)


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
            self.update.text = request.POST.get("text", "")
            self.update.save(update_fields=["text", "updated_at"])
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
        # Handle poster attribution from hidden username field or text input
        poster_username = self.request.POST.get("poster_name_username", "").strip()
        poster_name_text = form.cleaned_data.get("poster_name", "").strip()

        maintainer = None
        poster_name = ""

        if poster_username:
            maintainer = Maintainer.objects.filter(
                user__username__iexact=poster_username,
                is_shared_account=False,
            ).first()

        if not maintainer and poster_name_text:
            # No valid username selected, but text was entered - use text field
            poster_name = poster_name_text

        update = form.save(commit=False)
        update.posted_by = maintainer
        update.posted_by_name = poster_name
        update.occurred_at = apply_browser_timezone(
            form.cleaned_data.get("occurred_at"), self.request
        )
        update.save()

        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("part-request-update-detail", kwargs={"pk": self.object.pk})
