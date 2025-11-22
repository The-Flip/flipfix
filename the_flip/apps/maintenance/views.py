from __future__ import annotations

import base64
from datetime import timedelta
from io import BytesIO
from pathlib import Path

import qrcode
from PIL import Image
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.views.generic import ListView, TemplateView, FormView, View, DetailView, UpdateView

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.maintenance.forms import LogEntryQuickForm, MachineReportSearchForm, ProblemReportForm
from the_flip.apps.maintenance.models import LogEntry, LogEntryMedia, ProblemReport
from the_flip.apps.maintenance.tasks import enqueue_transcode


class ProblemReportListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """Global list of all problem reports across all machines. Maintainer-only access."""
    template_name = "maintenance/problem_report_list.html"
    context_object_name = "reports"
    queryset = ProblemReport.objects.select_related("machine").order_by("-status", "-created_at")

    def test_func(self):
        return self.request.user.is_staff


class MachineProblemReportListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """Paginated list of all problem reports for a specific machine."""
    template_name = "maintenance/machine_problem_report_list.html"
    context_object_name = "reports"
    paginate_by = 10

    def test_func(self):
        return self.request.user.is_staff

    def dispatch(self, request, *args, **kwargs):
        self.machine = get_object_or_404(MachineInstance, slug=kwargs["slug"])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        queryset = ProblemReport.objects.filter(machine=self.machine).select_related(
            "reported_by_user"
        ).order_by("-status", "-created_at")

        # Search by description text if provided
        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            queryset = queryset.filter(description__icontains=search_query)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["machine"] = self.machine
        search_query = self.request.GET.get("q", "")
        context["search_form"] = MachineReportSearchForm(initial={"q": search_query})
        return context


