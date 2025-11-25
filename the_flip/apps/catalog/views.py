from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction
from django.db.models import Case, CharField, Count, F, Max, Prefetch, Q, Value, When
from django.db.models.functions import Lower
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html
from django.views.generic import DetailView, FormView, ListView, UpdateView

from the_flip.apps.catalog.forms import (
    MachineInstanceForm,
    MachineModelForm,
    MachineQuickCreateForm,
)
from the_flip.apps.catalog.models import Location, MachineInstance, MachineModel
from the_flip.apps.maintenance.forms import ProblemReportForm
from the_flip.apps.maintenance.models import LogEntry, ProblemReport


class PublicMachineListView(ListView):
    template_name = "catalog/machine_list_public.html"
    context_object_name = "machines"

    def get_queryset(self):
        return (
            MachineInstance.objects.visible()
            .annotate(
                # Count open problem reports
                open_report_count=Count(
                    "problem_reports", filter=Q(problem_reports__status=ProblemReport.STATUS_OPEN)
                ),
                # Get the most recent open problem report date
                latest_open_report_date=Max(
                    "problem_reports__created_at",
                    filter=Q(problem_reports__status=ProblemReport.STATUS_OPEN),
                ),
            )
            .prefetch_related(
                Prefetch(
                    "problem_reports",
                    queryset=ProblemReport.objects.filter(
                        status=ProblemReport.STATUS_OPEN
                    ).order_by("-created_at")[:1],
                    to_attr="latest_open_report",
                )
            )
            .order_by(
                # 1. Status priority: fixing, broken, unknown, good
                Case(
                    When(operational_status=MachineInstance.STATUS_FIXING, then=Value(1)),
                    When(operational_status=MachineInstance.STATUS_BROKEN, then=Value(2)),
                    When(operational_status=MachineInstance.STATUS_UNKNOWN, then=Value(3)),
                    When(operational_status=MachineInstance.STATUS_GOOD, then=Value(4)),
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


class MachineListView(PublicMachineListView):
    template_name = "catalog/machine_list.html"


class PublicMachineDetailView(DetailView):
    template_name = "catalog/machine_detail.html"
    queryset = MachineInstance.objects.visible()
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["problem_report_form"] = ProblemReportForm()
        return context


class MachineDetailView(PublicMachineDetailView):
    """Maintainer-facing detail page; customize as needed."""

    template_name = "catalog/maintainer_machine_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        machine = self.object
        context["problem_reports"] = ProblemReport.objects.filter(machine=machine).select_related(
            "reported_by_user"
        )
        context["open_problem_reports"] = (
            ProblemReport.objects.filter(machine=machine, status=ProblemReport.STATUS_OPEN)
            .select_related("reported_by_user")
            .order_by("-created_at")
        )
        context["log_entries"] = LogEntry.objects.filter(machine=machine).prefetch_related(
            "maintainers", "media"
        )

        # Provide locations for the dropdown (ordered by sort_order)
        context["locations"] = Location.objects.all()

        # Combine logs and problem reports into a unified timeline
        recent_logs = list(
            LogEntry.objects.filter(machine=machine)
            .prefetch_related("maintainers", "media")
            .order_by("-created_at")[:20]
        )
        recent_reports = list(
            ProblemReport.objects.filter(machine=machine)
            .select_related("reported_by_user")
            .order_by("-created_at")[:20]
        )

        # Add entry_type attribute for template differentiation
        for log in recent_logs:
            log.entry_type = "log"
        for report in recent_reports:
            report.entry_type = "problem_report"

        # Combine and sort by created_at, newest first, limit to 20
        timeline_entries = sorted(
            recent_logs + recent_reports, key=lambda x: x.created_at, reverse=True
        )[:20]

        context["timeline_entries"] = timeline_entries

        return context

    def post(self, request, *args, **kwargs):
        """Handle inline AJAX updates for status and location."""
        if not request.user.is_staff:
            return JsonResponse({"error": "Unauthorized"}, status=403)

        self.object = self.get_object()
        action = request.POST.get("action")

        if action == "update_status":
            status = request.POST.get("operational_status")
            if status in dict(MachineInstance.STATUS_CHOICES):
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


class MachineUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """Edit machine instance details (excluding model)."""

    model = MachineInstance
    form_class = MachineInstanceForm
    template_name = "catalog/machine_edit.html"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def test_func(self):
        return self.request.user.is_staff

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("maintainer-machine-detail", kwargs={"slug": self.object.slug})


class MachineModelUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """Edit the pinball machine model."""

    model = MachineModel
    form_class = MachineModelForm
    template_name = "catalog/machine_model_edit.html"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def test_func(self):
        return self.request.user.is_staff

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get first instance of this model for breadcrumb navigation
        context["machine_instance"] = self.object.instances.first()
        return context

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        # For now, redirect to the machine list since model detail view doesn't exist yet
        return reverse("maintainer-machine-list")


class MachineQuickCreateView(LoginRequiredMixin, UserPassesTestMixin, FormView):
    """Quick create view for adding a new machine instance and optionally a new model.

    This view provides a streamlined interface for maintainers to quickly add machines
    to the catalog. It supports two workflows:
    1. Creating a new model with basic info and then creating an instance
    2. Creating an instance of an existing model with a unique name override
    """

    template_name = "catalog/machine_quick_create.html"
    form_class = MachineQuickCreateForm

    def test_func(self):
        """Only staff members can create machines."""
        return self.request.user.is_staff

    def form_valid(self, form):
        """Create the model (if needed) and instance, then redirect to the detail page."""
        cleaned_data = form.cleaned_data
        model = cleaned_data.get("model")
        model_name = cleaned_data.get("model_name")
        manufacturer = cleaned_data.get("manufacturer")
        year = cleaned_data.get("year")
        name_override = cleaned_data.get("name_override")

        with transaction.atomic():
            # If no existing model selected, create a new one
            if not model:
                model = MachineModel.objects.create(
                    name=model_name,
                    manufacturer=manufacturer or "",
                    year=year,
                    created_by=self.request.user,
                    updated_by=self.request.user,
                )

            # Create the machine instance
            instance = MachineInstance.objects.create(
                model=model,
                name_override=name_override or "",
                operational_status=MachineInstance.STATUS_UNKNOWN,
                location=None,  # No location set initially
                created_by=self.request.user,
                updated_by=self.request.user,
            )

        # Add success message with links
        messages.success(
            self.request,
            format_html(
                'Machine created! You can now <a href="{}">edit the machine</a> and <a href="{}">edit the model</a>.',
                reverse("machine-edit", kwargs={"slug": instance.slug}),
                reverse("machine-model-edit", kwargs={"slug": instance.model.slug}),
            ),
        )

        # Redirect to the machine detail page
        return redirect("maintainer-machine-detail", slug=instance.slug)
