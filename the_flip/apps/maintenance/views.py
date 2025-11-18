from __future__ import annotations

import base64
from io import BytesIO

import qrcode
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import format_html
from django.views.generic import ListView, TemplateView, FormView, View, DetailView, UpdateView

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.maintenance.forms import LogEntryQuickForm, MachineReportSearchForm, ProblemReportForm
from the_flip.apps.maintenance.models import LogEntry, LogEntryMedia, ProblemReport


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

    def form_valid(self, form):
        report = form.save(commit=False)
        report.machine = self.machine
        report.ip_address = self.request.META.get("REMOTE_ADDR")
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
        photo = form.cleaned_data["photo"]
        log_entry = LogEntry.objects.create(machine=self.machine, text=description)

        maintainer = self.match_maintainer(submitter_name)
        if maintainer:
            log_entry.maintainers.add(maintainer)
        elif submitter_name:
            log_entry.maintainer_names = submitter_name
            log_entry.save(update_fields=["maintainer_names"])

        if photo:
            LogEntryMedia.objects.create(
                log_entry=log_entry,
                media_type=LogEntryMedia.TYPE_PHOTO,
                file=photo,
            )

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
                media = LogEntryMedia.objects.create(
                    log_entry=self.object,
                    media_type=LogEntryMedia.TYPE_PHOTO,
                    file=request.FILES["file"],
                )
                return JsonResponse({
                    "success": True,
                    "media_id": media.id,
                    "media_url": media.file.url,
                })
            return JsonResponse({"success": False, "error": "No file provided"}, status=400)

        elif action == "delete_media":
            media_id = request.POST.get("media_id")
            try:
                media = LogEntryMedia.objects.get(id=media_id, log_entry=self.object)
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

        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(public_url)
        qr.make(fit=True)

        # Create image
        img = qr.make_image(fill_color="black", back_color="white")

        # Convert to base64 for inline display
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        qr_code_data = base64.b64encode(buffer.getvalue()).decode()

        context["qr_code_data"] = qr_code_data
        context["public_url"] = public_url

        return context
