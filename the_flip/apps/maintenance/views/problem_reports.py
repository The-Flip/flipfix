"""Problem report views: CRUD and listing."""

from __future__ import annotations

from datetime import timedelta
from functools import partial

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.views import View
from django.views.generic import FormView, ListView, TemplateView

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import Location, MachineInstance
from the_flip.apps.core.forms import is_video_file
from the_flip.apps.core.ip import get_real_ip
from the_flip.apps.core.mixins import CanAccessMaintainerPortalMixin, MediaUploadMixin
from the_flip.apps.core.tasks import enqueue_transcode
from the_flip.apps.maintenance.forms import (
    MaintainerProblemReportForm,
    ProblemReportForm,
    SearchForm,
)
from the_flip.apps.maintenance.models import (
    LogEntry,
    ProblemReport,
    ProblemReportMedia,
)


def get_problem_report_queryset(search_query: str = ""):
    """Build the queryset for global problem report lists.

    Used by both the main list view and the infinite scroll partial view
    to ensure consistent filtering, prefetching, and ordering.
    """
    latest_log_prefetch = Prefetch(
        "log_entries",
        queryset=LogEntry.objects.order_by("-created_at"),
        to_attr="prefetched_log_entries",
    )
    queryset = (
        ProblemReport.objects.select_related("machine", "machine__model")
        .prefetch_related(latest_log_prefetch, "media")
        .search(search_query)
    )

    return queryset


class ProblemReportListView(CanAccessMaintainerPortalMixin, TemplateView):
    """Global list of all problem reports across all machines. Maintainer-only access."""

    template_name = "maintenance/problem_report_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        search_query = self.request.GET.get("q", "").strip()
        reports = get_problem_report_queryset(search_query)

        paginator = Paginator(reports, 10)
        page_obj = paginator.get_page(self.request.GET.get("page"))

        # Stats for sidebar
        stats = [
            {
                "value": ProblemReport.objects.filter(status=ProblemReport.Status.OPEN).count(),
                "label": "Open",
            },
            {
                "value": ProblemReport.objects.filter(status=ProblemReport.Status.CLOSED).count(),
                "label": "Closed",
            },
        ]

        context.update(
            {
                "page_obj": page_obj,
                "reports": page_obj.object_list,
                "search_form": SearchForm(initial={"q": search_query}),
                "stats": stats,
            }
        )
        return context


class ProblemReportListPartialView(CanAccessMaintainerPortalMixin, View):
    """AJAX endpoint for infinite scrolling in the global problem report list."""

    template_name = "maintenance/partials/global_problem_report_entry.html"

    def get(self, request, *args, **kwargs):
        search_query = request.GET.get("q", "").strip()
        reports = get_problem_report_queryset(search_query)

        paginator = Paginator(reports, 10)
        page_obj = paginator.get_page(request.GET.get("page"))
        items_html = "".join(
            render_to_string(self.template_name, {"entry": report}, request=request)
            for report in page_obj.object_list
        )
        return JsonResponse(
            {
                "items": items_html,
                "has_next": page_obj.has_next(),
                "next_page": page_obj.next_page_number() if page_obj.has_next() else None,
            }
        )


class ProblemReportLogEntriesPartialView(CanAccessMaintainerPortalMixin, View):
    """AJAX endpoint for infinite scrolling log entries on a problem report detail page."""

    template_name = "maintenance/partials/problem_report_log_entry.html"

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

        log_entries = log_entries.prefetch_related("maintainers__user", "media").order_by(
            "-created_at"
        )

        paginator = Paginator(log_entries, 10)
        page_obj = paginator.get_page(request.GET.get("page"))
        items_html = "".join(
            render_to_string(self.template_name, {"entry": entry}, request=request)
            for entry in page_obj.object_list
        )
        return JsonResponse(
            {
                "items": items_html,
                "has_next": page_obj.has_next(),
                "next_page": page_obj.next_page_number() if page_obj.has_next() else None,
            }
        )


