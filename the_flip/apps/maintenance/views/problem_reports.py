"""Problem report views: CRUD and listing."""

from __future__ import annotations

from datetime import timedelta
from functools import partial

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.views import View
from django.views.generic import FormView, TemplateView, UpdateView

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import Location, MachineInstance
from the_flip.apps.core.attribution import (
    resolve_maintainer_for_create,
    resolve_maintainer_for_edit,
)
from the_flip.apps.core.columns import build_location_columns
from the_flip.apps.core.datetime import apply_browser_timezone, validate_not_future
from the_flip.apps.core.ip import get_real_ip
from the_flip.apps.core.markdown_links import (
    save_inline_markdown_field,
    sync_references,
)
from the_flip.apps.core.media import is_video_file
from the_flip.apps.core.mixins import (
    CanAccessMaintainerPortalMixin,
    FormPrefillMixin,
    InfiniteScrollMixin,
    MediaUploadMixin,
)
from the_flip.apps.core.tasks import enqueue_transcode
from the_flip.apps.maintenance.forms import (
    MaintainerProblemReportForm,
    ProblemReportEditForm,
    ProblemReportForm,
    SearchForm,
)
from the_flip.apps.maintenance.models import (
    LogEntry,
    ProblemReport,
    ProblemReportMedia,
)


class ProblemReportListView(CanAccessMaintainerPortalMixin, TemplateView):
    """Global column board of open problem reports, grouped by location."""

    template_name = "maintenance/problem_report_list.html"
    max_results_per_column = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = self.request.GET.get("q", "").strip()
        reports = ProblemReport.objects.search(query).for_open_by_location()
        context["columns"] = build_location_columns(
            reports,
            Location.objects.all(),
            include_empty_columns=False,
            max_results_per_column=self.max_results_per_column,
        )
        context["card_template"] = "maintenance/partials/column_problem_report_entry.html"
        context["search_form"] = SearchForm(initial={"q": query})
        context["query"] = query
        return context


class ProblemReportLogEntriesPartialView(CanAccessMaintainerPortalMixin, InfiniteScrollMixin, View):
    """AJAX endpoint for infinite scrolling log entries on a problem report detail page."""

    item_template = "maintenance/partials/problem_report_log_entry.html"

    def get_queryset(self):
        problem_report = get_object_or_404(ProblemReport, pk=self.kwargs["pk"])
        return (
            LogEntry.objects.filter(problem_report=problem_report)
            .search_for_problem_report(self.request.GET.get("q", ""))
            .select_related("machine")
            .prefetch_related("maintainers__user", "media")
            .order_by("-occurred_at")
        )


class PublicProblemReportCreateView(FormView):
    """Public-facing problem report submission (minimal shell)."""

    template_name = "maintenance/problem_report_new_public.html"
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
        report.priority = ProblemReport.Priority.UNTRIAGED
        report.ip_address = get_real_ip(self.request)
        report.device_info = self.request.META.get("HTTP_USER_AGENT", "")[:200]
        if self.request.user.is_authenticated:
            report.reported_by_user = self.request.user
        report.save()
        messages.success(self.request, "Thanks! The maintenance team has been notified.")
        return redirect("public-problem-report-create", slug=self.machine.slug)


