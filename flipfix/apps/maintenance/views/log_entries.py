"""Log entry views: CRUD and listing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.views import View
from django.views.generic import DetailView, FormView, TemplateView, UpdateView

from flipfix.apps.accounts.models import Maintainer
from flipfix.apps.catalog.models import MachineInstance
from flipfix.apps.catalog.view_helpers import resolve_selected_machine
from flipfix.apps.core.datetime import (
    apply_and_validate_timezone,
    parse_datetime_with_browser_timezone,
)
from flipfix.apps.core.forms import SearchForm
from flipfix.apps.core.markdown_links import sync_references
from flipfix.apps.core.media_upload import attach_media_files
from flipfix.apps.core.mixins import (
    CanAccessMaintainerPortalMixin,
    FormPrefillMixin,
    InfiniteScrollMixin,
    InlineTextEditMixin,
    MediaUploadMixin,
    SharedAccountMixin,
    can_access_maintainer_portal,
)
from flipfix.apps.maintenance.forms import LogEntryEditForm, LogEntryQuickForm
from flipfix.apps.maintenance.models import (
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


class MachineLogCreateView(
    FormPrefillMixin, SharedAccountMixin, CanAccessMaintainerPortalMixin, FormView
):
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
        if not self.is_shared_account:
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
        # Pre-fill chip input with current maintainer (unless shared account)
        if not self.is_shared_account and hasattr(self.request.user, "maintainer"):
            context["initial_maintainers"] = [self.request.user.maintainer]
        context["maintainer_errors"] = getattr(self, "maintainer_errors", [])
        context["selected_machine"] = resolve_selected_machine(self.request, self.machine)
        return context

    @transaction.atomic
    def form_valid(self, form):
        description = form.cleaned_data["text"].strip()
        media_files = form.cleaned_data["media_file"]
        occurred_at, is_valid = apply_and_validate_timezone(form, self.request)
        if not is_valid:
            return self.form_invalid(form)

        machine = self._resolve_machine(form)
        if machine is None:
            return self.form_invalid(form)

        result = self._resolve_maintainers(form)
        if result is None:
            return self.form_invalid(form)
        maintainers, freetext_names = result

        log_entry = LogEntry.objects.create(
            machine=machine,
            problem_report=self.problem_report,
            text=description,
            occurred_at=occurred_at,
            created_by=self.request.user,
        )
        sync_references(log_entry, log_entry.text)
        self.machine = machine

        self._link_maintainers(log_entry, maintainers, freetext_names)
        self._attach_media(log_entry, media_files)
        problem_closed = self._maybe_close_problem_report()
        self._build_success_message(log_entry, problem_closed)

        if self.problem_report:
            return redirect("problem-report-detail", pk=self.problem_report.pk)
        return redirect("maintainer-machine-detail", slug=self.machine.slug)

    def _resolve_machine(self, form):
        """Resolve the target machine from the URL or form input.

        Returns the MachineInstance, or None if resolution fails
        (after adding an error to the form).
        """
        if self.machine:
            return self.machine

        slug = (form.cleaned_data.get("machine_slug") or "").strip()
        machine = MachineInstance.objects.filter(slug=slug).first()
        if not machine:
            form.add_error("machine_slug", "Select a machine.")
            return None
        return machine

    def _resolve_maintainers(self, form):
        """Parse maintainer chip input and validate at least one is present.

        Returns (maintainers, freetext_names) on success, or None on
        failure (after setting self.maintainer_errors).
        """
        # Get maintainer selections from chip input
        usernames = self.request.POST.getlist("maintainer_usernames")
        freetext_names = [
            n.strip() for n in self.request.POST.getlist("maintainer_freetext") if n.strip()
        ]

        # Query for valid maintainers (shared accounts are filtered out)
        maintainers = list(
            Maintainer.objects.filter(
                user__username__in=usernames,
                is_shared_account=False,
            )
        )

        # Handle empty maintainers based on account type
        current_maintainer = get_object_or_404(Maintainer, user=self.request.user)
        if not maintainers and not freetext_names:
            if current_maintainer.is_shared_account:
                # Shared terminal: require explicit maintainer selection
                self.maintainer_errors = ["Please add at least one maintainer."]
                return None
            else:
                # Regular account: default to current user
                maintainers = [current_maintainer]

        return maintainers, freetext_names

    def _link_maintainers(self, log_entry, maintainers, freetext_names):
        """Set M2M maintainer links and freetext maintainer names on the log entry."""
        for maintainer in maintainers:
            log_entry.maintainers.add(maintainer)

        # De-dup freetext names while preserving order
        freetext_names = list(dict.fromkeys(freetext_names))
        if freetext_names:
            log_entry.maintainer_names = ", ".join(freetext_names)
            log_entry.save(update_fields=["maintainer_names"])

    def _attach_media(self, log_entry, media_files):
        """Attach uploaded media files to the log entry."""
        if media_files:
            attach_media_files(
                media_files=media_files,
                parent=log_entry,
                media_model=LogEntryMedia,
            )

    def _maybe_close_problem_report(self):
        """Close the linked problem report if the user checked the close checkbox.

        Returns True if the problem report was closed, False otherwise.
        """
        if self.problem_report and self.request.POST.get("close_problem"):
            self.problem_report.status = ProblemReport.Status.CLOSED
            self.problem_report.save(update_fields=["status"])
            return True
        return False

    def _build_success_message(self, log_entry, problem_closed):
        """Add a success message describing the created log entry."""
        if problem_closed:
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


class LogListView(CanAccessMaintainerPortalMixin, TemplateView):
    """Global list of all log entries across all machines. Maintainer-only access."""

    template_name = "maintenance/log_entry_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        search_query = self.request.GET.get("q", "").strip()
        logs = get_log_entry_queryset(search_query)

        paginator = Paginator(logs, settings.LIST_PAGE_SIZE)
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


class LogEntryDetailView(
    InlineTextEditMixin, MediaUploadMixin, CanAccessMaintainerPortalMixin, DetailView
):
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

    def post(self, request, *args, **kwargs):
        """Handle AJAX updates to the log entry."""
        self.object = self.get_object()
        action = request.POST.get("action")

        action_handlers = {
            "update_text": self.handle_update_text,
            "update_occurred_at": self._handle_update_occurred_at,
            "upload_media": self.handle_upload_media,
            "delete_media": self.handle_delete_media,
            "update_maintainers": self._handle_update_maintainers,
            "update_problem_report": self._handle_update_problem_report,
            "update_machine": self._handle_update_machine,
        }

        if action in action_handlers:
            return action_handlers[action](request)

        return JsonResponse({"success": False, "error": f"Unknown action: {action}"}, status=400)

    # -- Action handlers -------------------------------------------------------

    def _handle_update_occurred_at(self, request):
        """AJAX: update the occurred_at timestamp."""
        occurred_at_str = request.POST.get("occurred_at", "")
        if not occurred_at_str:
            return JsonResponse({"success": False, "error": "No date provided"}, status=400)

        occurred_at = parse_datetime_with_browser_timezone(occurred_at_str, request)
        if not occurred_at:
            return JsonResponse({"success": False, "error": "Invalid date format"}, status=400)

        # Validate not in the future
        # Make aware if naive (when browser_timezone not provided)
        if timezone.is_naive(occurred_at):
            occurred_at = timezone.make_aware(occurred_at)
        if occurred_at > timezone.now():
            return JsonResponse(
                {"success": False, "error": "Date cannot be in the future."}, status=400
            )
        self.object.occurred_at = occurred_at
        self.object.save(update_fields=["occurred_at", "updated_at"])
        return JsonResponse({"success": True})

    def _handle_update_maintainers(self, request):
        """AJAX: update maintainer assignments."""
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

    def _handle_update_problem_report(self, request):
        """AJAX: change the problem report (and machine) for this log entry."""
        problem_report_id = request.POST.get("problem_report_id", "").strip()

        if not problem_report_id or problem_report_id == "none":
            return self._unlink_problem_report(request)

        # Link to a specific problem report
        new_report = ProblemReport.objects.filter(pk=problem_report_id).first()
        if not new_report:
            return JsonResponse({"success": False, "error": "Problem report not found"}, status=404)

        if new_report.pk == self.object.problem_report_id:
            return JsonResponse({"success": True, "status": "noop"})

        # Capture old state before updating
        old_report = self.object.problem_report
        old_machine = self.object.machine

        # Update problem report and machine
        self.object.problem_report = new_report
        self.object.machine = new_report.machine
        self.object.save(update_fields=["problem_report", "machine", "updated_at"])

        self._add_problem_report_link_message(request, old_report, old_machine, new_report)

        return JsonResponse(
            {
                "success": True,
                "problem_report_id": new_report.pk,
                "machine_slug": new_report.machine.slug,
                "machine_name": new_report.machine.name,
            }
        )

    def _unlink_problem_report(self, request):
        """Unlink from problem report (become orphan), keep current machine."""
        if self.object.problem_report_id is None:
            return JsonResponse({"success": True, "status": "noop"})

        old_report = self.object.problem_report
        self.object.problem_report = None
        self.object.save(update_fields=["problem_report", "updated_at"])

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

    def _add_problem_report_link_message(self, request, old_report, old_machine, new_report):
        """Add a success message describing the problem report link change."""
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
            messages.success(
                request,
                format_html(
                    "Log entry linked to problem {} on {}.",
                    new_report_link,
                    new_machine_link,
                ),
            )
        elif old_machine.pk == new_report.machine.pk:
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

    def _handle_update_machine(self, request):
        """AJAX: change the machine for an orphan log entry (not linked to a problem report)."""
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
            return JsonResponse({"success": False, "error": "Machine slug required"}, status=400)

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
        context["maintainer_errors"] = getattr(self, "maintainer_errors", [])
        return context

    def form_valid(self, form):
        entry = form.save(commit=False)

        occurred_at, is_valid = apply_and_validate_timezone(form, self.request)
        if not is_valid:
            return self.form_invalid(form)

        entry.occurred_at = occurred_at

        # Get linked maintainers (from chip input autocomplete selections)
        # De-dup while preserving order
        usernames = list(dict.fromkeys(self.request.POST.getlist("maintainer_usernames")))
        maintainers = Maintainer.objects.filter(
            user__username__in=usernames,
            is_shared_account=False,
        )

        # Get free-text names (not linked to accounts)
        # Normalize: strip whitespace, de-dup, filter empty
        freetext_names = self.request.POST.getlist("maintainer_freetext")
        freetext_names = list(dict.fromkeys(n.strip() for n in freetext_names if n.strip()))

        # Validate at least one maintainer is specified (linked or freetext)
        if not maintainers and not freetext_names:
            self.maintainer_errors = ["Please add at least one maintainer."]
            return self.form_invalid(form)

        entry.maintainer_names = ", ".join(freetext_names)

        # Save then set M2M (M2M requires saved object)
        entry.save()
        entry.maintainers.set(maintainers)

        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("log-detail", kwargs={"pk": self.object.pk})
