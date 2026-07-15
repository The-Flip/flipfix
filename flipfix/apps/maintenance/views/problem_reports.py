"""Problem report views: CRUD and listing."""

from __future__ import annotations

import re
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.text import Truncator
from django.views import View
from django.views.generic import DetailView, FormView, TemplateView, UpdateView

from flipfix.apps.accounts.models import Maintainer
from flipfix.apps.catalog.models import Location, MachineInstance
from flipfix.apps.catalog.view_helpers import resolve_selected_machine
from flipfix.apps.core.attribution import (
    resolve_maintainer_for_create,
    resolve_maintainer_for_edit,
)
from flipfix.apps.core.columns import build_location_columns, group_by_machine
from flipfix.apps.core.datetime import apply_and_validate_timezone
from flipfix.apps.core.forms import SearchForm
from flipfix.apps.core.ip import get_real_ip
from flipfix.apps.core.markdown_links import sync_references
from flipfix.apps.core.media_upload import attach_media_files
from flipfix.apps.core.mixins import (
    FormPrefillMixin,
    InfiniteScrollMixin,
    InlineTextEditMixin,
    MediaUploadMixin,
    SharedAccountMixin,
)
from flipfix.apps.maintenance.forms import (
    MaintainerProblemReportForm,
    ProblemReportEditForm,
    ProblemReportForm,
)
from flipfix.apps.maintenance.models import (
    LogEntry,
    ProblemReport,
    ProblemReportMedia,
)
from flipfix.apps.maintenance.status_rules import (
    enforce_unplayable_breaks_machine,
    machine_status_downgrade_prompt,
)


class ProblemReportListView(TemplateView):
    """Global column board of open problem reports, grouped by location."""

    template_name = "maintenance/problem_report_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = self.request.GET.get("q", "").strip()
        reports = ProblemReport.objects.search(query).for_open_by_location()
        columns = build_location_columns(
            reports,
            Location.objects.all(),
            include_empty_columns=False,
        )
        for column in columns:
            column.items = group_by_machine(column.items)
        context["columns"] = columns
        context["card_template"] = "maintenance/partials/column_problem_report_group.html"
        context["search_form"] = SearchForm(initial={"q": query})
        context["query"] = query
        context["meta_description"] = (
            "Problem reports for pinball machines at The Flip, Chicago's playable pinball museum."
        )
        return context


class ProblemReportLogEntriesPartialView(InfiniteScrollMixin, View):
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


# Newly printed QR codes encode the machine's asset ID (e.g. M0001); older ones
# encode the slug. A single route resolves both, trying the asset ID first when the
# code matches the asset-ID shape so legacy slug codes keep working unchanged.
_ASSET_ID_RE = re.compile(rf"^{re.escape(MachineInstance.ASSET_ID_PREFIX)}\d+$", re.IGNORECASE)