class ProblemReportCreateView(FormPrefillMixin, CanAccessMaintainerPortalMixin, FormView):
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
        # Pre-fill reporter_name with current user's display name (unless shared account)
        if hasattr(self.request.user, "maintainer"):
            if not self.request.user.maintainer.is_shared_account:
                initial["reporter_name"] = (
                    self.request.user.get_full_name() or self.request.user.username
                )
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

        # Resolve reporter attribution
        current_maintainer = get_object_or_404(Maintainer, user=self.request.user)
        attribution = resolve_maintainer_for_create(
            self.request,
            current_maintainer,
            form,
            username_field="reporter_name_username",
            text_field="reporter_name",
        )
        if not attribution:
            return self.form_invalid(form)

        report = form.save(commit=False)
        report.machine = machine
        report.ip_address = get_real_ip(self.request)
        report.device_info = self.request.META.get("HTTP_USER_AGENT", "")[:200]

        # Set reporter: user FK from maintainer, or freetext name
        if attribution.maintainer:
            report.reported_by_user = attribution.maintainer.user
        report.reported_by_name = attribution.freetext_name

        occurred_at = apply_browser_timezone(form.cleaned_data.get("occurred_at"), self.request)

        # Validate after timezone conversion (form validation runs before conversion)
        if not validate_not_future(occurred_at, form):
            return self.form_invalid(form)

        report.occurred_at = occurred_at
        report.save()
        sync_references(report, report.description)

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

        action_handlers = {
            "update_text": self._handle_update_text,
            "update_machine": self._handle_update_machine,
            "update_priority": self._handle_update_priority,
            "update_status": self._handle_update_status,
            "upload_media": self.handle_upload_media,
            "delete_media": self.handle_delete_media,
            "toggle_status": self._handle_toggle_status,
        }

        if action in action_handlers:
            return action_handlers[action](request)

        # No action means form POST toggle (desktop Close/Re-Open button)
        if not action:
            return self._handle_toggle_status(request)

        return JsonResponse({"success": False, "error": f"Unknown action: {action}"}, status=400)

    # -- Action handlers -------------------------------------------------------

    def _handle_update_text(self, request):
        """AJAX: update the description field with inline markdown."""
        text = request.POST.get("text", "")
        try:
            save_inline_markdown_field(self.report, "description", text)
        except ValidationError as e:
            return JsonResponse({"success": False, "errors": e.messages}, status=400)
        return JsonResponse({"success": True})

    def _handle_update_machine(self, request):
        """AJAX: move the report (and its log entries) to a different machine."""
        machine_slug = request.POST.get("machine_slug", "").strip()
        if not machine_slug:
            return JsonResponse({"success": False, "error": "Machine slug required"}, status=400)

        new_machine = MachineInstance.objects.filter(slug=machine_slug).first()
        if not new_machine:
            return JsonResponse({"success": False, "error": "Machine not found"}, status=404)

        if new_machine.pk == self.report.machine_id:
            return JsonResponse({"success": True, "status": "noop"})

        old_machine = self.report.machine

        with transaction.atomic():
            self.report.machine = new_machine
            self.report.save(update_fields=["machine", "updated_at"])
            child_log_count = LogEntry.objects.filter(problem_report=self.report).update(
                machine=new_machine
            )

        old_machine_link = format_html(
            '<a href="{}">{}</a>',
            reverse("maintainer-machine-detail", kwargs={"slug": old_machine.slug}),
            old_machine.short_display_name,
        )
        new_machine_link = format_html(
            '<a href="{}">{}</a>',
            reverse("maintainer-machine-detail", kwargs={"slug": new_machine.slug}),
            new_machine.short_display_name,
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
                "new_machine_name": new_machine.name,
                "log_entries_moved": child_log_count,
            }
        )

    def _handle_update_priority(self, request):
        """AJAX: change priority (no log entry, no Discord)."""
        new_priority = request.POST.get("priority", "")
        settable = dict(ProblemReport.Priority.maintainer_settable())
        if new_priority not in settable:
            return JsonResponse({"success": False, "error": "Invalid priority"}, status=400)
        if new_priority == self.report.priority:
            return JsonResponse({"success": True, "status": "noop"})
        self.report.priority = new_priority
        self.report.save(update_fields=["priority", "updated_at"])
        return JsonResponse(
            {
                "success": True,
                "status": "success",
                "priority": new_priority,
                "priority_display": self.report.get_priority_display(),
            }
        )

    def _handle_update_status(self, request):
        """AJAX: change status (creates log entry, returns HTML for timeline injection)."""
        new_status = request.POST.get("status", "")
        if new_status not in ProblemReport.Status.values:
            return JsonResponse({"success": False, "error": "Invalid status"}, status=400)
        if new_status == self.report.status:
            return JsonResponse({"success": True, "status": "noop"})

        log_entry = self._change_report_status(new_status, request.user)

        log_entry_html = render_to_string(
            "maintenance/partials/problem_report_log_entry.html",
            {"entry": log_entry},
            request=request,
        )
        return JsonResponse(
            {
                "success": True,
                "status": "success",
                "new_status": new_status,
                "new_status_display": self.report.get_status_display(),
                "log_entry_html": log_entry_html,
                "entry_type": "log",
            }
        )

    def _handle_toggle_status(self, request):
        """Form POST: toggle between open/closed (desktop Close/Re-Open button)."""
        new_status = (
            ProblemReport.Status.CLOSED
            if self.report.status == ProblemReport.Status.OPEN
            else ProblemReport.Status.OPEN
        )
        self._change_report_status(new_status, request.user)

        action_text = "closed" if new_status == ProblemReport.Status.CLOSED else "re-opened"
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

    def _change_report_status(self, new_status, user):
        """Change the report status and create a log entry.

        Shared by both the AJAX status update and the form POST toggle.
        Returns the created LogEntry.
        """
        self.report.status = new_status
        log_text = (
            "Closed problem report"
            if new_status == ProblemReport.Status.CLOSED
            else "Re-opened problem report"
        )

        with transaction.atomic():
            self.report.save(update_fields=["status", "updated_at"])
            log_entry = LogEntry.objects.create(
                machine=self.report.machine,
                problem_report=self.report,
                text=log_text,
                created_by=user,
            )
            maintainer = Maintainer.objects.filter(user=user).first()
            if maintainer:
                log_entry.maintainers.add(maintainer)

        return log_entry

    def render_response(self, request, report):
        # Get log entries for this problem report with pagination
        search_query = request.GET.get("q", "").strip()
        log_entries = (
            LogEntry.objects.filter(problem_report=report)
            .search_for_problem_report(search_query)
            .select_related("machine")
            .prefetch_related("maintainers__user", "media")
            .order_by("-occurred_at")
        )
        paginator = Paginator(log_entries, settings.LIST_PAGE_SIZE)
        page_obj = paginator.get_page(request.GET.get("page"))

        context = {
            "report": report,
            "machine": report.machine,
            "page_obj": page_obj,
            "log_entries": page_obj.object_list,
            "log_count": paginator.count,
            "search_query": search_query,
        }
        return render(request, self.template_name, context)


