from __future__ import annotations

import base64
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from io import BytesIO
from pathlib import Path

import qrcode
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.db.models import Prefetch, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.views.generic import DetailView, FormView, ListView, TemplateView, View
from PIL import Image, ImageOps

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.maintenance.forms import (
    LogEntryQuickForm,
    ProblemReportForm,
    SearchForm,
)
from the_flip.apps.maintenance.models import LogEntry, LogEntryMedia, ProblemReport
from the_flip.apps.maintenance.tasks import enqueue_transcode


class MaintainerAutocompleteView(LoginRequiredMixin, UserPassesTestMixin, View):
    """JSON endpoint for maintainer name autocomplete."""

    def test_func(self):
        return self.request.user.is_staff

    def get(self, request, *args, **kwargs):
        query = request.GET.get("q", "").strip().lower()
        maintainers = Maintainer.objects.filter(is_shared_account=False).select_related("user")

        results = []
        for m in maintainers:
            display_name = m.display_name
            username = m.user.username
            first_name = (m.user.first_name or "").lower()
            last_name = (m.user.last_name or "").lower()
            # Filter by query (match start of first name, last name, or username)
            if query and not (
                first_name.startswith(query)
                or last_name.startswith(query)
                or username.lower().startswith(query)
            ):
                continue
            results.append(
                {
                    "id": m.id,
                    "display_name": display_name,
                    "username": username,
                    "first_name": m.user.first_name or "",
                    "last_name": m.user.last_name or "",
                }
            )

        # Sort alphabetically by display name
        results.sort(key=lambda x: x["display_name"].lower())
        return JsonResponse({"maintainers": results})


