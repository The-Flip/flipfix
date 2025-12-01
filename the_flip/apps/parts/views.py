"""Views for parts management."""

from __future__ import annotations

from pathlib import Path

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import format_html
from django.views.generic import FormView, TemplateView, View

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.maintenance.forms import SearchForm
from the_flip.apps.maintenance.tasks import enqueue_transcode
from the_flip.apps.parts.forms import PartRequestForm, PartRequestUpdateForm
from the_flip.apps.parts.models import (
    PartRequest,
    PartRequestMedia,
    PartRequestUpdate,
    PartRequestUpdateMedia,
)


class PartRequestListView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """List of all part requests. Maintainer-only access."""

    template_name = "parts/part_list.html"

    def test_func(self):
        return self.request.user.is_staff

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        parts = (
            PartRequest.objects.all()
            .select_related("requested_by__user", "machine", "machine__model")
            .prefetch_related("media")
            .order_by("-created_at")
        )

        # Filter by status
        status_filter = self.request.GET.get("status", "").strip()
        if status_filter:
            parts = parts.filter(status=status_filter)

        # Search
        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            parts = parts.filter(
                Q(text__icontains=search_query)
                | Q(machine__model__name__icontains=search_query)
                | Q(machine__name_override__icontains=search_query)
                | Q(requested_by__user__first_name__icontains=search_query)
                | Q(requested_by__user__last_name__icontains=search_query)
                | Q(updates__text__icontains=search_query)
            ).distinct()

        paginator = Paginator(parts, 10)
        page_obj = paginator.get_page(self.request.GET.get("page"))

        # Stats for sidebar
        requested_count = PartRequest.objects.filter(status=PartRequest.STATUS_REQUESTED).count()
        ordered_count = PartRequest.objects.filter(status=PartRequest.STATUS_ORDERED).count()
        received_count = PartRequest.objects.filter(status=PartRequest.STATUS_RECEIVED).count()

        context.update(
            {
                "page_obj": page_obj,
                "part_requests": page_obj.object_list,
                "search_form": SearchForm(initial={"q": search_query}),
                "status_filter": status_filter,
                "requested_count": requested_count,
                "ordered_count": ordered_count,
                "received_count": received_count,
            }
        )
        return context


class PartRequestListPartialView(LoginRequiredMixin, UserPassesTestMixin, View):
    """AJAX endpoint for infinite scrolling in the part request list."""

    template_name = "parts/partials/part_list_entry.html"

    def test_func(self):
        return self.request.user.is_staff

    def get(self, request, *args, **kwargs):
        parts = (
            PartRequest.objects.all()
            .select_related("requested_by__user", "machine", "machine__model")
            .prefetch_related("media")
            .order_by("-created_at")
        )

        status_filter = request.GET.get("status", "").strip()
        if status_filter:
            parts = parts.filter(status=status_filter)

        search_query = request.GET.get("q", "").strip()
        if search_query:
            parts = parts.filter(
                Q(text__icontains=search_query)
                | Q(machine__model__name__icontains=search_query)
                | Q(machine__name_override__icontains=search_query)
                | Q(requested_by__user__first_name__icontains=search_query)
                | Q(requested_by__user__last_name__icontains=search_query)
                | Q(updates__text__icontains=search_query)
            ).distinct()

        paginator = Paginator(parts, 10)
        page_obj = paginator.get_page(request.GET.get("page"))
        items_html = "".join(
            render_to_string(self.template_name, {"entry": part}) for part in page_obj.object_list
        )
        return JsonResponse(
            {
                "items": items_html,
                "has_next": page_obj.has_next(),
                "next_page": page_obj.next_page_number() if page_obj.has_next() else None,
            }
        )


class PartRequestCreateView(LoginRequiredMixin, UserPassesTestMixin, FormView):
    """Create a new part request."""

    template_name = "parts/part_form.html"
    form_class = PartRequestForm

    def test_func(self):
        return self.request.user.is_staff

    def dispatch(self, request, *args, **kwargs):
        self.machine = None
        if "slug" in kwargs:
            self.machine = get_object_or_404(MachineInstance, slug=kwargs["slug"])
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        if self.machine:
            initial["machine_slug"] = self.machine.slug
        return initial

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

    def form_valid(self, form):
        machine = self.machine
        if not machine:
            slug = (form.cleaned_data.get("machine_slug") or "").strip()
            if slug:
                machine = MachineInstance.objects.filter(slug=slug).first()

        # Get the maintainer for the current user
        maintainer = get_object_or_404(Maintainer, user=self.request.user)

        part_request = form.save(commit=False)
        part_request.requested_by = maintainer
        part_request.machine = machine
        part_request.save()

        # Handle media uploads
        media_files = form.cleaned_data.get("media_file", [])
        if media_files:
            for media_file in media_files:
                content_type = (getattr(media_file, "content_type", "") or "").lower()
                ext = Path(getattr(media_file, "name", "")).suffix.lower()
                is_video = content_type.startswith("video/") or ext in {
                    ".mp4",
                    ".mov",
                    ".m4v",
                    ".hevc",
                }

                media = PartRequestMedia.objects.create(
                    part_request=part_request,
                    media_type=PartRequestMedia.TYPE_VIDEO
                    if is_video
                    else PartRequestMedia.TYPE_PHOTO,
                    file=media_file,
                    transcode_status=PartRequestMedia.STATUS_PENDING if is_video else "",
                )

                if is_video:
                    enqueue_transcode(media.id, model_name="PartRequestMedia")

        messages.success(
            self.request,
            format_html(
                'Part request <a href="{}">#{}</a> created.',
                reverse("part-request-detail", kwargs={"pk": part_request.pk}),
                part_request.pk,
            ),
        )
        return redirect("part-request-detail", pk=part_request.pk)