class MachineProblemReportListView(CanAccessMaintainerPortalMixin, ListView):
    """Paginated list of all problem reports for a specific machine."""

    template_name = "maintenance/machine_problem_report_list.html"
    context_object_name = "reports"
    paginate_by = 10

    def dispatch(self, request, *args, **kwargs):
        self.machine = get_object_or_404(MachineInstance, slug=kwargs["slug"])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        latest_log_prefetch = Prefetch(
            "log_entries",
            queryset=LogEntry.objects.order_by("-created_at"),
            to_attr="prefetched_log_entries",
        )
        queryset = (
            ProblemReport.objects.filter(machine=self.machine)
            .select_related("reported_by_user")
            .prefetch_related(latest_log_prefetch, "media")
            .order_by("-status", "-created_at")
        )

        # Search by description text if provided
        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            queryset = queryset.filter(
                Q(description__icontains=search_query)
                | Q(log_entries__text__icontains=search_query)
                | Q(log_entries__maintainers__user__username__icontains=search_query)
                | Q(log_entries__maintainers__user__first_name__icontains=search_query)
                | Q(log_entries__maintainers__user__last_name__icontains=search_query)
                | Q(log_entries__maintainer_names__icontains=search_query)
                | Q(reported_by_name__icontains=search_query)
                | Q(reported_by_user__username__icontains=search_query)
                | Q(reported_by_user__first_name__icontains=search_query)
                | Q(reported_by_user__last_name__icontains=search_query)
            ).distinct()

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["machine"] = self.machine
        context["active_filter"] = "problems"
        search_query = self.request.GET.get("q", "")
        context["search_form"] = SearchForm(initial={"q": search_query})
        context["locations"] = Location.objects.all()
        return context