class ProblemReportEditView(CanAccessMaintainerPortalMixin, UpdateView):
    """Edit a problem report's metadata (reporter, timestamp)."""

    model = ProblemReport
    form_class = ProblemReportEditForm
    template_name = "maintenance/problem_report_edit.html"

    def get_queryset(self):
        return ProblemReport.objects.select_related(
            "machine",
            "machine__model",
            "reported_by_user",
        )

    def get_initial(self):
        initial = super().get_initial()
        # Pre-fill reporter_name with current reporter's display name
        if self.object.reported_by_user:
            initial["reporter_name"] = self.object.reported_by_user.get_full_name() or str(
                self.object.reported_by_user
            )
        elif self.object.reported_by_name:
            initial["reporter_name"] = self.object.reported_by_name
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["report"] = self.object
        context["machine"] = self.object.machine
        return context

    def form_valid(self, form):
        # Resolve reporter attribution
        attribution = resolve_maintainer_for_edit(
            self.request,
            form,
            username_field="reporter_name_username",
            text_field="reporter_name",
            error_message="Please enter a reporter name.",
        )
        if not attribution:
            return self.form_invalid(form)

        report = form.save(commit=False)

        # Set reporter: user FK from maintainer, or freetext name
        if attribution.maintainer:
            report.reported_by_user = attribution.maintainer.user
            report.reported_by_name = ""
        else:
            report.reported_by_user = None
            report.reported_by_name = attribution.freetext_name

        occurred_at = apply_browser_timezone(form.cleaned_data.get("occurred_at"), self.request)

        # Validate after timezone conversion (form validation runs before conversion)
        if not validate_not_future(occurred_at, form):
            return self.form_invalid(form)

        report.occurred_at = occurred_at
        report.save()

        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("problem-report-detail", kwargs={"pk": self.object.pk})


# ---------------------------------------------------------------------------
# Wall display
# ---------------------------------------------------------------------------

MIN_REFRESH_SECONDS = 10


class WallDisplaySetupView(CanAccessMaintainerPortalMixin, TemplateView):
    """Configuration page for the wall display board."""

    template_name = "maintenance/wall_display_setup.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["locations"] = Location.objects.all()
        return context


class WallDisplayBoardView(CanAccessMaintainerPortalMixin, TemplateView):
    """Full-screen wall display showing open problems by location."""

    template_name = "maintenance/wall_display_board.html"
    max_results_per_column = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        location_slugs = self.request.GET.getlist("location")

        if not location_slugs:
            context["error"] = "No locations specified."
            context["columns"] = []
            context["refresh_seconds"] = None
            return context

        # Parse refresh parameter
        refresh_seconds = None
        raw_refresh = self.request.GET.get("refresh")
        if raw_refresh:
            try:
                value = int(raw_refresh)
                if value >= MIN_REFRESH_SECONDS:
                    refresh_seconds = value
            except (ValueError, TypeError):
                pass

        locations_by_slug = {
            loc.slug: loc for loc in Location.objects.filter(slug__in=location_slugs)
        }
        invalid_slugs = [s for s in location_slugs if s not in locations_by_slug]

        if invalid_slugs:
            joined = ", ".join(f'"{s}"' for s in invalid_slugs)
            context["error"] = f"Unknown location: {joined}."
            context["columns"] = []
            context["refresh_seconds"] = None
            return context

        # Preserve URL param order so the setup page's drag order controls columns.
        locations = [locations_by_slug[s] for s in location_slugs]

        reports = ProblemReport.objects.for_wall_display(location_slugs)
        context["columns"] = build_location_columns(
            reports, locations, max_results_per_column=self.max_results_per_column
        )
        context["refresh_seconds"] = refresh_seconds
        return context