class PartRequestDetailView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Detail view for a part request. Maintainer-only access."""

    template_name = "parts/part_detail.html"

    def test_func(self):
        return self.request.user.is_staff

    def get(self, request, *args, **kwargs):
        part_request = get_object_or_404(
            PartRequest.objects.select_related(
                "requested_by__user", "machine", "machine__model"
            ).prefetch_related("media"),
            pk=kwargs["pk"],
        )
        return self.render_response(request, part_request)

    def post(self, request, *args, **kwargs):
        part_request = get_object_or_404(
            PartRequest.objects.select_related(
                "requested_by__user", "machine", "machine__model"
            ).prefetch_related("media"),
            pk=kwargs["pk"],
        )
        action = request.POST.get("action")

        # Handle AJAX text update
        if action == "update_text":
            part_request.text = request.POST.get("text", "")
            part_request.save(update_fields=["text", "updated_at"])
            return JsonResponse({"success": True})

        # Handle AJAX media upload
        if action == "upload_media":
            if "file" in request.FILES:
                upload = request.FILES["file"]
                content_type = (getattr(upload, "content_type", "") or "").lower()
                ext = Path(getattr(upload, "name", "")).suffix.lower()
                is_video = content_type.startswith("video/") or ext in {
                    ".mp4",
                    ".mov",
                    ".m4v",
                    ".hevc",
                }
                media = PartRequestMedia.objects.create(
                    part_request=part_request,
                    media_type=PartRequestMedia.TYPE_VIDEO
                    if is_video
                    else PartRequestMedia.TYPE_PHOTO,
                    file=upload,
                    transcode_status=PartRequestMedia.STATUS_PENDING if is_video else "",
                )
                if is_video:
                    enqueue_transcode(media.id, model_name="PartRequestMedia")
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
            return JsonResponse({"success": False, "error": "No file provided"}, status=400)

        # Handle AJAX media delete
        if action == "delete_media":
            media_id = request.POST.get("media_id")
            try:
                media = PartRequestMedia.objects.get(id=media_id, part_request=part_request)
                if media.transcoded_file:
                    media.transcoded_file.delete(save=False)
                if media.poster_file:
                    media.poster_file.delete(save=False)
                if media.thumbnail_file:
                    media.thumbnail_file.delete(save=False)
                media.file.delete()
                media.delete()
                return JsonResponse({"success": True})
            except PartRequestMedia.DoesNotExist:
                return JsonResponse({"success": False, "error": "Media not found"}, status=404)

        return JsonResponse({"success": False, "error": "Invalid action"}, status=400)

    def render_response(self, request, part_request):
        from django.shortcuts import render

        # Get updates for this part request with pagination
        updates = (
            PartRequestUpdate.objects.filter(part_request=part_request)
            .select_related("posted_by__user")
            .prefetch_related("media")
            .order_by("-created_at")
        )

        search_query = request.GET.get("q", "").strip()
        if search_query:
            updates = updates.filter(Q(text__icontains=search_query)).distinct()

        paginator = Paginator(updates, 10)
        page_obj = paginator.get_page(request.GET.get("page"))

        # Form for adding updates
        update_form = PartRequestUpdateForm()

        context = {
            "part_request": part_request,
            "machine": part_request.machine,
            "page_obj": page_obj,
            "updates": page_obj.object_list,
            "search_form": SearchForm(initial={"q": search_query}),
            "update_form": update_form,
        }
        return render(request, self.template_name, context)


class PartRequestUpdateCreateView(LoginRequiredMixin, UserPassesTestMixin, FormView):
    """Add an update/comment to a part request."""

    form_class = PartRequestUpdateForm

    def test_func(self):
        return self.request.user.is_staff

    def dispatch(self, request, *args, **kwargs):
        self.part_request = get_object_or_404(PartRequest, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        maintainer = get_object_or_404(Maintainer, user=self.request.user)

        update = form.save(commit=False)
        update.part_request = self.part_request
        update.posted_by = maintainer
        update.save()

        # Handle media uploads
        media_files = form.cleaned_data.get("media_file", [])
        if media_files:
            for media_file in media_files:
                content_type = (getattr(media_file, "content_type", "") or "").lower()
                ext = Path(getattr(media_file, "name", "")).suffix.lower()
                is_video = content_type.startswith("video/") or ext in {
                    ".mp4",
                    ".mov",
                    ".m4v",
                    ".hevc",
                }

                media = PartRequestUpdateMedia.objects.create(
                    update=update,
                    media_type=PartRequestUpdateMedia.TYPE_VIDEO
                    if is_video
                    else PartRequestUpdateMedia.TYPE_PHOTO,
                    file=media_file,
                    transcode_status=PartRequestUpdateMedia.STATUS_PENDING if is_video else "",
                )

                if is_video:
                    enqueue_transcode(media.id, model_name="PartRequestUpdateMedia")

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
        messages.error(self.request, "Please correct the errors below.")
        return redirect("part-request-detail", pk=self.part_request.pk)


class PartRequestUpdatesPartialView(LoginRequiredMixin, UserPassesTestMixin, View):
    """AJAX endpoint for infinite scrolling updates on a part request detail page."""

    template_name = "parts/partials/part_update_entry.html"

    def test_func(self):
        return self.request.user.is_staff

    def get(self, request, *args, **kwargs):
        part_request = get_object_or_404(PartRequest, pk=kwargs["pk"])
        updates = (
            PartRequestUpdate.objects.filter(part_request=part_request)
            .select_related("posted_by__user")
            .prefetch_related("media")
            .order_by("-created_at")
        )

        search_query = request.GET.get("q", "").strip()
        if search_query:
            updates = updates.filter(Q(text__icontains=search_query)).distinct()

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
