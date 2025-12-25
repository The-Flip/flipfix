from constance import config
from django.contrib import messages
from django.db import transaction
from django.db.models import Case, CharField, Count, F, Max, Prefetch, Q, Value, When
from django.db.models.functions import Lower
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html
from django.views import View
from django.views.generic import DetailView, FormView, ListView, UpdateView

from the_flip.apps.catalog.forms import (
    MachineCreateModelDoesNotExistForm,
    MachineCreateModelExistsForm,
    MachineInstanceForm,
    MachineModelForm,
)
from the_flip.apps.catalog.models import Location, MachineInstance, MachineModel
from the_flip.apps.core.mixins import CanAccessMaintainerPortalMixin, can_access_maintainer_portal
from the_flip.apps.maintenance.forms import ProblemReportForm, SearchForm
from the_flip.apps.maintenance.models import LogEntry, ProblemReport
from the_flip.apps.parts.models import PartRequest, PartRequestUpdate


def get_activity_entries(machine, search_query=None):
    """Get combined log entries, problem reports, and parts events for a machine.

    Returns all entries (unsliced) for pagination by the caller.
    """
    latest_log_prefetch = Prefetch(
        "log_entries",
        queryset=LogEntry.objects.order_by("-created_at"),
        to_attr="prefetched_log_entries",
    )
    logs = LogEntry.objects.filter(machine=machine).prefetch_related("maintainers__user", "media")
    reports = (
        ProblemReport.objects.filter(machine=machine)
        .select_related("reported_by_user")
        .prefetch_related(latest_log_prefetch)
    )

    # Get part requests and updates only if parts feature is enabled
    if config.PARTS_ENABLED:
        part_requests = PartRequest.objects.filter(machine=machine).select_related(
            "requested_by__user"
        )
        part_updates = PartRequestUpdate.objects.filter(
            part_request__machine=machine
        ).select_related("posted_by__user", "part_request")
    else:
        part_requests = PartRequest.objects.none()
        part_updates = PartRequestUpdate.objects.none()

    if search_query:
        logs = logs.filter(
            Q(text__icontains=search_query)
            | Q(problem_report__description__icontains=search_query)
            | Q(maintainers__user__username__icontains=search_query)
            | Q(maintainers__user__first_name__icontains=search_query)
            | Q(maintainers__user__last_name__icontains=search_query)
            | Q(maintainer_names__icontains=search_query)
        ).distinct()
        reports = reports.filter(
            Q(description__icontains=search_query)
            | Q(reported_by_name__icontains=search_query)
            | Q(log_entries__maintainers__user__username__icontains=search_query)
            | Q(log_entries__maintainers__user__first_name__icontains=search_query)
            | Q(log_entries__maintainers__user__last_name__icontains=search_query)
            | Q(log_entries__maintainer_names__icontains=search_query)
        ).distinct()
        part_requests = part_requests.filter(
            Q(text__icontains=search_query)
            | Q(requested_by__user__first_name__icontains=search_query)
            | Q(requested_by__user__last_name__icontains=search_query)
            | Q(requested_by_name__icontains=search_query)
        ).distinct()
        part_updates = part_updates.filter(
            Q(text__icontains=search_query)
            | Q(posted_by__user__first_name__icontains=search_query)
            | Q(posted_by__user__last_name__icontains=search_query)
            | Q(posted_by_name__icontains=search_query)
        ).distinct()

    logs = logs.order_by("-created_at")
    reports = reports.order_by("-created_at")
    part_requests = part_requests.order_by("-created_at")
    part_updates = part_updates.order_by("-created_at")

    return logs, reports, part_requests, part_updates


def get_activity_page(machine, page_num, page_size=10, search_query=None):
    """Get a paginated page of activity entries.

    Uses merge-sort style pagination: fetches just enough from each table
    to construct the requested page.
    """
    offset = (page_num - 1) * page_size
    fetch_limit = offset + page_size  # Worst case: all items from one table

    logs, reports, part_requests, part_updates = get_activity_entries(machine, search_query)

    # Fetch only what we need for this page
    logs_list = list(logs[:fetch_limit])
    reports_list = list(reports[:fetch_limit])
    part_requests_list = list(part_requests[:fetch_limit])
    part_updates_list = list(part_updates[:fetch_limit])

    # Tag entries for template differentiation
    for log in logs_list:
        log.entry_type = "log"  # type: ignore[attr-defined]
    for report in reports_list:
        report.entry_type = "problem_report"  # type: ignore[attr-defined]
    for pr in part_requests_list:
        pr.entry_type = "part_request"  # type: ignore[attr-defined]
    for pu in part_updates_list:
        pu.entry_type = "part_request_update"  # type: ignore[attr-defined]

    # Combine, sort, slice to page
    combined = sorted(
        logs_list + reports_list + part_requests_list + part_updates_list,
        key=lambda x: x.created_at,
        reverse=True,
    )
    page_items = combined[offset : offset + page_size]
    has_next = len(combined) > offset + page_size

    return page_items, has_next