class ProblemReportCreateView(FormView):
    template_name = "maintenance/problem_report_form.html"
    form_class = ProblemReportForm

    def dispatch(self, request, *args, **kwargs):
        self.machine = get_object_or_404(MachineInstance, slug=kwargs["slug"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["machine"] = self.machine
        return context

    def post(self, request, *args, **kwargs):
        """Override post to check rate limiting before processing form."""
        # Check rate limiting
        ip_address = request.META.get("REMOTE_ADDR")
        if ip_address and not self._check_rate_limit(ip_address):
            messages.error(
                request,
                "Too many reports submitted recently. Please try again later."
            )
            return redirect(self.machine.get_absolute_url())

        return super().post(request, *args, **kwargs)

    def _check_rate_limit(self, ip_address: str) -> bool:
        """Check if IP address has exceeded rate limit. Returns True if OK to proceed."""
        time_window = timezone.now() - timedelta(minutes=settings.RATE_LIMIT_WINDOW_MINUTES)
        recent_reports = ProblemReport.objects.filter(
            ip_address=ip_address,
            created_at__gte=time_window
        ).count()
        return recent_reports < settings.RATE_LIMIT_REPORTS_PER_IP

    def form_valid(self, form):
        report = form.save(commit=False)
        report.machine = self.machine
        report.ip_address = self.request.META.get("REMOTE_ADDR")
        report.device_info = self.request.META.get("HTTP_USER_AGENT", "")[:200]  # Truncate to field max length
        if self.request.user.is_authenticated:
            report.reported_by_user = self.request.user
        report.save()
        messages.success(self.request, "Thanks! The maintenance team has been notified.")
        return redirect(self.machine.get_absolute_url())


class ProblemReportDetailView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Detail view for a problem report with status toggle capability. Maintainer-only access."""
    template_name = "maintenance/problem_report_detail.html"

    def test_func(self):
        return self.request.user.is_staff

    def get(self, request, *args, **kwargs):
        report = get_object_or_404(
            ProblemReport.objects.select_related("machine", "reported_by_user"),
            pk=kwargs["pk"]
        )
        return self.render_response(request, report)

    def post(self, request, *args, **kwargs):
        report = get_object_or_404(
            ProblemReport.objects.select_related("machine", "reported_by_user"),
            pk=kwargs["pk"]
        )
        # Toggle status
        if report.status == ProblemReport.STATUS_OPEN:
            report.status = ProblemReport.STATUS_CLOSED
            message = "Problem report closed."
        else:
            report.status = ProblemReport.STATUS_OPEN
            message = "Problem report re-opened."

        report.save(update_fields=["status", "updated_at"])
        messages.success(request, message)
        return redirect("problem-report-detail", pk=report.pk)

    def render_response(self, request, report):
        from django.shortcuts import render
        context = {
            "report": report,
            "machine": report.machine,
        }
        return render(request, self.template_name, context)


class MachineLogView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = "maintenance/machine_log.html"

    def test_func(self):
        return self.request.user.is_staff

    def dispatch(self, request, *args, **kwargs):
        self.machine = get_object_or_404(MachineInstance, slug=kwargs["slug"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        logs = (
            LogEntry.objects.filter(machine=self.machine)
            .select_related("machine")
            .prefetch_related("maintainers", "media")
            .order_by("-created_at")
        )
        paginator = Paginator(logs, 10)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        context.update(
            {
                "machine": self.machine,
                "page_obj": page_obj,
                "log_entries": page_obj.object_list,
            }
        )
        return context


class MachineLogCreateView(LoginRequiredMixin, UserPassesTestMixin, FormView):
    template_name = "maintenance/machine_log_new.html"
    form_class = LogEntryQuickForm

    def test_func(self):
        return self.request.user.is_staff

    def dispatch(self, request, *args, **kwargs):
        self.machine = get_object_or_404(MachineInstance, slug=kwargs["slug"])
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        if self.request.user.is_authenticated:
            initial["submitter_name"] = (
                self.request.user.get_full_name() or self.request.user.get_username()
            )
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["machine"] = self.machine
        return context

    def form_valid(self, form):
        submitter_name = form.cleaned_data["submitter_name"].strip()
        description = form.cleaned_data["text"].strip()
        media_file = form.cleaned_data["media"]
        log_entry = LogEntry.objects.create(machine=self.machine, text=description)

        maintainer = self.match_maintainer(submitter_name)
        if maintainer:
            log_entry.maintainers.add(maintainer)
        elif submitter_name:
            log_entry.maintainer_names = submitter_name
            log_entry.save(update_fields=["maintainer_names"])

        if media_file:
            content_type = (getattr(media_file, "content_type", "") or "").lower()
            ext = Path(getattr(media_file, "name", "")).suffix.lower()
            is_video = content_type.startswith("video/") or ext in {".mp4", ".mov", ".m4v", ".hevc"}

            media = LogEntryMedia.objects.create(
                log_entry=log_entry,
                media_type=LogEntryMedia.TYPE_VIDEO if is_video else LogEntryMedia.TYPE_PHOTO,
                file=media_file,
                transcode_status=LogEntryMedia.STATUS_PENDING if is_video else "",
            )

            if is_video:
                enqueue_transcode(media.id)

        messages.success(
            self.request,
            format_html(
                'Log entry added. Edit it <a href="{}">here</a>.',
                reverse('log-detail', kwargs={'pk': log_entry.pk})
            )
        )
        return redirect("log-machine", slug=self.machine.slug)

    def match_maintainer(self, name: str):
        normalized = name.lower().strip()
        if not normalized:
            return None
        for maintainer in Maintainer.objects.select_related("user"):
            username = maintainer.user.username.lower()
            full_name = (maintainer.user.get_full_name() or "").lower()
            if normalized in {username, full_name}:
                return maintainer
        return None


class MachineLogPartialView(LoginRequiredMixin, UserPassesTestMixin, View):
    template_name = "maintenance/partials/log_entry.html"

    def test_func(self):
        return self.request.user.is_staff

    def get(self, request, *args, **kwargs):
        machine = get_object_or_404(MachineInstance, slug=kwargs["slug"])
        logs = (
            LogEntry.objects.filter(machine=machine)
            .select_related("machine")
            .prefetch_related("maintainers", "media")
            .order_by("-created_at")
        )
        paginator = Paginator(logs, 10)
        page_obj = paginator.get_page(request.GET.get("page"))
        items_html = "".join(
            render_to_string(self.template_name, {"entry": entry, "machine": machine})
            for entry in page_obj.object_list
        )
        return JsonResponse(
            {
                "items": items_html,
                "has_next": page_obj.has_next(),
                "next_page": page_obj.next_page_number() if page_obj.has_next() else None,
            }
        )


class LogListView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Global list of all log entries across all machines. Maintainer-only access."""
    template_name = "maintenance/log_list.html"

    def test_func(self):
        return self.request.user.is_staff

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        logs = (
            LogEntry.objects.all()
            .select_related("machine")
            .prefetch_related("maintainers", "media")
            .order_by("-created_at")
        )
        paginator = Paginator(logs, 10)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        context.update(
            {
                "page_obj": page_obj,
                "log_entries": page_obj.object_list,
            }
        )
        return context


class LogListPartialView(LoginRequiredMixin, UserPassesTestMixin, View):
    """AJAX endpoint for infinite scrolling in the global log list."""
    template_name = "maintenance/partials/log_list_entry.html"

    def test_func(self):
        return self.request.user.is_staff

    def get(self, request, *args, **kwargs):
        logs = (
            LogEntry.objects.all()
            .select_related("machine")
            .prefetch_related("maintainers", "media")
            .order_by("-created_at")
        )
        paginator = Paginator(logs, 10)
        page_obj = paginator.get_page(request.GET.get("page"))
        items_html = "".join(
            render_to_string(
                self.template_name,
                {"entry": entry, "machine": entry.machine}
            )
            for entry in page_obj.object_list
        )
        return JsonResponse(
            {
                "items": items_html,
                "has_next": page_obj.has_next(),
                "next_page": page_obj.next_page_number() if page_obj.has_next() else None,
            }
        )


class LogEntryDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = LogEntry
    template_name = "maintenance/log_entry_detail.html"
    context_object_name = "entry"

    def test_func(self):
        return self.request.user.is_staff

    def get_queryset(self):
        return LogEntry.objects.select_related("machine").prefetch_related("maintainers", "media")

    def post(self, request, *args, **kwargs):
        """Handle AJAX updates to the log entry."""
        self.object = self.get_object()
        action = request.POST.get("action")

        if action == "update_text":
            self.object.text = request.POST.get("text", "")
            self.object.save(update_fields=["text", "updated_at"])
            return JsonResponse({"success": True})

        elif action == "upload_media":
            if "file" in request.FILES:
                upload = request.FILES["file"]
                content_type = (getattr(upload, "content_type", "") or "").lower()
                ext = Path(getattr(upload, "name", "")).suffix.lower()
                is_video = content_type.startswith("video/") or ext in {".mp4", ".mov", ".m4v", ".hevc"}
                media = LogEntryMedia.objects.create(
                    log_entry=self.object,
                    media_type=LogEntryMedia.TYPE_VIDEO if is_video else LogEntryMedia.TYPE_PHOTO,
                    file=upload,
                    transcode_status=LogEntryMedia.STATUS_PENDING if is_video else "",
                )
                if is_video:
                    enqueue_transcode(media.id)
                return JsonResponse({
                    "success": True,
                    "media_id": media.id,
                    "media_url": media.transcoded_file.url if media.transcoded_file else media.file.url,
                    "media_type": media.media_type,
                    "transcode_status": media.transcode_status,
                    "poster_url": media.poster_file.url if media.poster_file else None,
                })
            return JsonResponse({"success": False, "error": "No file provided"}, status=400)

        elif action == "delete_media":
            media_id = request.POST.get("media_id")
            try:
                media = LogEntryMedia.objects.get(id=media_id, log_entry=self.object)
                if media.transcoded_file:
                    media.transcoded_file.delete(save=False)
                if media.poster_file:
                    media.poster_file.delete(save=False)
                media.file.delete()
                media.delete()
                return JsonResponse({"success": True})
            except LogEntryMedia.DoesNotExist:
                return JsonResponse({"success": False, "error": "Media not found"}, status=404)

        return JsonResponse({"success": False, "error": "Invalid action"}, status=400)


class MachineQRView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """Generate and display a printable QR code for a machine's public info page."""
    model = MachineInstance
    template_name = "maintenance/machine_qr.html"
    context_object_name = "machine"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def test_func(self):
        return self.request.user.is_staff

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        machine = self.object

        # Build the absolute URL for the public machine detail page
        public_url = self.request.build_absolute_uri(
            reverse("public-machine-detail", args=[machine.slug])
        )

        # Generate QR code with high error correction for logo embedding
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,  # High error correction (30%)
            box_size=10,
            border=4,
        )
        qr.add_data(public_url)
        qr.make(fit=True)

        # Create QR code image and convert to RGB for logo overlay
        qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

        # Add logo to center of QR code
        logo_path = Path(__file__).resolve().parent.parent.parent / "static/core/images/the_flip_logo.png"
        if logo_path.exists():
            logo = Image.open(logo_path)

            # Calculate logo size (20% of QR code size for safe scanning)
            qr_width, qr_height = qr_img.size
            logo_size = int(qr_width * 0.20)

            # Resize logo maintaining aspect ratio
            logo.thumbnail((logo_size, logo_size), Image.LANCZOS)

            # Add white background/padding to logo for better contrast
            padding = 10
            logo_with_bg = Image.new("RGB", (logo.size[0] + padding * 2, logo.size[1] + padding * 2), "white")
            logo_pos = (padding, padding)
            logo_with_bg.paste(logo, logo_pos, logo if logo.mode == "RGBA" else None)

            # Calculate center position and paste logo
            logo_position = ((qr_width - logo_with_bg.size[0]) // 2, (qr_height - logo_with_bg.size[1]) // 2)
            qr_img.paste(logo_with_bg, logo_position)

        # Convert to base64 for inline display
        buffer = BytesIO()
        qr_img.save(buffer, format="PNG")
        qr_code_data = base64.b64encode(buffer.getvalue()).decode()

        context["qr_code_data"] = qr_code_data
        context["public_url"] = public_url

        return context