class PublicProblemReportCreateView(FormView):
    """Public-facing problem report submission (minimal shell)."""

    template_name = "maintenance/problem_report_form_public.html"
    form_class = ProblemReportForm

    def dispatch(self, request, *args, **kwargs):
        self.machine = get_object_or_404(MachineInstance, slug=kwargs["slug"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["machine"] = self.machine
        return context

    def post(self, request, *args, **kwargs):
        # Check rate limiting
        ip_address = get_real_ip(request)
        if ip_address and not self._check_rate_limit(ip_address):
            messages.error(request, "Too many reports submitted recently. Please try again later.")
            return redirect("public-problem-report-create", slug=self.machine.slug)
        return super().post(request, *args, **kwargs)

    def _check_rate_limit(self, ip_address: str) -> bool:
        time_window = timezone.now() - timedelta(minutes=settings.RATE_LIMIT_WINDOW_MINUTES)
        recent_reports = ProblemReport.objects.filter(
            ip_address=ip_address, created_at__gte=time_window
        ).count()
        return recent_reports < settings.RATE_LIMIT_REPORTS_PER_IP

    def form_valid(self, form):
        report = form.save(commit=False)
        report.machine = self.machine
        report.ip_address = get_real_ip(self.request)
        report.device_info = self.request.META.get("HTTP_USER_AGENT", "")[:200]
        if self.request.user.is_authenticated:
            report.reported_by_user = self.request.user
        report.save()
        messages.success(self.request, "Thanks! The maintenance team has been notified.")
        return redirect("public-problem-report-create", slug=self.machine.slug)


class ProblemReportCreateView(CanAccessMaintainerPortalMixin, FormView):
    """Maintainer-facing problem report creation (global or machine-scoped)."""

    template_name = "maintenance/problem_report_new.html"
    form_class = MaintainerProblemReportForm

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
        # Check if current user is a shared account (show autocomplete for reporter selection)
        is_shared_account = False
        if hasattr(self.request.user, "maintainer"):
            is_shared_account = self.request.user.maintainer.is_shared_account
        context["is_shared_account"] = is_shared_account
        selected_slug = (
            self.request.POST.get("machine_slug") if self.request.method == "POST" else ""
        )
        if selected_slug and not self.machine:
            context["selected_machine"] = MachineInstance.objects.filter(slug=selected_slug).first()
        elif self.machine:
            context["selected_machine"] = self.machine
        return context

    @transaction.atomic
    def form_valid(self, form):
        machine = self.machine
        if not machine:
            slug = (form.cleaned_data.get("machine_slug") or "").strip()
            machine = MachineInstance.objects.filter(slug=slug).first()
            if not machine:
                form.add_error("machine_slug", "Select a machine.")
                return self.form_invalid(form)

        report = form.save(commit=False)
        report.machine = machine
        report.ip_address = get_real_ip(self.request)
        report.device_info = self.request.META.get("HTTP_USER_AGENT", "")[:200]
        if self.request.user.is_authenticated:
            report.reported_by_user = self.request.user
        # Save reporter name for shared accounts
        reporter_name = (form.cleaned_data.get("reporter_name") or "").strip()
        if reporter_name:
            report.reported_by_name = reporter_name
        report.save()

        # Handle media uploads
        media_files = form.cleaned_data.get("media_file", [])
        if media_files:
            for media_file in media_files:
                is_video = is_video_file(media_file)

                media = ProblemReportMedia.objects.create(
                    problem_report=report,
                    media_type=ProblemReportMedia.MediaType.VIDEO
                    if is_video
                    else ProblemReportMedia.MediaType.PHOTO,
                    file=media_file,
                    transcode_status=ProblemReportMedia.TranscodeStatus.PENDING if is_video else "",
                )

                if is_video:
                    transaction.on_commit(
                        partial(
                            enqueue_transcode, media_id=media.id, model_name="ProblemReportMedia"
                        )
                    )

        messages.success(
            self.request,
            format_html(
                'Problem report <a href="{}">#{}</a> created.',
                reverse("problem-report-detail", kwargs={"pk": report.pk}),
                report.pk,
            ),
        )
        return redirect("problem-report-detail", pk=report.pk)


class ProblemReportDetailView(MediaUploadMixin, CanAccessMaintainerPortalMixin, View):
    """Detail view for a problem report with status toggle capability. Maintainer-only access."""

    template_name = "maintenance/problem_report_detail.html"

    def get_media_model(self):
        return ProblemReportMedia

    def get_media_parent(self):
        return self.report

    def get(self, request, *args, **kwargs):
        report = get_object_or_404(
            ProblemReport.objects.select_related("machine", "reported_by_user"), pk=kwargs["pk"]
        )
        return self.render_response(request, report)

    def post(self, request, *args, **kwargs):
        self.report = get_object_or_404(
            ProblemReport.objects.select_related("machine", "reported_by_user"), pk=kwargs["pk"]
        )
        action = request.POST.get("action")

        # Handle AJAX description update
        if action == "update_text":
            self.report.description = request.POST.get("text", "")
            self.report.save(update_fields=["description", "updated_at"])
            return JsonResponse({"success": True})

        # Handle AJAX machine update (move report to different machine)
        if action == "update_machine":
            machine_slug = request.POST.get("machine_slug", "").strip()
            if not machine_slug:
                return JsonResponse(
                    {"success": False, "error": "Machine slug required"}, status=400
                )

            new_machine = MachineInstance.objects.filter(slug=machine_slug).first()
            if not new_machine:
                return JsonResponse({"success": False, "error": "Machine not found"}, status=404)

            if new_machine.pk == self.report.machine_id:
                return JsonResponse({"success": True, "status": "noop"})

            old_machine = self.report.machine

            with transaction.atomic():
                self.report.machine = new_machine
                self.report.save(update_fields=["machine", "updated_at"])

                # Move all child log entries to the new machine
                child_log_count = LogEntry.objects.filter(problem_report=self.report).update(
                    machine=new_machine
                )

            # Build message with hyperlinked machine names
            old_machine_link = format_html(
                '<a href="{}">{}</a>',
                reverse("maintainer-machine-detail", kwargs={"slug": old_machine.slug}),
                old_machine.display_name,
            )
            new_machine_link = format_html(
                '<a href="{}">{}</a>',
                reverse("maintainer-machine-detail", kwargs={"slug": new_machine.slug}),
                new_machine.display_name,
            )
            if child_log_count:
                messages.success(
                    request,
                    format_html(
                        "Problem report moved from {} to {}. Its {} log entries also moved.",
                        old_machine_link,
                        new_machine_link,
                        child_log_count,
                    ),
                )
            else:
                messages.success(
                    request,
                    format_html(
                        "Problem report moved from {} to {}.",
                        old_machine_link,
                        new_machine_link,
                    ),
                )

            return JsonResponse(
                {
                    "success": True,
                    "new_machine_slug": new_machine.slug,
                    "new_machine_name": new_machine.display_name,
                    "log_entries_moved": child_log_count,
                }
            )

        # Handle AJAX media upload
        if action == "upload_media":
            return self.handle_upload_media(request)

        # Handle AJAX media delete
        if action == "delete_media":
            return self.handle_delete_media(request)

        # Reject unrecognized actions (empty string means toggle status from form)
        if action and action != "toggle_status":
            return JsonResponse(
                {"success": False, "error": f"Unknown action: {action}"}, status=400
            )

        # Toggle status (wrapped in transaction so status + log entry are atomic)
        if self.report.status == ProblemReport.Status.OPEN:
            self.report.status = ProblemReport.Status.CLOSED
            action_text = "closed"
            log_text = "Closed problem report"
        else:
            self.report.status = ProblemReport.Status.OPEN
            action_text = "re-opened"
            log_text = "Re-opened problem report"

        with transaction.atomic():
            self.report.save(update_fields=["status", "updated_at"])
            log_entry = LogEntry.objects.create(
                machine=self.report.machine,
                problem_report=self.report,
                text=log_text,
                created_by=request.user,
            )
            maintainer = Maintainer.objects.filter(user=request.user).first()
            if maintainer:
                log_entry.maintainers.add(maintainer)
        messages.success(
            request,
            format_html(
                'Problem report <a href="{}">#{}</a> {}.',
                reverse("problem-report-detail", kwargs={"pk": self.report.pk}),
                self.report.pk,
                action_text,
            ),
        )
        return redirect("problem-report-detail", pk=self.report.pk)

    def render_response(self, request, report):
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

        log_entries = log_entries.prefetch_related("maintainers__user", "media").order_by(
            "-created_at"
        )
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