class MachineListViewForPublic(ListView):
    """Public machine list showing status and open problems, sorted by priority."""

    template_name = "catalog/machine_list_public.html"
    context_object_name = "machines"

    def get_queryset(self):
        return (
            MachineInstance.objects.visible()
            .annotate(
                # Count open problem reports
                open_report_count=Count(
                    "problem_reports", filter=Q(problem_reports__status=ProblemReport.Status.OPEN)
                ),
                # Get the most recent open problem report date
                latest_open_report_date=Max(
                    "problem_reports__created_at",
                    filter=Q(problem_reports__status=ProblemReport.Status.OPEN),
                ),
            )
            .prefetch_related(
                Prefetch(
                    "problem_reports",
                    queryset=ProblemReport.objects.filter(
                        status=ProblemReport.Status.OPEN
                    ).order_by("-created_at")[:1],
                    to_attr="latest_open_report",
                )
            )
            .order_by(
                # 1. Status priority: fixing, broken, unknown, good
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
                # 2. Machines with open problem reports first (nulls last means machines with no reports come last)
                F("latest_open_report_date").desc(nulls_last=True),
                # 3. Within machines with open reports, sort by most recent report first (already handled by step 2)
                # 4. Machine name as tie-breaker
                Lower("model__name"),
            )
        )


class MachineListView(CanAccessMaintainerPortalMixin, MachineListViewForPublic):
    """Maintainer machine list with location stats in the sidebar."""

    template_name = "catalog/machine_list_for_maintainers.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        visible_machines = MachineInstance.objects.visible()

        # Stats for sidebar (total + location counts, max 4 to fit grid)
        stats = [{"value": visible_machines.count(), "label": "Total"}]
        for slug, label in [
            ("floor", "Floor"),
            ("workshop", "Workshop"),
            ("storage", "Storage"),
            ("hall", "Hall"),
        ]:
            count = visible_machines.filter(location__slug=slug).count()
            if count > 0:
                stats.append({"value": count, "label": label})
            if len(stats) >= 4:
                break
        context["stats"] = stats

        return context


class MachineDetailViewForPublic(DetailView):
    """Public machine detail page with problem report form."""

    template_name = "catalog/machine_detail_public.html"
    queryset = MachineInstance.objects.visible()
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["problem_report_form"] = ProblemReportForm()
        return context


class MachineDetailViewForMaintainers(CanAccessMaintainerPortalMixin, MachineDetailViewForPublic):
    """Maintainer-facing detail page; requires maintainer portal access."""

    template_name = "catalog/machine_detail_maintainer.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        machine = self.object

        # Add machine alias for template compatibility with machine_feed_base.html
        context["machine"] = machine
        context["active_filter"] = "all"

        # Provide locations for the dropdown (ordered by sort_order)
        context["locations"] = Location.objects.all()

        # Search form and query
        search_query = self.request.GET.get("q", "").strip()
        context["search_form"] = SearchForm(initial={"q": search_query})

        # Get first page of activity entries
        page_size = 10
        activity_entries, has_next = get_activity_page(
            machine, page_num=1, page_size=page_size, search_query=search_query or None
        )
        context["activity_entries"] = activity_entries

        # Create a simple page_obj-like object for template compatibility
        class SimplePage:
            """Lightweight page stub providing has_next()/next_page_number() for templates."""

            def __init__(self, has_next):
                self._has_next = has_next

            def has_next(self):
                """Return whether more pages exist."""
                return self._has_next

            def next_page_number(self):
                """Return the next page number (always 2 for first page)."""
                return 2

        context["page_obj"] = SimplePage(has_next)

        return context

    def post(self, request, *args, **kwargs):
        """Handle inline AJAX updates for status and location."""
        if not can_access_maintainer_portal(request.user):
            return JsonResponse({"error": "Unauthorized"}, status=403)

        self.object = self.get_object()
        action = request.POST.get("action")

        if action == "update_status":
            status = request.POST.get("operational_status")
            if status in MachineInstance.OperationalStatus.values:
                self.object.operational_status = status
                self.object.updated_by = request.user
                self.object.save(update_fields=["operational_status", "updated_by", "updated_at"])
                return JsonResponse(
                    {
                        "status": "success",
                        "operational_status": status,
                        "operational_status_display": self.object.get_operational_status_display(),
                    }
                )
            return JsonResponse({"error": "Invalid status"}, status=400)

        elif action == "update_location":
            location_slug = request.POST.get("location")
            if not location_slug:
                # Clear location
                self.object.location = None
                self.object.updated_by = request.user
                self.object.save(update_fields=["location", "updated_by", "updated_at"])
                return JsonResponse(
                    {
                        "status": "success",
                        "location": "",
                        "location_display": "",
                    }
                )
            try:
                location = Location.objects.get(slug=location_slug)
                self.object.location = location
                self.object.updated_by = request.user
                self.object.save(update_fields=["location", "updated_by", "updated_at"])
                return JsonResponse(
                    {
                        "status": "success",
                        "location": location.slug,
                        "location_display": location.name,
                    }
                )
            except Location.DoesNotExist:
                return JsonResponse({"error": "Invalid location"}, status=400)

        return JsonResponse({"error": "Unknown action"}, status=400)