class PublicProblemReportCreateView(FormView):
    """Public-facing problem report submission (minimal shell)."""

    template_name = "maintenance/problem_report_new_public.html"
    form_class = ProblemReportForm

    def dispatch(self, request, *args, **kwargs):
        code = kwargs["code"]
        machine = None
        if _ASSET_ID_RE.match(code):
            machine = MachineInstance.objects.filter(asset_id__iexact=code).first()
        if machine is None:
            machine = MachineInstance.objects.filter(slug=code).first()
        if machine is None:
            raise Http404("No machine matches the given code.")
        self.machine = machine
        return super().dispatch(request, *args, **kwargs)

    def _self_url_code(self) -> str:
        """Canonical code for redirecting back to this form (asset ID preferred)."""
        return self.machine.asset_id or self.machine.slug

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["machine"] = self.machine
        return context

    def post(self, request, *args, **kwargs):
        # Check rate limiting
        ip_address = get_real_ip(request)
        if ip_address and not self._check_rate_limit(ip_address):
            messages.error(request, "Too many reports submitted recently. Please try again later.")
            return redirect("public-problem-report-create", code=self._self_url_code())
        return super().post(request, *args, **kwargs)

    def _check_rate_limit(self, ip_address: str) -> bool:
        time_window = timezone.now() - timedelta(minutes=settings.RATE_LIMIT_WINDOW_MINUTES)
        recent_reports = ProblemReport.objects.filter(
            ip_address=ip_address, created_at__gte=time_window
        ).count()
        return recent_reports < settings.RATE_LIMIT_REPORTS_PER_IP

    @transaction.atomic
    def form_valid(self, form):
        report = form.save(commit=False)
        report.machine = self.machine
        report.priority = ProblemReport.Priority.UNTRIAGED
        report.ip_address = get_real_ip(self.request)
        report.device_info = self.request.META.get("HTTP_USER_AGENT", "")[:200]
        if self.request.user.is_authenticated:
            report.reported_by_user = self.request.user
        report.save()

        # Attach any photos/videos the reporter uploaded. Must run inside the
        # transaction: attach_media_files schedules video transcoding on_commit.
        media_files = form.cleaned_data.get("media_file", [])
        if media_files:
            attach_media_files(
                media_files=media_files,
                parent=report,
                media_model=ProblemReportMedia,
            )

        messages.success(self.request, "Thanks! The maintenance team has been notified.")
        return redirect("public-problem-report-create", code=self._self_url_code())