class ProblemReportListView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Global list of all problem reports across all machines. Maintainer-only access."""

    template_name = "maintenance/problem_report_list.html"

    def test_func(self):
        return self.request.user.is_staff

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Prefetch the most recent log entry for each problem report
        latest_log_prefetch = Prefetch(
            "log_entries",
            queryset=LogEntry.objects.order_by("-created_at"),
            to_attr="prefetched_log_entries",
        )
        reports = (
            ProblemReport.objects.select_related("machine", "machine__model")
            .prefetch_related(latest_log_prefetch)
            .order_by("-status", "-created_at")
        )

        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            reports = reports.filter(
                Q(description__icontains=search_query)
                | Q(machine__model__name__icontains=search_query)
                | Q(machine__name_override__icontains=search_query)
            )

        paginator = Paginator(reports, 10)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        context.update(
            {
                "page_obj": page_obj,
                "reports": page_obj.object_list,
                "search_form": SearchForm(initial={"q": search_query}),
            }
        )
        return context


class ProblemReportListPartialView(LoginRequiredMixin, UserPassesTestMixin, View):
    """AJAX endpoint for infinite scrolling in the global problem report list."""

    template_name = "maintenance/partials/problem_report_list_entry.html"

    def test_func(self):
        return self.request.user.is_staff

    def get(self, request, *args, **kwargs):
        # Prefetch the most recent log entry for each problem report
        latest_log_prefetch = Prefetch(
            "log_entries",
            queryset=LogEntry.objects.order_by("-created_at"),
            to_attr="prefetched_log_entries",
        )
        reports = (
            ProblemReport.objects.select_related("machine", "machine__model")
            .prefetch_related(latest_log_prefetch)
            .order_by("-status", "-created_at")
        )

        search_query = request.GET.get("q", "").strip()
        if search_query:
            reports = reports.filter(
                Q(description__icontains=search_query)
                | Q(machine__model__name__icontains=search_query)
                | Q(machine__name_override__icontains=search_query)
            )

        paginator = Paginator(reports, 10)
        page_obj = paginator.get_page(request.GET.get("page"))
        items_html = "".join(
            render_to_string(self.template_name, {"report": report})
            for report in page_obj.object_list
        )
        return JsonResponse(
            {
                "items": items_html,
                "has_next": page_obj.has_next(),
                "next_page": page_obj.next_page_number() if page_obj.has_next() else None,
            }
        )


class ProblemReportLogEntriesPartialView(LoginRequiredMixin, UserPassesTestMixin, View):
    """AJAX endpoint for infinite scrolling log entries on a problem report detail page."""

    template_name = "maintenance/partials/problem_report_log_entry.html"

    def test_func(self):
        return self.request.user.is_staff

    def get(self, request, *args, **kwargs):
        problem_report = get_object_or_404(ProblemReport, pk=kwargs["pk"])
        log_entries = LogEntry.objects.filter(problem_report=problem_report).select_related(
            "machine"
        )

        search_query = request.GET.get("q", "").strip()
        if search_query:
            log_entries = log_entries.filter(
                Q(text__icontains=search_query)
                | Q(maintainers__user__username__icontains=search_query)
                | Q(maintainers__user__first_name__icontains=search_query)
                | Q(maintainers__user__last_name__icontains=search_query)
                | Q(maintainer_names__icontains=search_query)
            ).distinct()

        log_entries = log_entries.prefetch_related("maintainers", "media").order_by("-created_at")

        paginator = Paginator(log_entries, 10)
        page_obj = paginator.get_page(request.GET.get("page"))
        items_html = "".join(
            render_to_string(self.template_name, {"entry": entry}) for entry in page_obj.object_list
        )
        return JsonResponse(
            {
                "items": items_html,
                "has_next": page_obj.has_next(),
                "next_page": page_obj.next_page_number() if page_obj.has_next() else None,
            }
        )


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
        queryset = (
            ProblemReport.objects.filter(machine=self.machine)
            .select_related("reported_by_user")
            .order_by("-status", "-created_at")
        )

        # Search by description text if provided
        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            queryset = queryset.filter(description__icontains=search_query)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["machine"] = self.machine
        search_query = self.request.GET.get("q", "")
        context["search_form"] = SearchForm(initial={"q": search_query})
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
            messages.error(request, "Too many reports submitted recently. Please try again later.")
            return redirect(self.machine.get_absolute_url())

        return super().post(request, *args, **kwargs)

    def _check_rate_limit(self, ip_address: str) -> bool:
        """Check if IP address has exceeded rate limit. Returns True if OK to proceed."""
        time_window = timezone.now() - timedelta(minutes=settings.RATE_LIMIT_WINDOW_MINUTES)
        recent_reports = ProblemReport.objects.filter(
            ip_address=ip_address, created_at__gte=time_window
        ).count()
        return recent_reports < settings.RATE_LIMIT_REPORTS_PER_IP

    def form_valid(self, form):
        report = form.save(commit=False)
        report.machine = self.machine
        report.ip_address = self.request.META.get("REMOTE_ADDR")
        report.device_info = self.request.META.get("HTTP_USER_AGENT", "")[
            :200
        ]  # Truncate to field max length
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
            ProblemReport.objects.select_related("machine", "reported_by_user"), pk=kwargs["pk"]
        )
        return self.render_response(request, report)

    def post(self, request, *args, **kwargs):
        report = get_object_or_404(
            ProblemReport.objects.select_related("machine", "reported_by_user"), pk=kwargs["pk"]
        )
        # Toggle status
        if report.status == ProblemReport.STATUS_OPEN:
            report.status = ProblemReport.STATUS_CLOSED
            message = "Problem report closed."
            log_text = "Closed problem report"
        else:
            report.status = ProblemReport.STATUS_OPEN
            message = "Problem report re-opened."
            log_text = "Re-opened problem report"

        report.save(update_fields=["status", "updated_at"])
        log_entry = LogEntry.objects.create(
            machine=report.machine,
            problem_report=report,
            text=log_text,
            created_by=request.user,
        )
        maintainer = Maintainer.objects.filter(user=request.user).first()
        if maintainer:
            log_entry.maintainers.add(maintainer)
        messages.success(request, message)
        return redirect("problem-report-detail", pk=report.pk)

    def render_response(self, request, report):
        from django.shortcuts import render

        # Get log entries for this problem report with pagination
        log_entries = LogEntry.objects.filter(problem_report=report).select_related("machine")

        search_query = request.GET.get("q", "").strip()
        if search_query:
            log_entries = log_entries.filter(
                Q(text__icontains=search_query)
                | Q(maintainers__user__username__icontains=search_query)
                | Q(maintainers__user__first_name__icontains=search_query)
                | Q(maintainers__user__last_name__icontains=search_query)
                | Q(maintainer_names__icontains=search_query)
            ).distinct()

        log_entries = log_entries.prefetch_related("maintainers", "media").order_by("-created_at")
        paginator = Paginator(log_entries, 10)
        page_obj = paginator.get_page(request.GET.get("page"))

        context = {
            "report": report,
            "machine": report.machine,
            "page_obj": page_obj,
            "log_entries": page_obj.object_list,
            "search_form": SearchForm(initial={"q": search_query}),
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
            .select_related("machine", "problem_report")
            .prefetch_related("maintainers", "media")
            .order_by("-work_date")
        )

        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            logs = logs.filter(
                Q(text__icontains=search_query)
                | Q(maintainers__user__username__icontains=search_query)
                | Q(maintainers__user__first_name__icontains=search_query)
                | Q(maintainers__user__last_name__icontains=search_query)
            ).distinct()

        paginator = Paginator(logs, 10)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        context.update(
            {
                "machine": self.machine,
                "page_obj": page_obj,
                "log_entries": page_obj.object_list,
                "search_form": SearchForm(initial={"q": search_query}),
            }
        )
        return context


class MachineLogCreateView(LoginRequiredMixin, UserPassesTestMixin, FormView):
    template_name = "maintenance/machine_log_new.html"
    form_class = LogEntryQuickForm

    def test_func(self):
        return self.request.user.is_staff

    def dispatch(self, request, *args, **kwargs):
        # Two modes: either a machine slug OR a problem report pk
        self.problem_report = None
        if "pk" in kwargs:
            # Creating log entry for a problem report - inherit machine from it
            self.problem_report = get_object_or_404(
                ProblemReport.objects.select_related("machine"), pk=kwargs["pk"]
            )
            self.machine = self.problem_report.machine
        else:
            # Creating log entry for a machine directly
            self.machine = get_object_or_404(MachineInstance, slug=kwargs["slug"])
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        # Pre-fill maintainer name only for individual accounts (not shared accounts)
        if self.request.user.is_authenticated:
            is_shared = (
                hasattr(self.request.user, "maintainer")
                and self.request.user.maintainer.is_shared_account
            )
            if not is_shared:
                initial["submitter_name"] = (
                    self.request.user.get_full_name() or self.request.user.get_username()
                )
        # work_date default is set by JavaScript to use browser's local timezone
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["machine"] = self.machine
        context["problem_report"] = self.problem_report
        # Check if current user is a shared account (show autocomplete for maintainer selection)
        is_shared_account = False
        if hasattr(self.request.user, "maintainer"):
            is_shared_account = self.request.user.maintainer.is_shared_account
        context["is_shared_account"] = is_shared_account
        return context

    def form_valid(self, form):
        submitter_name = form.cleaned_data["submitter_name"].strip()
        description = form.cleaned_data["text"].strip()
        media_file = form.cleaned_data["media_file"]
        work_date = form.cleaned_data["work_date"]

        # Convert work_date to browser's timezone if offset provided
        tz_offset_str = self.request.POST.get("tz_offset", "")
        if tz_offset_str:
            try:
                tz_offset_minutes = int(tz_offset_str)
                # Create timezone from offset (invert sign: JS gives minutes behind UTC)
                browser_tz = dt_timezone(timedelta(minutes=-tz_offset_minutes))
                # Replace the timezone info with browser's timezone
                # First make naive, then attach browser timezone
                naive_dt = work_date.replace(tzinfo=None)
                work_date = naive_dt.replace(tzinfo=browser_tz)
            except (ValueError, TypeError):
                pass  # Keep original work_date if conversion fails

        log_entry = LogEntry.objects.create(
            machine=self.machine,
            problem_report=self.problem_report,
            text=description,
            work_date=work_date,
            created_by=self.request.user,
        )

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
                reverse("log-detail", kwargs={"pk": log_entry.pk}),
            ),
        )

        # Redirect back to problem report if created from there, otherwise to machine log
        if self.problem_report:
            return redirect("problem-report-detail", pk=self.problem_report.pk)
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
            .select_related("machine", "problem_report")
            .prefetch_related("maintainers", "media")
            .order_by("-work_date")
        )

        search_query = request.GET.get("q", "").strip()
        if search_query:
            logs = logs.filter(
                Q(text__icontains=search_query)
                | Q(maintainers__user__username__icontains=search_query)
                | Q(maintainers__user__first_name__icontains=search_query)
                | Q(maintainers__user__last_name__icontains=search_query)
            ).distinct()

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
            .select_related("machine", "machine__model", "problem_report")
            .prefetch_related("maintainers", "media")
            .order_by("-work_date")
        )

        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            logs = logs.filter(
                Q(text__icontains=search_query)
                | Q(machine__model__name__icontains=search_query)
                | Q(machine__name_override__icontains=search_query)
                | Q(maintainers__user__username__icontains=search_query)
                | Q(maintainers__user__first_name__icontains=search_query)
                | Q(maintainers__user__last_name__icontains=search_query)
            ).distinct()

        paginator = Paginator(logs, 10)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        context.update(
            {
                "page_obj": page_obj,
                "log_entries": page_obj.object_list,
                "search_form": SearchForm(initial={"q": search_query}),
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
            .select_related("machine", "machine__model", "problem_report")
            .prefetch_related("maintainers", "media")
            .order_by("-work_date")
        )

        search_query = request.GET.get("q", "").strip()
        if search_query:
            logs = logs.filter(
                Q(text__icontains=search_query)
                | Q(machine__model__name__icontains=search_query)
                | Q(machine__name_override__icontains=search_query)
                | Q(maintainers__user__username__icontains=search_query)
                | Q(maintainers__user__first_name__icontains=search_query)
                | Q(maintainers__user__last_name__icontains=search_query)
            ).distinct()

        paginator = Paginator(logs, 10)
        page_obj = paginator.get_page(request.GET.get("page"))
        items_html = "".join(
            render_to_string(self.template_name, {"entry": entry, "machine": entry.machine})
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

        elif action == "update_work_date":
            work_date_str = request.POST.get("work_date", "")
            if not work_date_str:
                return JsonResponse({"success": False, "error": "No date provided"}, status=400)
            try:
                # Parse datetime-local format: YYYY-MM-DDTHH:MM
                naive_dt = datetime.strptime(work_date_str, "%Y-%m-%dT%H:%M")

                # Get browser timezone offset (minutes behind UTC, negative = ahead)
                tz_offset_str = request.POST.get("tz_offset", "")
                if tz_offset_str:
                    tz_offset_minutes = int(tz_offset_str)
                    # Create timezone from offset (invert sign: JS gives minutes behind UTC)
                    browser_tz = dt_timezone(timedelta(minutes=-tz_offset_minutes))
                    work_date = naive_dt.replace(tzinfo=browser_tz)
                else:
                    # Fallback to server timezone if no offset provided
                    work_date = timezone.make_aware(naive_dt)

                # Validate not in the future (compare in browser's timezone)
                now_in_browser_tz = timezone.now().astimezone(work_date.tzinfo)
                if work_date.date() > now_in_browser_tz.date():
                    return JsonResponse(
                        {"success": False, "error": "Date cannot be in the future."}, status=400
                    )
                self.object.work_date = work_date
                self.object.save(update_fields=["work_date", "updated_at"])
                return JsonResponse({"success": True})
            except ValueError:
                return JsonResponse({"success": False, "error": "Invalid date format"}, status=400)

        elif action == "upload_media":
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
                media = LogEntryMedia.objects.create(
                    log_entry=self.object,
                    media_type=LogEntryMedia.TYPE_VIDEO if is_video else LogEntryMedia.TYPE_PHOTO,
                    file=upload,
                    transcode_status=LogEntryMedia.STATUS_PENDING if is_video else "",
                )
                if is_video:
                    enqueue_transcode(media.id)
                return JsonResponse(
                    {
                        "success": True,
                        "media_id": media.id,
                        "media_url": media.transcoded_file.url
                        if media.transcoded_file
                        else media.file.url,
                        "media_type": media.media_type,
                        "transcode_status": media.transcode_status,
                        "poster_url": media.poster_file.url if media.poster_file else None,
                    }
                )
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
        logo_path = (
            Path(__file__).resolve().parent.parent.parent / "static/core/images/logo_white.png"
        )
        if logo_path.exists():
            # Invert white logo to black for visibility on white QR background
            logo = Image.open(logo_path).convert("RGBA")
            r, g, b, a = logo.split()
            rgb = Image.merge("RGB", (r, g, b))
            inverted = ImageOps.invert(rgb)
            logo = Image.merge("RGBA", (*inverted.split(), a))

            # Calculate logo size (28% of QR code size, within 30% error correction capacity)
            qr_width, qr_height = qr_img.size
            logo_size = int(qr_width * 0.28)

            # Resize logo maintaining aspect ratio
            logo.thumbnail((logo_size, logo_size), Image.LANCZOS)

            # Add white background/padding to logo for better contrast
            padding = 4
            logo_with_bg = Image.new(
                "RGB", (logo.size[0] + padding * 2, logo.size[1] + padding * 2), "white"
            )
            logo_pos = (padding, padding)
            logo_with_bg.paste(logo, logo_pos, logo if logo.mode == "RGBA" else None)

            # Calculate center position and paste logo
            logo_position = (
                (qr_width - logo_with_bg.size[0]) // 2,
                (qr_height - logo_with_bg.size[1]) // 2,
            )
            qr_img.paste(logo_with_bg, logo_position)

        # Convert to base64 for inline display
        buffer = BytesIO()
        qr_img.save(buffer, format="PNG")
        qr_code_data = base64.b64encode(buffer.getvalue()).decode()

        context["qr_code_data"] = qr_code_data
        context["public_url"] = public_url

        return context


class ReceiveTranscodedMediaView(View):
    """
    API endpoint for worker service to upload transcoded video files.

    Expects multipart/form-data with:
    - video_file: transcoded video file
    - poster_file: generated poster image
    - log_entry_media_id: ID of LogEntryMedia record to update
    - Authorization header: Bearer <token>
    """

    def post(self, request, *args, **kwargs):
        # Validate authentication token
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith("Bearer "):
            return JsonResponse(
                {"success": False, "error": "Missing or invalid Authorization header"}, status=401
            )

        token = auth_header[7:]  # Remove "Bearer " prefix
        if not settings.TRANSCODING_UPLOAD_TOKEN:
            return JsonResponse(
                {"success": False, "error": "Server not configured for transcoding uploads"},
                status=500,
            )

        if token != settings.TRANSCODING_UPLOAD_TOKEN:
            return JsonResponse(
                {"success": False, "error": "Invalid authentication token"}, status=403
            )

        # Validate required fields
        media_id = request.POST.get("log_entry_media_id")
        if not media_id:
            return JsonResponse(
                {"success": False, "error": "Missing log_entry_media_id"}, status=400
            )

        video_file = request.FILES.get("video_file")
        poster_file = request.FILES.get("poster_file")

        if not video_file:
            return JsonResponse({"success": False, "error": "Missing video_file"}, status=400)

        # Validate file types
        video_content_type = (getattr(video_file, "content_type", "") or "").lower()
        if not video_content_type.startswith("video/"):
            return JsonResponse(
                {"success": False, "error": f"Invalid video file type: {video_content_type}"},
                status=400,
            )

        if poster_file:
            poster_content_type = (getattr(poster_file, "content_type", "") or "").lower()
            if not poster_content_type.startswith("image/"):
                return JsonResponse(
                    {"success": False, "error": f"Invalid poster file type: {poster_content_type}"},
                    status=400,
                )

        # Get LogEntryMedia record
        try:
            media = LogEntryMedia.objects.get(id=media_id)
        except LogEntryMedia.DoesNotExist:
            return JsonResponse(
                {"success": False, "error": f"LogEntryMedia with id {media_id} not found"},
                status=404,
            )

        # Save transcoded files and update record
        try:
            from django.db import transaction

            with transaction.atomic():
                # Delete original file
                if media.file:
                    media.file.delete(save=False)

                # Save transcoded video
                media.transcoded_file = video_file

                # Save poster if provided
                if poster_file:
                    media.poster_file = poster_file

                # Update status
                media.transcode_status = LogEntryMedia.STATUS_READY

                media.save()

            return JsonResponse(
                {
                    "success": True,
                    "message": "Transcoded media uploaded successfully",
                    "media_id": media.id,
                    "transcoded_url": media.transcoded_file.url,
                    "poster_url": media.poster_file.url if media.poster_file else None,
                }
            )

        except Exception as e:
            return JsonResponse(
                {"success": False, "error": f"Failed to save transcoded media: {str(e)}"},
                status=500,
            )