class MachineActivityPartialView(CanAccessMaintainerPortalMixin, View):
    """AJAX endpoint for infinite scroll of machine activity entries."""

    def get(self, request, slug):
        try:
            machine = MachineInstance.objects.get(slug=slug)
        except MachineInstance.DoesNotExist:
            return JsonResponse({"error": "Machine not found"}, status=404)

        page_num = int(request.GET.get("page", 1))
        search_query = request.GET.get("q", "").strip() or None

        page_items, has_next = get_activity_page(
            machine, page_num=page_num, page_size=10, search_query=search_query
        )

        # Render each entry using the partial template
        items_html = "".join(
            render_to_string("maintenance/partials/activity_entry.html", {"entry": entry})
            for entry in page_items
        )

        return JsonResponse(
            {
                "items": items_html,
                "has_next": has_next,
                "next_page": page_num + 1 if has_next else None,
            }
        )


class MachineUpdateView(CanAccessMaintainerPortalMixin, UpdateView):
    """Edit machine instance details (excluding model)."""

    model = MachineInstance
    form_class = MachineInstanceForm
    template_name = "catalog/machine_edit.html"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["locations"] = Location.objects.all()
        return context

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("maintainer-machine-detail", kwargs={"slug": self.object.slug})


class MachineModelUpdateView(CanAccessMaintainerPortalMixin, UpdateView):
    """Edit the pinball machine model."""

    model = MachineModel
    form_class = MachineModelForm
    template_name = "catalog/machine_model_edit.html"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get all instances of this model for sidebar
        instances = self.object.instances.all()
        context["instances"] = instances
        # Get first instance for breadcrumb navigation
        context["machine_instance"] = instances.first() if instances else None
        return context

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        form.instance._request = self.request
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("machine-model-edit", kwargs={"slug": self.object.slug})


class MachineCreateLandingView(CanAccessMaintainerPortalMixin, View):
    """Landing page for adding a new machine - select model first."""

    template_name = "catalog/machine_create_landing.html"

    def get(self, request):
        context = {"models": MachineModel.objects.all().order_by("name")}
        return TemplateResponse(request, self.template_name, context)

    def post(self, request):
        """Handle form submission - redirect to selected model page."""
        selected_slug = request.POST.get("model_slug", "")

        if selected_slug == "new":
            return redirect("machine-create-model-does-not-exist")

        # Validate the slug exists
        model = get_object_or_404(MachineModel, slug=selected_slug)
        return redirect("machine-create-model-exists", model_slug=model.slug)


class MachineCreateModelExistsView(CanAccessMaintainerPortalMixin, FormView):
    """Add an instance of a specific machine model."""

    template_name = "catalog/machine_create_model_exists.html"
    form_class = MachineCreateModelExistsForm

    def dispatch(self, request, *args, **kwargs):
        self.machine_model = get_object_or_404(MachineModel, slug=kwargs["model_slug"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["machine_model"] = self.machine_model
        context["existing_instances"] = self.machine_model.instances.all()
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["model_name"] = self.machine_model.name
        kwargs["instance_count"] = self.machine_model.instances.count()
        return kwargs

    def form_valid(self, form):
        instance = MachineInstance.objects.create(
            model=self.machine_model,
            name=form.cleaned_data["instance_name"],
            operational_status=MachineInstance.OperationalStatus.UNKNOWN,
            created_by=self.request.user,
            updated_by=self.request.user,
        )
        messages.success(
            self.request,
            format_html(
                'Machine created! You can now <a href="{}">edit the machine</a> or <a href="{}">edit the model</a>.',
                reverse("machine-edit", kwargs={"slug": instance.slug}),
                reverse("machine-model-edit", kwargs={"slug": self.machine_model.slug}),
            ),
        )
        return redirect("maintainer-machine-detail", slug=instance.slug)


class MachineCreateModelDoesNotExistView(CanAccessMaintainerPortalMixin, FormView):
    """Create a new machine model and first instance."""

    template_name = "catalog/machine_create_model_does_not_exist.html"
    form_class = MachineCreateModelDoesNotExistForm

    def form_valid(self, form):
        cleaned_data = form.cleaned_data
        with transaction.atomic():
            model = MachineModel.objects.create(
                name=cleaned_data["name"],
                manufacturer=cleaned_data.get("manufacturer") or "",
                year=cleaned_data.get("year"),
                created_by=self.request.user,
                updated_by=self.request.user,
            )
            instance = MachineInstance.objects.create(
                model=model,
                name=cleaned_data["name"],  # First instance uses model name
                operational_status=MachineInstance.OperationalStatus.UNKNOWN,
                created_by=self.request.user,
                updated_by=self.request.user,
            )
        messages.success(
            self.request,
            format_html(
                'Machine created! You can now <a href="{}">edit the machine</a> and <a href="{}">edit the model</a>.',
                reverse("machine-edit", kwargs={"slug": instance.slug}),
                reverse("machine-model-edit", kwargs={"slug": model.slug}),
            ),
        )
        return redirect("maintainer-machine-detail", slug=instance.slug)