class ProblemReportCreateView(FormPrefillMixin, SharedAccountMixin, FormView):
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
        if not self.is_shared_account:
            initial["reporter_name"] = (
                self.request.user.get_full_name() or self.request.user.username
            )
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["machine"] = self.machine
        context["selected_machine"] = resolve_selected_machine(self.request, self.machine)
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

        occurred_at, is_valid = apply_and_validate_timezone(form, self.request)
        if not is_valid:
            return self.form_invalid(form)

        report.occurred_at = occurred_at
        report.save()
        sync_references(report, report.description)

        # An open Unplayable report means the machine is broken.
        enforce_unplayable_breaks_machine(report, actor=self.request.user)

        # Handle media uploads
        media_files = form.cleaned_data.get("media_file", [])
        if media_files:
            attach_media_files(
                media_files=media_files,
                parent=report,
                media_model=ProblemReportMedia,
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


class ProblemReportDetailView(InlineTextEditMixin, MediaUploadMixin, DetailView):
    """Detail view for a problem report with status toggle capability. Maintainer-only access."""

    model = ProblemReport
    template_name = "maintenance/problem_report_detail.html"
    context_object_name = "report"
    inline_text_field_name = "description"

    def get_queryset(self):
        return ProblemReport.objects.select_related("machine", "reported_by_user")

    def get_media_model(self):
        return ProblemReportMedia

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        search_query = self.request.GET.get("q", "").strip()
        log_entries = (
            LogEntry.objects.filter(problem_report=self.object)
            .search_for_problem_report(search_query)
            .select_related("machine")
            .prefetch_related("maintainers__user", "media")
            .order_by("-occurred_at")
        )
        paginator = Paginator(log_entries, settings.LIST_PAGE_SIZE)
        page_obj = paginator.get_page(self.request.GET.get("page"))

        context["machine"] = self.object.machine
        context["page_obj"] = page_obj
        context["log_entries"] = page_obj.object_list
        context["log_count"] = paginator.count
        context["search_query"] = search_query
        context["meta_description"] = Truncator(self.object.description).chars(155)
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        action = request.POST.get("action")

        action_handlers = {
            "update_text": self.handle_update_text,
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

    def _handle_update_machine(self, request):
        """AJAX: move the report (and its log entries) to a different machine."""
        machine_slug = request.POST.get("machine_slug", "").strip()
        if not machine_slug:
            return JsonResponse({"success": False, "error": "Machine slug required"}, status=400)

        new_machine = MachineInstance.objects.filter(slug=machine_slug).first()
        if not new_machine:
            return JsonResponse({"success": False, "error": "Machine not found"}, status=404)

        if new_machine.pk == self.object.machine_id:
            return JsonResponse({"success": True, "status": "noop"})

        old_machine = self.object.machine

        with transaction.atomic():
            self.object.machine = new_machine
            self.object.save(update_fields=["machine", "updated_at"])
            child_log_count = LogEntry.objects.filter(problem_report=self.object).update(
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
        if new_priority == self.object.priority:
            return JsonResponse({"success": True, "status": "noop"})
        with transaction.atomic():
            self.object.priority = new_priority
            self.object.save(update_fields=["priority", "updated_at"])
            # Raising priority to Unplayable breaks the machine.
            machine_marked_broken = enforce_unplayable_breaks_machine(
                self.object, actor=request.user
            )
        return JsonResponse(
            {
                "success": True,
                "status": "success",
                "priority": new_priority,
                "priority_display": self.object.get_priority_display(),
                "machine_marked_broken": machine_marked_broken,
            }
        )

    def _handle_update_status(self, request):
        """AJAX: change status (creates log entry, returns HTML for timeline injection)."""
        new_status = request.POST.get("status", "")
        if new_status not in ProblemReport.Status.values:
            return JsonResponse({"success": False, "error": "Invalid status"}, status=400)
        if new_status == self.object.status:
            return JsonResponse({"success": True, "status": "noop"})

        log_entry = self._change_report_status(new_status, request.user)

        log_entry_html = render_to_string(
            "maintenance/partials/problem_report_log_entry.html",
            {"entry": log_entry},
            request=request,
        )
        response = {
            "success": True,
            "status": "success",
            "new_status": new_status,
            "new_status_display": self.object.get_status_display(),
            "log_entry_html": log_entry_html,
            "entry_type": "log",
        }
        prompt = machine_status_downgrade_prompt(self.object)
        if prompt is not None:
            response["machine_status_prompt"] = prompt
        return JsonResponse(response)

    def _handle_toggle_status(self, request):
        """Form POST: toggle between open/closed (desktop Close/Re-Open button)."""
        new_status = (
            ProblemReport.Status.CLOSED
            if self.object.status == ProblemReport.Status.OPEN
            else ProblemReport.Status.OPEN
        )
        self._change_report_status(new_status, request.user)

        action_text = "closed" if new_status == ProblemReport.Status.CLOSED else "re-opened"
        messages.success(
            request,
            format_html(
                'Problem report <a href="{}">#{}</a> {}.',
                reverse("problem-report-detail", kwargs={"pk": self.object.pk}),
                self.object.pk,
                action_text,
            ),
        )
        prompt = machine_status_downgrade_prompt(self.object)
        if prompt is not None:
            machine = self.object.machine
            messages.info(
                request,
                format_html(
                    '{} <a href="{}">Update {} status</a>.',
                    prompt["message"],
                    reverse("machine-details", kwargs={"slug": machine.slug}),
                    machine.short_display_name,
                ),
            )
        return redirect("problem-report-detail", pk=self.object.pk)

    def _change_report_status(self, new_status, user):
        """Change the report status and create a log entry.

        Shared by both the AJAX status update and the form POST toggle.
        Returns the created LogEntry.
        """
        self.object.status = new_status
        log_text = (
            "Closed problem report"
            if new_status == ProblemReport.Status.CLOSED
            else "Re-opened problem report"
        )

        with transaction.atomic():
            self.object.save(update_fields=["status", "updated_at"])
            log_entry = LogEntry.objects.create(
                machine=self.object.machine,
                problem_report=self.object,
                text=log_text,
                created_by=user,
            )
            maintainer = Maintainer.objects.filter(user=user).first()
            if maintainer:
                log_entry.maintainers.add(maintainer)

        return log_entry


class ProblemReportEditView(UpdateView):
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

        occurred_at, is_valid = apply_and_validate_timezone(form, self.request)
        if not is_valid:
            return self.form_invalid(form)

        report.occurred_at = occurred_at
        report.save()

        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("problem-report-detail", kwargs={"pk": self.object.pk})
