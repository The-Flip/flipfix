"""Log entry views: CRUD and listing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import partial

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.views import View
from django.views.generic import DetailView, FormView, TemplateView, UpdateView

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import Location, MachineInstance
from the_flip.apps.core.datetime import apply_browser_timezone, parse_datetime_with_browser_timezone
from the_flip.apps.core.media import is_video_file
from the_flip.apps.core.mixins import (
    CanAccessMaintainerPortalMixin,
    InfiniteScrollMixin,
    MediaUploadMixin,
    can_access_maintainer_portal,
)
from the_flip.apps.core.tasks import enqueue_transcode
from the_flip.apps.maintenance.forms import LogEntryEditForm, LogEntryQuickForm, SearchForm
from the_flip.apps.maintenance.models import (
    LogEntry,
    LogEntryMedia,
    ProblemReport,
)


def get_log_entry_queryset(search_query: str = ""):
    """Build the queryset for global log entry lists.

    Used by both the main list view and the infinite scroll partial view
    to ensure consistent filtering, prefetching, and ordering.
    """
    queryset = (
        LogEntry.objects.all()
        .select_related("machine", "machine__model", "problem_report")
        .prefetch_related("maintainers__user", "media")
        .search(search_query)
        .order_by("-occurred_at")
    )

    return queryset


class MachineLogView(CanAccessMaintainerPortalMixin, TemplateView):
    """View all log entries for a specific machine."""

    template_name = "maintenance/machine_log.html"

    def dispatch(self, request, *args, **kwargs):
        self.machine = get_object_or_404(MachineInstance, slug=kwargs["slug"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        search_query = self.request.GET.get("q", "").strip()
        logs = (
            LogEntry.objects.filter(machine=self.machine)
            .search_for_machine(search_query)
            .select_related("machine", "problem_report")
            .prefetch_related("maintainers__user", "media")
            .order_by("-occurred_at")
        )

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
        # occurred_at default is set by JavaScript to use browser's local timezone
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["machine"] = self.machine
        context["problem_report"] = self.problem_report
        context["is_global"] = self.is_global
        # Check if current user is a shared account (show autocomplete for maintainer selection)
        # Also pass current maintainer for pre-filling chip input
        is_shared_account = False
        if hasattr(self.request.user, "maintainer"):
            maintainer = self.request.user.maintainer
            is_shared_account = maintainer.is_shared_account
            if not is_shared_account:
                context["initial_maintainers"] = [maintainer]
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
        description = form.cleaned_data["text"].strip()
        media_files = form.cleaned_data["media_file"]
        occurred_at = apply_browser_timezone(form.cleaned_data["occurred_at"], self.request)
        machine = self.machine

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
            occurred_at=occurred_at,
            created_by=self.request.user,
        )
        self.machine = machine

        # Get linked maintainers (from chip input autocomplete selections)
        usernames = self.request.POST.getlist("maintainer_usernames")
        maintainers = Maintainer.objects.filter(
            user__username__in=usernames,
            is_shared_account=False,
        )
        for maintainer in maintainers:
            log_entry.maintainers.add(maintainer)

        # Get free-text names (not linked to accounts)
        # Normalize: strip whitespace, de-dup, filter empty
        freetext_names = self.request.POST.getlist("maintainer_freetext")
        freetext_names = list(dict.fromkeys(n.strip() for n in freetext_names if n.strip()))
        if freetext_names:
            log_entry.maintainer_names = ", ".join(freetext_names)
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
            .search_for_machine(request.GET.get("q", ""))
            .select_related("machine", "problem_report")
            .prefetch_related("maintainers__user", "media")
            .order_by("-occurred_at")
        )

        paginator = Paginator(logs, 10)
        page_obj = paginator.get_page(request.GET.get("page"))
        items_html = "".join(
            render_to_string(
                self.template_name, {"entry": entry, "machine": machine}, request=request
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
        this_week_count = LogEntry.objects.filter(occurred_at__gte=week_ago).count()
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


class LogListPartialView(CanAccessMaintainerPortalMixin, InfiniteScrollMixin, View):
    """AJAX endpoint for infinite scrolling in the global log list."""

    item_template = "maintenance/partials/global_log_entry.html"

    def get_queryset(self):
        search_query = self.request.GET.get("q", "").strip()
        return get_log_entry_queryset(search_query)


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

        elif action == "update_occurred_at":
            occurred_at_str = request.POST.get("occurred_at", "")
            if not occurred_at_str:
                return JsonResponse({"success": False, "error": "No date provided"}, status=400)

            occurred_at = parse_datetime_with_browser_timezone(occurred_at_str, request)
            if not occurred_at:
                return JsonResponse({"success": False, "error": "Invalid date format"}, status=400)

            # Validate not in the future (compare in browser's timezone)
            now_in_browser_tz = timezone.now().astimezone(occurred_at.tzinfo)
            if occurred_at.date() > now_in_browser_tz.date():
                return JsonResponse(
                    {"success": False, "error": "Date cannot be in the future."}, status=400
                )
            self.object.occurred_at = occurred_at
            self.object.save(update_fields=["occurred_at", "updated_at"])
            return JsonResponse({"success": True})

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
                        "machine_name": self.object.machine.name,
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
                new_report.machine.short_display_name,
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
                    old_machine.short_display_name,
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
                    "machine_name": new_report.machine.name,
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
                old_machine.short_display_name,
            )
            new_machine_link = format_html(
                '<a href="{}">{}</a>',
                reverse("maintainer-machine-detail", kwargs={"slug": new_machine.slug}),
                new_machine.short_display_name,
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
                    "new_machine_name": new_machine.name,
                }
            )

        return JsonResponse({"success": False, "error": "Invalid action"}, status=400)


class LogEntryEditView(CanAccessMaintainerPortalMixin, UpdateView):
    """Edit a log entry's metadata (maintainer, timestamp)."""

    model = LogEntry
    form_class = LogEntryEditForm
    template_name = "maintenance/log_entry_edit.html"

    def get_queryset(self):
        return LogEntry.objects.select_related(
            "machine",
            "machine__model",
            "problem_report",
        ).prefetch_related("maintainers__user")

    def get_initial(self):
        initial = super().get_initial()
        # Pre-fill maintainer_name with current maintainer(s)
        if self.object.maintainers.exists():
            initial["maintainer_name"] = ", ".join(str(m) for m in self.object.maintainers.all())
        elif self.object.maintainer_names:
            initial["maintainer_name"] = self.object.maintainer_names
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["entry"] = self.object
        context["machine"] = self.object.machine
        return context

    def form_valid(self, form):
        entry = form.save(commit=False)

        # Apply browser timezone to occurred_at
        entry.occurred_at = apply_browser_timezone(
            form.cleaned_data.get("occurred_at"), self.request
        )

        # Get linked maintainers (from chip input autocomplete selections)
        # De-dup while preserving order
        usernames = list(dict.fromkeys(self.request.POST.getlist("maintainer_usernames")))
        maintainers = Maintainer.objects.filter(
            user__username__in=usernames,
            is_shared_account=False,
        )
        entry.save()
        entry.maintainers.set(maintainers)

        # Get free-text names (not linked to accounts)
        # Normalize: strip whitespace, de-dup, filter empty
        freetext_names = self.request.POST.getlist("maintainer_freetext")
        freetext_names = list(dict.fromkeys(n.strip() for n in freetext_names if n.strip()))
        entry.maintainer_names = ", ".join(freetext_names)
        entry.save(update_fields=["maintainer_names"])

        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("log-detail", kwargs={"pk": self.object.pk})
