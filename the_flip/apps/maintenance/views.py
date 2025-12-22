from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from datetime import timezone as dt_timezone
from functools import partial, wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import (
    Case,
    CharField,
    Count,
    F,
    Max,
    Prefetch,
    Q,
    Value,
    When,
)
from django.db.models.functions import Lower
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import DetailView, FormView, ListView, TemplateView, View

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import Location, MachineInstance
from the_flip.apps.core.forms import is_video_file
from the_flip.apps.core.ip import get_real_ip
from the_flip.apps.core.mixins import (
    CanAccessMaintainerPortalMixin,
    MediaUploadMixin,
    can_access_maintainer_portal,
)
from the_flip.apps.core.models import AbstractMedia, get_media_model
from the_flip.apps.core.qr import QR_BOX_SIZE_BULK, generate_qr_code_base64
from the_flip.apps.core.tasks import enqueue_transcode
from the_flip.apps.maintenance.forms import (
    LogEntryQuickForm,
    MaintainerProblemReportForm,
    ProblemReportForm,
    SearchForm,
)
from the_flip.apps.maintenance.models import (
    LogEntry,
    LogEntryMedia,
    ProblemReport,
    ProblemReportMedia,
)

logger = logging.getLogger(__name__)


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
        .order_by("-status", "-created_at")
    )

    if search_query:
        queryset = queryset.filter(
            Q(description__icontains=search_query)
            | Q(machine__model__name__icontains=search_query)
            | Q(machine__name_override__icontains=search_query)
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


def get_log_entry_queryset(search_query: str = ""):
    """Build the queryset for global log entry lists.

    Used by both the main list view and the infinite scroll partial view
    to ensure consistent filtering, prefetching, and ordering.
    """
    queryset = (
        LogEntry.objects.all()
        .select_related("machine", "machine__model", "problem_report")
        .prefetch_related("maintainers__user", "media")
        .order_by("-work_date")
    )

    if search_query:
        queryset = queryset.filter(
            Q(text__icontains=search_query)
            | Q(machine__model__name__icontains=search_query)
            | Q(machine__name_override__icontains=search_query)
            | Q(maintainers__user__username__icontains=search_query)
            | Q(maintainers__user__first_name__icontains=search_query)
            | Q(maintainers__user__last_name__icontains=search_query)
            | Q(maintainer_names__icontains=search_query)
            | Q(problem_report__description__icontains=search_query)
        ).distinct()

    return queryset


class MaintainerAutocompleteView(CanAccessMaintainerPortalMixin, View):
    """JSON endpoint for maintainer name autocomplete."""

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


class MachineAutocompleteView(CanAccessMaintainerPortalMixin, View):
    """JSON endpoint for machine autocomplete (maintainer-only)."""

    def get(self, request, *args, **kwargs):
        query = request.GET.get("q", "").strip()
        machines = (
            MachineInstance.objects.select_related("model", "location")
            .annotate(
                open_report_count=Count(
                    "problem_reports", filter=Q(problem_reports__status=ProblemReport.Status.OPEN)
                ),
                latest_open_report_date=Max(
                    "problem_reports__created_at",
                    filter=Q(problem_reports__status=ProblemReport.Status.OPEN),
                ),
            )
            .order_by(
                Case(
                    When(
                        operational_status=MachineInstance.OperationalStatus.FIXING, then=Value(1)
                    ),
                    When(
                        operational_status=MachineInstance.OperationalStatus.BROKEN, then=Value(2)
                    ),
                    When(
                        operational_status=MachineInstance.OperationalStatus.UNKNOWN, then=Value(3)
                    ),
                    When(operational_status=MachineInstance.OperationalStatus.GOOD, then=Value(4)),
                    default=Value(5),
                    output_field=CharField(),
                ),
                F("latest_open_report_date").desc(nulls_last=True),
                Lower("model__name"),
            )
        )

        if query:
            machines = machines.filter(
                Q(name_override__icontains=query)
                | Q(model__name__icontains=query)
                | Q(location__name__icontains=query)
                | Q(slug__icontains=query)
            )

        machines = machines[:50]

        results = []
        for machine in machines:
            results.append(
                {
                    "id": machine.id,
                    "slug": machine.slug,
                    "display_name": machine.display_name,
                    "location": machine.location.name if machine.location else "",
                }
            )

        return JsonResponse({"machines": results})


class ProblemReportAutocompleteView(CanAccessMaintainerPortalMixin, View):
    """JSON endpoint for problem report autocomplete (maintainer-only).

    Returns open problem reports grouped by machine, with current machine first.
    Includes a "None" option for unlinking log entries.
    """

    def get(self, request, *args, **kwargs) -> JsonResponse:
        query = request.GET.get("q", "").strip()
        current_machine_slug = request.GET.get("current_machine", "")

        reports = (
            ProblemReport.objects.filter(status=ProblemReport.Status.OPEN)
            .select_related("machine", "machine__model", "machine__location")
            .order_by("-created_at")
        )

        if query:
            reports = reports.filter(
                Q(description__icontains=query)
                | Q(machine__model__name__icontains=query)
                | Q(machine__name_override__icontains=query)
            )

        reports = reports[:100]

        # Group reports by machine
        grouped: dict[str, list[dict]] = {}
        current_machine_reports: list[dict] = []

        for report in reports:
            machine = report.machine
            report_data = {
                "id": report.id,
                "machine_slug": machine.slug,
                "machine_name": machine.display_name,
                "summary": self._get_summary(report),
                "created_at": report.created_at.isoformat(),
            }

            if machine.slug == current_machine_slug:
                current_machine_reports.append(report_data)
            else:
                machine_key = machine.display_name
                if machine_key not in grouped:
                    grouped[machine_key] = []
                grouped[machine_key].append(report_data)

        # Build result with current machine first
        result_groups = []
        if current_machine_reports:
            # Get machine name from first report
            machine_name = current_machine_reports[0]["machine_name"]
            result_groups.append(
                {"machine_name": f"{machine_name} (current)", "reports": current_machine_reports}
            )

        # Add other machines sorted alphabetically
        for machine_name in sorted(grouped.keys()):
            result_groups.append({"machine_name": machine_name, "reports": grouped[machine_name]})

        return JsonResponse({"groups": result_groups})

    def _get_summary(self, report: ProblemReport) -> str:
        """Build a concise problem report summary for the dropdown."""
        if report.problem_type == ProblemReport.ProblemType.OTHER:
            if report.description:
                desc = report.description[:60]
                if len(report.description) > 60:
                    desc += "..."
                return desc
            return "No description"
        else:
            type_label = report.get_problem_type_display()
            if report.description:
                desc = report.description[:40]
                if len(report.description) > 40:
                    desc += "..."
                return f"{type_label}: {desc}"
            return type_label


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
            render_to_string(self.template_name, {"entry": report})
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
            render_to_string(self.template_name, {"entry": entry}) for entry in page_obj.object_list
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


class MachineLogView(CanAccessMaintainerPortalMixin, TemplateView):
    """View all log entries for a specific machine."""

    template_name = "maintenance/machine_log.html"

    def dispatch(self, request, *args, **kwargs):
        self.machine = get_object_or_404(MachineInstance, slug=kwargs["slug"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        logs = (
            LogEntry.objects.filter(machine=self.machine)
            .select_related("machine", "problem_report")
            .prefetch_related("maintainers__user", "media")
            .order_by("-work_date")
        )

        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            logs = logs.filter(
                Q(text__icontains=search_query)
                | Q(maintainers__user__username__icontains=search_query)
                | Q(maintainers__user__first_name__icontains=search_query)
                | Q(maintainers__user__last_name__icontains=search_query)
                | Q(maintainer_names__icontains=search_query)
                | Q(problem_report__description__icontains=search_query)
                | Q(problem_report__reported_by_name__icontains=search_query)
            ).distinct()

        paginator = Paginator(logs, 10)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        context.update(
            {
                "machine": self.machine,
                "active_filter": "logs",
                "page_obj": page_obj,
                "log_entries": page_obj.object_list,
                "search_form": SearchForm(initial={"q": search_query}),
                "locations": Location.objects.all(),
            }
        )
        return context


class MachineLogCreateView(CanAccessMaintainerPortalMixin, FormView):
    """Create a new log entry for a machine or problem report."""

    template_name = "maintenance/log_entry_new.html"
    form_class = LogEntryQuickForm

    def dispatch(self, request, *args, **kwargs):
        # Two modes: either a machine slug OR a problem report pk
        self.problem_report = None
        self.is_global = False
        if "pk" in kwargs:
            # Creating log entry for a problem report - inherit machine from it
            self.problem_report = get_object_or_404(
                ProblemReport.objects.select_related("machine"), pk=kwargs["pk"]
            )
            self.machine = self.problem_report.machine
        elif "slug" in kwargs:
            # Creating log entry for a machine directly
            self.machine = get_object_or_404(MachineInstance, slug=kwargs["slug"])
        else:
            # Global log creation - pick machine in form
            self.machine = None
            self.is_global = True
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not can_access_maintainer_portal(request.user):
                raise PermissionDenied
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
        if self.machine:
            initial["machine_slug"] = self.machine.slug
        # work_date default is set by JavaScript to use browser's local timezone
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["machine"] = self.machine
        context["problem_report"] = self.problem_report
        context["is_global"] = self.is_global
        # Check if current user is a shared account (show autocomplete for maintainer selection)
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
        submitter_name = form.cleaned_data["submitter_name"].strip()
        description = form.cleaned_data["text"].strip()
        media_files = form.cleaned_data["media_file"]
        work_date = form.cleaned_data["work_date"]
        machine = self.machine

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

        if not machine:
            slug = (form.cleaned_data.get("machine_slug") or "").strip()
            machine = MachineInstance.objects.filter(slug=slug).first()
            if not machine:
                form.add_error("machine_slug", "Select a machine.")
                return self.form_invalid(form)

        log_entry = LogEntry.objects.create(
            machine=machine,
            problem_report=self.problem_report,
            text=description,
            work_date=work_date,
            created_by=self.request.user,
        )
        self.machine = machine

        # Use hidden username field from autocomplete for reliable maintainer lookup,
        # fall back to name-based matching if not available
        submitter_username = self.request.POST.get("submitter_name_username", "").strip()
        maintainer = None
        if submitter_username:
            maintainer = Maintainer.objects.filter(
                user__username__iexact=submitter_username,
                is_shared_account=False,
            ).first()
        if not maintainer:
            maintainer = Maintainer.match_by_name(submitter_name)
        if maintainer:
            log_entry.maintainers.add(maintainer)
        elif submitter_name:
            log_entry.maintainer_names = submitter_name
            log_entry.save(update_fields=["maintainer_names"])

        if media_files:
            for media_file in media_files:
                is_video = is_video_file(media_file)

                media = LogEntryMedia.objects.create(
                    log_entry=log_entry,
                    media_type=LogEntryMedia.MediaType.VIDEO
                    if is_video
                    else LogEntryMedia.MediaType.PHOTO,
                    file=media_file,
                    transcode_status=LogEntryMedia.TranscodeStatus.PENDING if is_video else "",
                )

                if is_video:
                    transaction.on_commit(
                        partial(enqueue_transcode, media_id=media.id, model_name="LogEntryMedia")
                    )

        # Close problem report if checkbox was checked
        if self.problem_report and self.request.POST.get("close_problem"):
            self.problem_report.status = ProblemReport.Status.CLOSED
            self.problem_report.save(update_fields=["status"])
            messages.success(
                self.request,
                format_html(
                    'Log entry added and problem <a href="{}">#{}</a> closed. Edit the log <a href="{}">here</a>.',
                    reverse("problem-report-detail", kwargs={"pk": self.problem_report.pk}),
                    self.problem_report.pk,
                    reverse("log-detail", kwargs={"pk": log_entry.pk}),
                ),
            )
        else:
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


class MachineLogPartialView(CanAccessMaintainerPortalMixin, View):
    """AJAX endpoint for infinite scrolling in machine log view."""

    template_name = "maintenance/partials/log_entry.html"

    def get(self, request, *args, **kwargs):
        machine = get_object_or_404(MachineInstance, slug=kwargs["slug"])
        logs = (
            LogEntry.objects.filter(machine=machine)
            .select_related("machine", "problem_report")
            .prefetch_related("maintainers__user", "media")
            .order_by("-work_date")
        )

        search_query = request.GET.get("q", "").strip()
        if search_query:
            logs = logs.filter(
                Q(text__icontains=search_query)
                | Q(maintainers__user__username__icontains=search_query)
                | Q(maintainers__user__first_name__icontains=search_query)
                | Q(maintainers__user__last_name__icontains=search_query)
                | Q(maintainer_names__icontains=search_query)
                | Q(problem_report__description__icontains=search_query)
                | Q(problem_report__reported_by_name__icontains=search_query)
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


class LogListView(CanAccessMaintainerPortalMixin, TemplateView):
    """Global list of all log entries across all machines. Maintainer-only access."""

    template_name = "maintenance/log_entry_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        search_query = self.request.GET.get("q", "").strip()
        logs = get_log_entry_queryset(search_query)

        paginator = Paginator(logs, 10)
        page_obj = paginator.get_page(self.request.GET.get("page"))

        # Stats for sidebar
        week_ago = datetime.now(UTC) - timedelta(days=7)
        this_week_count = LogEntry.objects.filter(work_date__gte=week_ago).count()
        total_count = LogEntry.objects.count()

        context.update(
            {
                "page_obj": page_obj,
                "log_entries": page_obj.object_list,
                "search_form": SearchForm(initial={"q": search_query}),
                "this_week_count": this_week_count,
                "total_count": total_count,
            }
        )
        return context


class LogListPartialView(CanAccessMaintainerPortalMixin, View):
    """AJAX endpoint for infinite scrolling in the global log list."""

    template_name = "maintenance/partials/global_log_entry.html"

    def get(self, request, *args, **kwargs):
        search_query = request.GET.get("q", "").strip()
        logs = get_log_entry_queryset(search_query)

        paginator = Paginator(logs, 10)
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


class LogEntryDetailView(MediaUploadMixin, CanAccessMaintainerPortalMixin, DetailView):
    """Detail page for a single log entry with media upload support."""

    model = LogEntry
    template_name = "maintenance/log_entry_detail.html"
    context_object_name = "entry"

    def get_queryset(self):
        return LogEntry.objects.select_related("machine").prefetch_related(
            "maintainers__user", "media"
        )

    def get_media_model(self):
        return LogEntryMedia

    def get_media_parent(self):
        return self.object

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
            return self.handle_upload_media(request)

        elif action == "delete_media":
            return self.handle_delete_media(request)

        elif action == "update_maintainers":
            names_raw = request.POST.get("maintainers", "")
            names = [name.strip() for name in names_raw.split(",") if name.strip()]

            matched = []
            unmatched = []
            for name in names:
                maintainer = Maintainer.match_by_name(name)
                if maintainer:
                    matched.append(maintainer)
                else:
                    unmatched.append(name)

            self.object.maintainers.set(matched)
            self.object.maintainer_names = ", ".join(unmatched)
            self.object.save(update_fields=["maintainer_names", "updated_at"])
            return JsonResponse({"success": True})

        elif action == "update_problem_report":
            # Change the problem report for this log entry
            # Also changes the machine to match the new problem report
            problem_report_id = request.POST.get("problem_report_id", "").strip()

            if not problem_report_id or problem_report_id == "none":
                # Unlink from problem report (become orphan), keep current machine
                if self.object.problem_report_id is None:
                    return JsonResponse({"success": True, "status": "noop"})

                old_report = self.object.problem_report
                self.object.problem_report = None
                self.object.save(update_fields=["problem_report", "updated_at"])

                # Message: "Log entry unlinked from problem report #{id}."
                old_report_link = format_html(
                    '<a href="{}">#{}</a>',
                    reverse("problem-report-detail", kwargs={"pk": old_report.pk}),
                    old_report.pk,
                )
                messages.success(
                    request,
                    format_html("Log entry unlinked from problem report {}.", old_report_link),
                )

                return JsonResponse(
                    {
                        "success": True,
                        "problem_report_id": None,
                        "machine_slug": self.object.machine.slug,
                        "machine_name": self.object.machine.display_name,
                    }
                )

            # Link to a specific problem report
            new_report = ProblemReport.objects.filter(pk=problem_report_id).first()
            if not new_report:
                return JsonResponse(
                    {"success": False, "error": "Problem report not found"}, status=404
                )

            if new_report.pk == self.object.problem_report_id:
                return JsonResponse({"success": True, "status": "noop"})

            # Capture old state before updating
            old_report = self.object.problem_report
            old_machine = self.object.machine

            # Update problem report and machine
            self.object.problem_report = new_report
            self.object.machine = new_report.machine
            self.object.save(update_fields=["problem_report", "machine", "updated_at"])

            # Build message based on what changed
            new_report_link = format_html(
                '<a href="{}">#{}</a>',
                reverse("problem-report-detail", kwargs={"pk": new_report.pk}),
                new_report.pk,
            )
            new_machine_link = format_html(
                '<a href="{}">{}</a>',
                reverse("maintainer-machine-detail", kwargs={"slug": new_report.machine.slug}),
                new_report.machine.display_name,
            )

            if old_report is None:
                # Was orphan, now linked: "Log entry linked to problem #{id} on {machine}."
                messages.success(
                    request,
                    format_html(
                        "Log entry linked to problem {} on {}.",
                        new_report_link,
                        new_machine_link,
                    ),
                )
            elif old_machine.pk == new_report.machine.pk:
                # Same machine, different PR: "Log entry moved from problem #{old} to problem #{new}."
                old_report_link = format_html(
                    '<a href="{}">#{}</a>',
                    reverse("problem-report-detail", kwargs={"pk": old_report.pk}),
                    old_report.pk,
                )
                messages.success(
                    request,
                    format_html(
                        "Log entry moved from problem {} to problem {}.",
                        old_report_link,
                        new_report_link,
                    ),
                )
            else:
                # Different machine and PR
                old_report_link = format_html(
                    '<a href="{}">#{}</a>',
                    reverse("problem-report-detail", kwargs={"pk": old_report.pk}),
                    old_report.pk,
                )
                old_machine_link = format_html(
                    '<a href="{}">{}</a>',
                    reverse("maintainer-machine-detail", kwargs={"slug": old_machine.slug}),
                    old_machine.display_name,
                )
                messages.success(
                    request,
                    format_html(
                        "Log entry moved from problem {} on {} to problem {} on {}.",
                        old_report_link,
                        old_machine_link,
                        new_report_link,
                        new_machine_link,
                    ),
                )

            return JsonResponse(
                {
                    "success": True,
                    "problem_report_id": new_report.pk,
                    "machine_slug": new_report.machine.slug,
                    "machine_name": new_report.machine.display_name,
                }
            )

        elif action == "update_machine":
            # Change the machine for an orphan log entry (not linked to a problem report)
            if self.object.problem_report_id is not None:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Cannot directly change machine for log entries linked to a problem report. Change the problem report instead.",
                    },
                    status=400,
                )

            machine_slug = request.POST.get("machine_slug", "").strip()
            if not machine_slug:
                return JsonResponse(
                    {"success": False, "error": "Machine slug required"}, status=400
                )

            new_machine = MachineInstance.objects.filter(slug=machine_slug).first()
            if not new_machine:
                return JsonResponse({"success": False, "error": "Machine not found"}, status=404)

            if new_machine.pk == self.object.machine_id:
                return JsonResponse({"success": True, "status": "noop"})

            old_machine = self.object.machine
            self.object.machine = new_machine
            self.object.save(update_fields=["machine", "updated_at"])

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
            messages.success(
                request,
                format_html(
                    "Log entry moved from {} to {}.",
                    old_machine_link,
                    new_machine_link,
                ),
            )

            return JsonResponse(
                {
                    "success": True,
                    "new_machine_slug": new_machine.slug,
                    "new_machine_name": new_machine.display_name,
                }
            )

        return JsonResponse({"success": False, "error": "Invalid action"}, status=400)


class MachineQRView(CanAccessMaintainerPortalMixin, DetailView):
    """Generate and display a printable QR code for a machine's public info page."""

    model = MachineInstance
    template_name = "maintenance/machine_qr.html"
    context_object_name = "machine"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        machine = self.object

        public_url = self.request.build_absolute_uri(
            reverse("public-problem-report-create", args=[machine.slug])
        )

        context["qr_code_data"] = generate_qr_code_base64(public_url)
        context["public_url"] = public_url

        return context


class MachineBulkQRCodeView(CanAccessMaintainerPortalMixin, TemplateView):
    """Printable grid of QR codes for all machines."""

    template_name = "maintenance/machine_qr_bulk.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        machines = MachineInstance.objects.visible().select_related("model", "location")
        qr_entries = []

        for machine in machines:
            public_url = self.request.build_absolute_uri(
                reverse("public-problem-report-create", args=[machine.slug])
            )
            qr_entries.append(
                {
                    "machine": machine,
                    "qr_data": generate_qr_code_base64(public_url, box_size=QR_BOX_SIZE_BULK),
                    "public_url": public_url,
                }
            )

        context["qr_entries"] = qr_entries
        return context


class _AuthenticationError(Exception):
    """Raised when API authentication fails."""

    def __init__(self, message: str, status: int = 401):
        self.message = message
        self.status = status
        super().__init__(message)


def _json_api_view(view_method):
    """
    Decorator that converts exceptions to JSON error responses.

    Handles:
    - _AuthenticationError → 401/403 with error message
    - ValidationError → 400 with error message
    - Http404 → 404 with error message
    - OSError → 500 with "File storage error" message (logged)
    - Other exceptions → 500 with generic message (logged)
    """

    @wraps(view_method)
    def wrapper(self, request, *args, **kwargs):
        try:
            return view_method(self, request, *args, **kwargs)
        except _AuthenticationError as e:
            return JsonResponse({"success": False, "error": e.message}, status=e.status)
        except ValidationError as e:
            return JsonResponse({"success": False, "error": str(e.message)}, status=400)
        except Http404 as e:
            return JsonResponse({"success": False, "error": str(e) or "Not found"}, status=404)
        except OSError as e:
            logger.exception("File storage error in %s", view_method.__name__)
            return JsonResponse({"success": False, "error": f"File storage error: {e}"}, status=500)
        except Exception:
            logger.exception("Unexpected error in %s", view_method.__name__)
            return JsonResponse({"success": False, "error": "Internal server error"}, status=500)

    return wrapper


def _validate_transcoding_auth(request) -> None:
    """
    Validate Bearer token authentication for transcoding API endpoints.

    Raises:
        _AuthenticationError: If authentication fails.
    """
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if not auth_header.startswith("Bearer "):
        raise _AuthenticationError("Missing or invalid Authorization header", status=401)

    token = auth_header[7:]  # Remove "Bearer " prefix
    if not settings.TRANSCODING_UPLOAD_TOKEN:
        raise _AuthenticationError("Server not configured for transcoding", status=500)

    if not constant_time_compare(token, settings.TRANSCODING_UPLOAD_TOKEN):
        raise _AuthenticationError("Invalid authentication token", status=403)


def _get_media_record(model_name: str, media_id: int) -> tuple[type, AbstractMedia]:
    """
    Look up a media record by model name and ID.

    Raises:
        ValidationError: If model_name is invalid.
        Http404: If media record not found.
    """
    try:
        media_model = get_media_model(model_name)
    except ValueError as e:
        raise ValidationError(str(e)) from e

    try:
        media = media_model.objects.get(id=media_id)
    except media_model.DoesNotExist as e:
        raise Http404(f"{model_name} with id {media_id} not found") from e

    return media_model, media


def _validate_upload_files(video_file, poster_file) -> None:
    """
    Validate uploaded video and poster files.

    Raises:
        ValidationError: If files are missing or have invalid types.
    """
    if not video_file:
        raise ValidationError("Missing video_file")

    video_content_type = (getattr(video_file, "content_type", "") or "").lower()
    if not video_content_type.startswith("video/"):
        raise ValidationError(f"Invalid video file type: {video_content_type}")

    if poster_file:
        poster_content_type = (getattr(poster_file, "content_type", "") or "").lower()
        if not poster_content_type.startswith("image/"):
            raise ValidationError(f"Invalid poster file type: {poster_content_type}")


@method_decorator(csrf_exempt, name="dispatch")
class ReceiveTranscodedMediaView(View):
    """
    API endpoint for worker service to upload transcoded video files.

    POST /api/transcoding/upload/<model_name>/<media_id>/

    Expects multipart/form-data with:
    - video_file: transcoded video file
    - poster_file: generated poster image
    - Authorization header: Bearer <token>
    """

    @_json_api_view
    def post(self, request, model_name: str, media_id: int):
        _validate_transcoding_auth(request)

        video_file = request.FILES.get("video_file")
        poster_file = request.FILES.get("poster_file")
        _validate_upload_files(video_file, poster_file)

        media_model, media = _get_media_record(model_name, media_id)

        return self._save_transcoded_files(media, media_model, video_file, poster_file)

    def _save_transcoded_files(self, media, media_model, video_file, poster_file) -> JsonResponse:
        """Save transcoded video and poster files to the media record."""
        original_file_name = media.file.name if media.file else None

        with transaction.atomic():
            if media.file:
                media.file = None

            media.transcoded_file = video_file
            if poster_file:
                media.poster_file = poster_file
            media.transcode_status = media_model.TranscodeStatus.READY
            media.save()

        # Delete original file only after transaction commits successfully
        if original_file_name:
            storage = media.transcoded_file.storage
            transaction.on_commit(partial(storage.delete, name=original_file_name))

        return JsonResponse(
            {
                "success": True,
                "message": "Transcoded media uploaded successfully",
                "media_id": media.id,
                "transcoded_url": media.transcoded_file.url,
                "poster_url": media.poster_file.url if media.poster_file else None,
            }
        )


@method_decorator(csrf_exempt, name="dispatch")
class ServeSourceMediaView(View):
    """
    API endpoint for worker service to download source video files.

    GET /api/transcoding/download/<model_name>/<media_id>/
    Authorization: Bearer <token>

    Returns the source file as a streaming response.
    """

    @_json_api_view
    def get(self, request, model_name: str, media_id: int):
        _validate_transcoding_auth(request)
        _media_model, media = _get_media_record(model_name, media_id)

        if not media.file:
            raise Http404("Media has no source file")

        return FileResponse(
            media.file.open("rb"),
            as_attachment=True,
            filename=media.file.name.split("/")[-1],
        )
